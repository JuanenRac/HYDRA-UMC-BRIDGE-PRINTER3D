# =============================================================================
# HYDRA-UMC-BRIDGE-PRINTER3D - Real MQTT transport over HYDRA-UMC-MQTT-BROKER
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Reach this bridge's already-real logic over the real MQTT broker.

Every command this module can send is one `moonraker.py` already
implements (`MoonrakerJobControl.start_job`/`pause_job`/`resume_job`/
`cancel_job`/`emergency_stop`, `PrinterBridge.plan`) - this module adds a new
transport (MQTT, per the ecosystem's own "MQTT via the real broker, real
commands included" decision), it does not grant any new physical authority. It
never streams raw G-code and never touches firmware, heaters or motion
directly - the same real boundary `moonraker.py` already documents
applies unchanged: this only ever asks Moonraker's own already-safe REST
API to start/pause/resume/cancel an already-sliced, already-verified
gcode file already sitting on the printer's own filesystem (or, for the hard
stop, to halt the machine).

`PrinterMqttBridge.handle_message()` is the one real place topic routing
happens, and it is a pure(ish) dispatcher over a Moonraker `base_url` and
a `cell_state` callable - fully testable against the same kind of local
`ThreadingHTTPServer` fixture `test_moonraker.py` already uses, no real
MQTT broker required. `run_forever()` is the thin real-I/O glue that
lazily imports `paho-mqtt`.

Topic scheme (see HYDRA-UMC-MQTT-BROKER's own `hydra/bridges/<name>/...`
convention, `docs/BRIDGE_TOPICS.md`):
  hydra/bridges/printer3d/state             <- published, RETAINED (PrinterStatus + observed_at, epoch milliseconds)
  hydra/bridges/printer3d/cmd/status        -> (empty) re-fetch Moonraker readiness + publish state
  hydra/bridges/printer3d/cmd/job           -> BridgeJob JSON (job_to_dict shape) - the shared bridge-contract gate (plan only: it never acts)
  hydra/bridges/printer3d/cmd/start         -> {"job": <job_to_dict>, "filename": "part.gcode"}
  hydra/bridges/printer3d/cmd/pause         -> (empty) always allowed
  hydra/bridges/printer3d/cmd/resume        -> (empty) requires a genuinely HOLDING printer
  hydra/bridges/printer3d/cmd/cancel        -> (empty) always allowed
  hydra/bridges/printer3d/cmd/emergency_stop -> (empty) always allowed, the hard stop (Klipper M112)
  hydra/bridges/printer3d/availability      <- "online" / "offline", RETAINED (the broker publishes "offline" if this bridge dies)
  hydra/bridges/printer3d/cmd/<verb>/result <- published, one JSON result per command above

