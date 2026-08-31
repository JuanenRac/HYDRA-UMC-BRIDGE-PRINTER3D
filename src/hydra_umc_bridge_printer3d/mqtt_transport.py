# =============================================================================
# HYDRA-UMC-BRIDGE-PRINTER3D - Real MQTT transport over HYDRA-UMC-MQTT-BROKER
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Reach this bridge's already-real logic over the real MQTT broker.

Every command this module can send is one `moonraker.py` already
implements (`MoonrakerJobControl.start_job`/`pause_job`/`resume_job`/
`cancel_job`, `PrinterBridge.plan`) - this module adds a new transport
(MQTT, per the ecosystem's own "MQTT via the real broker, real commands
included" decision), it does not grant any new physical authority. It
never streams raw G-code and never touches firmware, heaters or motion
directly - the same real boundary `moonraker.py` already documents
applies unchanged: this only ever asks Moonraker's own already-safe REST
API to start/pause/resume/cancel an already-sliced, already-verified
gcode file already sitting on the printer's own filesystem.

`PrinterMqttBridge.handle_message()` is the one real place topic routing
happens, and it is a pure(ish) dispatcher over a Moonraker `base_url` and
a `cell_state` callable - fully testable against the same kind of local
`ThreadingHTTPServer` fixture `test_moonraker.py` already uses, no real
MQTT broker required. `run_forever()` is the thin real-I/O glue that
lazily imports `paho-mqtt` and is not itself unit-tested beyond
import-time behavior, same convention as elsewhere in this ecosystem.

Topic scheme (see HYDRA-UMC-MQTT-BROKER's own `hydra/bridges/<name>/...`
convention, `docs/BRIDGE_TOPICS.md`):
  hydra/bridges/printer3d/state             <- published, RETAINED (PrinterStatus)
  hydra/bridges/printer3d/cmd/status        -> (empty) re-fetch Moonraker readiness + publish state
  hydra/bridges/printer3d/cmd/job           -> BridgeJob JSON (job_to_dict shape) - the shared bridge-contract gate
  hydra/bridges/printer3d/cmd/start         -> {"job": <job_to_dict>, "filename": "part.gcode"}
  hydra/bridges/printer3d/cmd/pause         -> (empty) always allowed
  hydra/bridges/printer3d/cmd/resume        -> (empty) requires a genuinely HOLDING printer
  hydra/bridges/printer3d/cmd/cancel        -> (empty) always allowed
  hydra/bridges/printer3d/cmd/<verb>/result <- published, one JSON result per command above
"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Callable

from hydra_umc_sdk.bridge_contract import BridgeError, CellState, decision_to_dict, job_from_dict

from .moonraker import MoonrakerJobControl, MoonrakerProbe, PrinterBridge, PrinterStatus

TOPIC_PREFIX = "hydra/bridges/printer3d/"


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


def _status_payload(status: PrinterStatus) -> str:
    payload = asdict(status)
    payload["state"] = status.state.value
    return json.dumps(payload)


def _result_payload(topic: str, result: object) -> MqttPublish:
    payload = asdict(result)
    return MqttPublish(topic, json.dumps(payload))


class PrinterMqttBridge:
    """Real command/telemetry dispatch for this bridge's MQTT topics.

    `cell_state` is a callable, not a fixed value - the real cell
    coordination state can change between messages, and every gated
    command here must always act on the current reading.
    """

    def __init__(self, base_url: str, cell_state: Callable[[], CellState]) -> None:
        self._base_url = base_url
        self._cell_state = cell_state
        self._probe = MoonrakerProbe()
        self._control = MoonrakerJobControl()
        self._gate = PrinterBridge()
        self._last_status: PrinterStatus | None = None

    def refresh_status(self) -> PrinterStatus:
        """Fetch real Moonraker readiness now and remember it for `start`/`resume`/`cmd/job`."""

        status = self._probe.fetch(self._base_url)
        self._last_status = status
        return status

    def handle_message(self, topic: str, payload: bytes) -> list[MqttPublish]:
        """Route one real inbound MQTT message. An unrecognised `cmd/`
        sub-topic (this bridge subscribes to `cmd/#`, a wildcard) is
        silently ignored, never an error - a future sibling topic this
        version does not know about yet must never crash the message loop."""

        if not topic.startswith(TOPIC_PREFIX):
            return []
        suffix = topic[len(TOPIC_PREFIX) :]

        if suffix == "cmd/status":
            return [MqttPublish(f"{TOPIC_PREFIX}state", _status_payload(self.refresh_status()), retain=True)]
        if suffix == "cmd/pause":
            return [_result_payload(f"{TOPIC_PREFIX}cmd/pause/result", self._control.pause_job(self._base_url))]
        if suffix == "cmd/cancel":
            return [_result_payload(f"{TOPIC_PREFIX}cmd/cancel/result", self._control.cancel_job(self._base_url))]
        if suffix == "cmd/resume":
            status = self._last_status or self.refresh_status()
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
        status = self._last_status or self.refresh_status()
        result = self._control.start_job(job, self._cell_state(), status, self._base_url, filename)
        return _result_payload(result_topic, result)

    def _handle_job(self, payload: bytes) -> MqttPublish:
        try:
            job = job_from_dict(json.loads(payload))
        except (json.JSONDecodeError, BridgeError, UnicodeDecodeError) as error:
            decision = {"allowed": False, "reason": f"malformed job payload: {error}"}
            return MqttPublish(f"{TOPIC_PREFIX}cmd/job/result", json.dumps(decision))
        status = self._last_status or self.refresh_status()
        decision = self._gate.plan(job, self._cell_state(), status)
        return MqttPublish(f"{TOPIC_PREFIX}cmd/job/result", json.dumps(decision_to_dict(decision)))


def run_forever(
    bridge: PrinterMqttBridge,
    host: str,
    port: int = 1883,
    client_id: str = "hydra-umc-bridge-printer3d",
) -> None:
    """Connect to a real HYDRA-UMC-MQTT-BROKER and dispatch forever.

    The only place this module imports paho-mqtt - lazily, so the rest of
    this module (and every test) works on a host without it installed.
    """

    try:
        import paho.mqtt.client as mqtt  # type: ignore[import-untyped]
    except ImportError as error:
        raise RuntimeError(
            "paho-mqtt is not installed - install it to connect to a real HYDRA-UMC-MQTT-BROKER "
            "(this module's topic-dispatch/gating logic works and is tested without it)"
        ) from error

    def on_connect(client: object, userdata: object, flags: object, reason_code: object, properties: object = None) -> None:
        client.subscribe(f"{TOPIC_PREFIX}cmd/#")  # type: ignore[attr-defined]

    def on_message(client: object, userdata: object, message: object) -> None:
        for publish in bridge.handle_message(message.topic, message.payload):  # type: ignore[attr-defined]
            client.publish(publish.topic, publish.payload, retain=publish.retain)  # type: ignore[attr-defined]

    client = mqtt.Client(client_id=client_id)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(host, port)
    client.loop_forever()