Stop commands (pause, cancel, emergency_stop) are handled on a lane of their own, so a slow Moonraker answering a
start or a status request never delays them. A payload larger than 16 KiB, a payload that cannot be read and any
unexpected failure while handling a message are answered with a refusal on the result topic; they never end the loop.
"""

from __future__ import annotations

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from typing import Callable

from hydra_umc_sdk.bridge_contract import BridgeError, CellState, JobPhase, decision_to_dict, job_from_dict
from hydra_umc_sdk.job_intake import IdempotencyStore
from hydra_umc_sdk.mqtt_connection import apply_connection_settings, settings_from_env

from .moonraker import MoonrakerJobControl, MoonrakerProbe, PrinterBridge, PrinterStatus, api_key_from_env

TOPIC_PREFIX = "hydra/bridges/printer3d/"
AVAILABILITY_TOPIC = f"{TOPIC_PREFIX}availability"

# A command is a few hundred bytes; anything larger is not a command, and parsing it is how a hostile payload costs the bridge its memory or its stack.
MAX_PAYLOAD_BYTES = 16 * 1024

# Handled on their own lane: a stop must never wait behind a slow start or status request.
STOP_VERBS = frozenset({"cmd/pause", "cmd/cancel", "cmd/emergency_stop"})

_LOG = logging.getLogger(__name__)


class MqttPublish:
    """One real outbound MQTT publish this module decided to make."""

    __slots__ = ("topic", "payload", "retain")

    def __init__(self, topic: str, payload: str, retain: bool = False) -> None:
        self.topic = topic
        self.payload = payload
        self.retain = retain

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, MqttPublish)
            and (self.topic, self.payload, self.retain) == (other.topic, other.payload, other.retain)
        )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"MqttPublish(topic={self.topic!r}, payload={self.payload!r}, retain={self.retain!r})"


def _status_payload(status: PrinterStatus, observed_at_ms: int) -> str:
    payload = asdict(status)
    payload["state"] = status.state.value
    # when this reading was taken: a retained state without it cannot be told from one that is hours old
    payload["observed_at"] = observed_at_ms
    return json.dumps(payload)


def _result_payload(topic: str, result: object) -> MqttPublish:
    payload = asdict(result)
    return MqttPublish(topic, json.dumps(payload))


def _refusal(suffix: str, reason: str) -> list[MqttPublish]:
    """The answer to a command that could not be handled; nothing for a topic that is not a `cmd/<verb>`."""
    parts = suffix.split("/")
    if len(parts) != 2 or parts[0] != "cmd":
        return []
    result = {"allowed": False, "executed": False, "reason": reason, "http_status": None}
    return [MqttPublish(f"{TOPIC_PREFIX}{suffix}/result", json.dumps(result))]


class PrinterMqttBridge:
    """Real command/telemetry dispatch for this bridge's MQTT topics.

    `cell_state` is a callable, not a fixed value - the real cell
    coordination state can change between messages, and every gated
    command here must always act on the current reading.

    `api_key` is the Moonraker API key (sent as `X-Api-Key`); when it is not
    given the `MOONRAKER_API_KEY` environment variable is used, if set.
    """

    def __init__(
        self,
        base_url: str,
        cell_state: Callable[[], CellState],
        idempotency: IdempotencyStore | None = None,
        *,
        api_key: str | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        # docs/BRIDGE_CONTRACT.md: the idempotency key of a job is handled once; a repeat gets the answer that was given, so a repeated start never starts a second print
        self._idempotency = idempotency
        self._base_url = base_url
        self._cell_state = cell_state
        self._clock = clock
        key = api_key if api_key is not None else api_key_from_env()
        self._probe = MoonrakerProbe(key)
        self._control = MoonrakerJobControl(key)
        self._gate = PrinterBridge()

    def refresh_status(self) -> PrinterStatus:
        """Fetch real Moonraker readiness right now - never cached.

        this used to be remembered in `_last_status` and reused by
        `start`/`resume`/`cmd/job` for as long as this bridge stayed up,
        with no expiry - a printer that started printing (or finished a
        pause) seconds after the last `cmd/status` fetch would still gate
        against the stale reading. Every command that needs readiness now
        calls this immediately before deciding, exactly like CNC/LASER's
        own per-command refresh."""

        return self._probe.fetch(self._base_url)

    def handle_message(self, topic: str, payload: bytes, *, retained: bool = False) -> list[MqttPublish]:
        """Route one real inbound MQTT message. An unrecognised `cmd/`
        sub-topic (this bridge subscribes to `cmd/#`, a wildcard) is
        silently ignored, never an error - a future sibling topic this
        version does not know about yet must never crash the message loop.

        `retained` is True when the broker delivered this message
        because of the MQTT retain flag, not because a client just
        published it live. `on_connect()`'s own `subscribe("cmd/#")`
        replays every currently-retained message on that wildcard the
        instant it (re)subscribes - which happens on every reconnect, not
        just once at startup - so a retained `cmd/start`/`cmd/resume`
        would otherwise re-start or re-resume a real print job with no
        new operator intent behind it, every single time this bridge
        reconnects. A retained delivery is always ignored here (a retained
        `cmd/status` too: it answers only a live request), before it ever
        reaches a real command.

        This never raises: an oversized payload and any failure while handling
        the message come back as a refusal on the verb's result topic.
        """

        if retained:
            return []
        if not topic.startswith(TOPIC_PREFIX):
            return []
        suffix = topic[len(TOPIC_PREFIX) :]
        if len(payload) > MAX_PAYLOAD_BYTES:
            return _refusal(suffix, f"payload is larger than {MAX_PAYLOAD_BYTES} bytes")
        try:
            return self._dispatch(suffix, payload)
        except Exception as error:  # noqa: BLE001 - nothing a message does may end the loop
            _LOG.exception("could not handle %s", topic)
            return _refusal(suffix, f"the command could not be handled: {type(error).__name__}")

    def _dispatch(self, suffix: str, payload: bytes) -> list[MqttPublish]:
        if suffix == "cmd/status":
            return [MqttPublish(f"{TOPIC_PREFIX}state", _status_payload(self.refresh_status(), int(self._clock() * 1000)), retain=True)]
        if suffix == "cmd/pause":
            return [_result_payload(f"{TOPIC_PREFIX}cmd/pause/result", self._control.pause_job(self._base_url))]
        if suffix == "cmd/cancel":
            return [_result_payload(f"{TOPIC_PREFIX}cmd/cancel/result", self._control.cancel_job(self._base_url))]
        if suffix == "cmd/emergency_stop":
            return [_result_payload(f"{TOPIC_PREFIX}cmd/emergency_stop/result", self._control.emergency_stop(self._base_url))]
        if suffix == "cmd/resume":
            status = self.refresh_status()
            result = self._control.resume_job(self._cell_state(), status, self._base_url)
            return [_result_payload(f"{TOPIC_PREFIX}cmd/resume/result", result)]
        if suffix == "cmd/start":
            return [self._handle_start(payload)]
        if suffix == "cmd/job":
            return [self._handle_job(payload)]
        return []

    def _handle_start(self, payload: bytes) -> MqttPublish:
        result_topic = f"{TOPIC_PREFIX}cmd/start/result"
        try:
            request = json.loads(payload)
            if not isinstance(request, dict):
                raise ValueError("start payload must be a JSON object")
            job = job_from_dict(request["job"])
            filename = request["filename"]
        except (json.JSONDecodeError, BridgeError, KeyError, ValueError, UnicodeDecodeError) as error:
            result = {"allowed": False, "executed": False, "reason": f"malformed start payload: {error}", "http_status": None}
            return MqttPublish(result_topic, json.dumps(result))
        # one key space per verb: asking the gate with `cmd/job` and then starting with the same job must start it
        key = f"start:{job.idempotency_key}"
        repeat = self._repeat(key, result_topic, {"allowed": False, "executed": False, "reason": "this idempotency_key was already handled", "http_status": None})
        if repeat is not None:
            return repeat
        try:
            status = self.refresh_status()
            result = self._control.start_job(job, self._cell_state(), status, self._base_url, filename)
            return self._answer(key, _result_payload(result_topic, result))
        except Exception as error:  # noqa: BLE001
            _LOG.exception("cmd/start failed")
            failure = {"allowed": False, "executed": False, "reason": f"the start could not be handled: {type(error).__name__}", "http_status": None}
            return self._answer(key, MqttPublish(result_topic, json.dumps(failure)))

    def _handle_job(self, payload: bytes) -> MqttPublish:
        result_topic = f"{TOPIC_PREFIX}cmd/job/result"
        try:
            job = job_from_dict(json.loads(payload))
        except (json.JSONDecodeError, BridgeError, UnicodeDecodeError) as error:
            decision = {"allowed": False, "reason": f"malformed job payload: {error}"}
            return MqttPublish(result_topic, json.dumps(decision))
        key = f"job:{job.idempotency_key}"
        repeat = self._repeat(key, result_topic, {"allowed": False, "reason": "this idempotency_key was already handled"})
        if repeat is not None:
            return repeat
        try:
            status = self.refresh_status()
            decision = self._gate.plan(job, self._cell_state(), status)
            result = decision_to_dict(decision)
            result["mode"] = "gate-only"
            if job.phase is JobPhase.ABORT:
                # the shared gate always lets an abort through, but THIS topic only answers a question: it stops nothing
                result["forwarded"] = False
                result["reason"] = "abort acknowledged by the gate only - nothing was stopped; publish cmd/cancel or cmd/emergency_stop to stop the printer"
            return self._answer(key, MqttPublish(result_topic, json.dumps(result)))
        except Exception as error:  # noqa: BLE001
            _LOG.exception("cmd/job failed")
            failure = {"allowed": False, "reason": f"the job could not be handled: {type(error).__name__}"}
            return self._answer(key, MqttPublish(result_topic, json.dumps(failure)))

    def _repeat(self, key: str, result_topic: str, fallback: dict) -> MqttPublish | None:
        """None when this job key is new (it is claimed now); otherwise the answer given the first time, which is sent again instead of running the job a second time."""
        if self._idempotency is None or self._idempotency.claim(key):
            return None
        stored = self._idempotency.recall(key)
        return MqttPublish(result_topic, stored if stored is not None else json.dumps(fallback))

    def _answer(self, key: str, publish: MqttPublish) -> MqttPublish:
        if self._idempotency is not None:
            self._idempotency.remember(key, publish.payload)
        return publish


class MessageDispatcher:
    """Takes the messages off the network thread: a slow Moonraker must not hold up the MQTT keep-alive, and a stop must not wait behind anything.

    Ordinary commands run one at a time, in order, on one lane; the stop commands (`STOP_VERBS`) run on a second lane.
    """

    def __init__(self, bridge: PrinterMqttBridge, stop_verbs: frozenset[str] = STOP_VERBS) -> None:
        self._bridge = bridge
        self._stop_verbs = frozenset(stop_verbs)
        self._lane = ThreadPoolExecutor(max_workers=1, thread_name_prefix="hydra-bridge")
        self._stop_lane = ThreadPoolExecutor(max_workers=1, thread_name_prefix="hydra-bridge-stop")

    def on_message(self, client: object, userdata: object, message: object) -> None:
        if bool(getattr(message, "retain", False)):
            return  # a replay by the broker, never a request
        topic = message.topic  # type: ignore[attr-defined]
        suffix = topic[len(TOPIC_PREFIX) :] if topic.startswith(TOPIC_PREFIX) else ""
        lane = self._stop_lane if suffix in self._stop_verbs else self._lane
        lane.submit(self._handle, client, topic, bytes(message.payload))  # type: ignore[attr-defined]

    def _handle(self, client: object, topic: str, payload: bytes) -> None:
        try:
            for publish in self._bridge.handle_message(topic, payload, retained=False):
                client.publish(publish.topic, publish.payload, retain=publish.retain)  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            _LOG.exception("could not answer %s", topic)

    def close(self, wait: bool = True) -> None:
        self._lane.shutdown(wait=wait)
        self._stop_lane.shutdown(wait=wait)


def connect_with_retry(
    connect,
    *,
    max_attempts: int = 5,
    retry_delay_seconds: float = 2.0,
    sleep=time.sleep,
) -> None:
    """Retries `connect()` on OSError (what an unreachable broker actually
    raises - connection refused, timeout), tolerating the real startup
    race a systemd unit for this bridge hits if it starts before
    HYDRA-UMC-MQTT-BROKER is listening yet (both are independent systemd
    units with no ordering guarantee across a real reboot). Only OSError is retried;
    anything else is a real bug, not a transient startup race, and
    propagates immediately. `sleep` is injectable so tests can prove the
    retry/give-up behavior without a real multi-second wait."""
    last_error: OSError | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            connect()
            return
        except OSError as error:
            last_error = error
            if attempt < max_attempts:
                sleep(retry_delay_seconds)
    raise RuntimeError(
        f"could not reach the MQTT broker after {max_attempts} attempts "
        f"({retry_delay_seconds}s apart): {last_error}"
    ) from last_error


def run_forever(
    bridge: PrinterMqttBridge,
    host: str,
    port: int = 1883,
    client_id: str = "hydra-umc-bridge-printer3d",
    *,
    max_connect_attempts: int = 5,
    connect_retry_delay_seconds: float = 2.0,
    username: str | None = None,
    password: str | None = None,
) -> None:
    """Connect to a real HYDRA-UMC-MQTT-BROKER and dispatch forever.

    The only place this module imports paho-mqtt - lazily, so the rest of
    this module (and every test) works on a host without it installed.

    `username`/`password` are optional (matching
    HYDRA-UMC-MQTT-BROKER's own `MQTT_AUTH_JSON` authentication, which is
    itself opt-in) - a broker deployed with authentication required had no
    way to be reached from here at all before this. `password` is only
    meaningful together with `username`; a caller supplying `password`
    alone almost certainly meant to set both, so that combination is
    rejected rather than silently connecting unauthenticated.

    The bridge announces itself on `availability`: "online" once connected, and
    the broker publishes "offline" (the Last Will) if the connection is lost.
    """

    if password is not None and username is None:
        raise ValueError("password was given without a username - MQTT credentials need both")

    try:
        import paho.mqtt.client as mqtt  # type: ignore[import-untyped]
    except ImportError as error:
        raise RuntimeError(
            "paho-mqtt is not installed - install it to connect to a real HYDRA-UMC-MQTT-BROKER "
            "(this module's topic-dispatch/gating logic works and is tested without it)"
        ) from error

    def on_connect(client: object, userdata: object, flags: object, reason_code: object, properties: object = None) -> None:
        if getattr(reason_code, "is_failure", False):
            return  # the broker refused us: paho reports it and retries on its own
        client.subscribe(f"{TOPIC_PREFIX}cmd/#")  # type: ignore[attr-defined]
        client.publish(AVAILABILITY_TOPIC, "online", qos=1, retain=True)  # type: ignore[attr-defined]

    dispatcher = MessageDispatcher(bridge)
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
    # the credentials and TLS of this service's environment (HYDRA_MQTT_*), unless the caller gave a user name explicitly
    apply_connection_settings(client, settings_from_env(), username=username, password=password)
    client.reconnect_delay_set(min_delay=1, max_delay=30)
    client.will_set(AVAILABILITY_TOPIC, "offline", qos=1, retain=True)
    client.on_connect = on_connect
    client.on_message = dispatcher.on_message
    try:
        connect_with_retry(
            lambda: client.connect(host, port),
            max_attempts=max_connect_attempts,
            retry_delay_seconds=connect_retry_delay_seconds,
        )
        client.loop_forever()
    finally:
        dispatcher.close(wait=False)
