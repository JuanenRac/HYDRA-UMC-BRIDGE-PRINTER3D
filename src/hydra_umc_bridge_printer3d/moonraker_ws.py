# =============================================================================
# HYDRA-UMC-BRIDGE-PRINTER3D - Moonraker websocket subscription
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Follow the printer through Moonraker's websocket instead of asking it every few seconds. Read-only, off by default.

Moonraker pushes a JSON-RPC notification whenever a subscribed printer object changes, and says at once when Klipper shuts down.
With the websocket switched on in the configuration file the bridge subscribes to ``webhooks``, ``print_stats``, ``extruder``,
``heater_bed``, ``display_status`` and ``virtual_sdcard`` and publishes:

* ``hydra/bridges/printer3d/state`` (retained, the same payload as ``cmd/status``) every time the state of the printer changes, and
  immediately on ``notify_klippy_shutdown``;
* ``hydra/bridges/printer3d/telemetry`` (not retained, at most once per ``telemetry_interval_seconds``) with the progress and the temperatures.

Nothing here sends a command to the printer: the only thing written to the socket is the subscription itself. The state is derived with the same
parsers as the polling probe, so both ways agree; until the first full snapshot arrived, and whenever the socket is lost, the state is ``OFFLINE``
(fail-closed). While the socket is not healthy the polling of the bridge (``cmd/status`` and the heartbeat) is what keeps working: the bridge
falls back to it by itself and the subscriber reconnects with a delay between attempts.

The socket itself comes from the optional ``websocket-client`` package, imported only when a connection is opened; ``connect`` is a parameter so
every test runs on a fake connection.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.parse import urlparse, urlunparse

from hydra_umc_sdk.bridge_contract import MachineState
from hydra_umc_sdk.bridge_transport import MqttPublish

from .moonraker import API_KEY_HEADER, MoonrakerProbe, PrinterStatus

TOPIC_PREFIX = "hydra/bridges/printer3d/"
STATE_TOPIC = f"{TOPIC_PREFIX}state"
TELEMETRY_TOPIC = f"{TOPIC_PREFIX}telemetry"

# What is subscribed to: Moonraker answers with the current value of each object and then pushes the changes.
SUBSCRIBED_OBJECTS: dict[str, None] = {
    "webhooks": None,
    "print_stats": None,
    "extruder": None,
    "heater_bed": None,
    "display_status": None,
    "virtual_sdcard": None,
}
SUBSCRIBE_ID = 1
MAX_MESSAGE_BYTES = 256 * 1024

_LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class WebSocketSettings:
    """The ``[websocket]`` table of the configuration file. Off unless ``enabled``."""

    enabled: bool = False
    url: str | None = None  # default: derived from the Moonraker URL (http -> ws, https -> wss, plus /websocket)
    reconnect_seconds: float = 5.0
    telemetry_interval_seconds: float = 1.0

    def validate(self) -> None:
        if self.reconnect_seconds <= 0:
            raise ValueError("reconnect_seconds must be positive")
        if self.telemetry_interval_seconds < 0:
            raise ValueError("telemetry_interval_seconds must not be negative")
        if self.url is not None and not self.url.startswith(("ws://", "wss://")):
            raise ValueError("url must be an absolute ws(s) URL")


def websocket_url(moonraker_url: str, override: str | None = None) -> str:
    """The websocket endpoint of a Moonraker base URL (``http://host:7125`` -> ``ws://host:7125/websocket``)."""
    if override:
        return override
    parsed = urlparse(moonraker_url.strip())
    scheme = "wss" if parsed.scheme == "https" else "ws"
    return urlunparse((scheme, parsed.netloc, "/websocket", "", "", ""))


class Connection(Protocol):
    def send(self, text: str) -> None: ...

    def recv(self) -> str | None:
        """The next text message, or ``None`` when nothing arrived within the read timeout; raises ``OSError`` when the socket is gone."""

    def close(self) -> None: ...


ConnectFunction = Callable[[str, "dict[str, str]", float], Connection]


def connect_with_websocket_client(url: str, headers: dict[str, str], timeout_seconds: float) -> Connection:
    """The real connection; the only place ``websocket-client`` is imported."""
    try:
        import websocket  # type: ignore[import-untyped]
    except ImportError as error:
        raise RuntimeError("websocket-client is not installed - install it (pip install websocket-client) to follow Moonraker over its websocket") from error
    raw = websocket.create_connection(url, timeout=timeout_seconds, header=[f"{name}: {value}" for name, value in headers.items()])

    class _Adapter:
        def send(self, text: str) -> None:
            raw.send(text)

        def recv(self) -> str | None:
            try:
                message = raw.recv()
            except websocket.WebSocketTimeoutException:
                return None
            except websocket.WebSocketException as error:
                raise OSError(str(error)) from error
            return message if isinstance(message, str) else message.decode("utf-8", "replace")

        def close(self) -> None:
            raw.close()

    return _Adapter()


def _number(value: object) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


class PrinterObjectTracker:
    """The last known value of the subscribed printer objects, and what to publish when one of them changes.

    Pure: it takes decoded JSON-RPC messages and returns the MQTT messages to publish, so it is tested without a socket.
    """

    def __init__(self, *, clock: Callable[[], float] = time.time, telemetry_interval_seconds: float = 1.0) -> None:
        self._clock = clock
        self._telemetry_interval = telemetry_interval_seconds
        self._objects: dict[str, dict[str, Any]] = {}
        self._have_snapshot = False
        self._klippy_override: PrinterStatus | None = None  # set by a klippy notification until webhooks says otherwise
        self._last_state: tuple[MachineState, str] | None = None
        self._last_telemetry = 0.0

    # --- state -------------------------------------------------------------
    @property
    def have_snapshot(self) -> bool:
        return self._have_snapshot

    def lost(self, reason: str) -> list[MqttPublish]:
        """The socket is gone: what the bridge knows is no longer current, so it says OFFLINE (the polling keeps working)."""
        self._have_snapshot = False
        self._objects.clear()
        self._klippy_override = None
        return self._state_if_changed(PrinterStatus(MachineState.OFFLINE, reason))

    def status(self) -> PrinterStatus:
        """The state of the printer, derived with the parsers of the polling probe; ``OFFLINE`` until the first snapshot."""
        if not self._have_snapshot:
            return PrinterStatus(MachineState.OFFLINE, "no websocket snapshot yet")
        if self._klippy_override is not None:
            return self._klippy_override
        webhooks = self._objects.get("webhooks", {})
        info = MoonrakerProbe.parse_info({"result": {"state": webhooks.get("state", ""), "state_message": webhooks.get("state_message", "")}})
        if info.state is not MachineState.IDLE:
            return info
        print_status = MoonrakerProbe.parse_print_stats({"result": {"status": {"print_stats": self._objects.get("print_stats", {})}}})
        return info if print_status is None else print_status

    # --- messages ----------------------------------------------------------
    def handle(self, message: object) -> list[MqttPublish]:
        """One decoded JSON-RPC message from Moonraker -> the messages to publish (usually none). A message of an unknown shape is ignored."""
        if not isinstance(message, dict):
            return []
        result = message.get("result")
        if message.get("id") == SUBSCRIBE_ID and isinstance(result, dict):
            return self._merge(result.get("status"), snapshot=True)
        method = message.get("method")
        params = message.get("params")
        if method == "notify_status_update":
            if isinstance(params, list) and params:
                return self._merge(params[0], snapshot=False)
            return []
        if method == "notify_klippy_shutdown":
            self._klippy_override = PrinterStatus(MachineState.FAULT, "klippy shutdown: Klipper stopped the printer")
            return self._state_if_changed(self.status(), force=True)
        if method == "notify_klippy_disconnected":
            self._klippy_override = PrinterStatus(MachineState.OFFLINE, "Moonraker lost the connection to Klipper")
            return self._state_if_changed(self.status())
        if method == "notify_klippy_ready":
            # the objects must be asked for again; until the new snapshot arrives the state stays as the notification left it
            self._klippy_override = PrinterStatus(MachineState.OFFLINE, "Klipper is ready again, waiting for a new snapshot")
            return self._state_if_changed(self.status())
        return []

    def _merge(self, status: object, *, snapshot: bool) -> list[MqttPublish]:
        if not isinstance(status, dict):
            return []
        for name, values in status.items():
            if isinstance(values, dict):
                self._objects.setdefault(str(name), {}).update(values)
        if snapshot:
            self._have_snapshot = True
            self._klippy_override = None
        elif not self._have_snapshot:
            return []
        if "webhooks" in status and self._klippy_override is not None and snapshot is False:
            self._klippy_override = None
        out = self._state_if_changed(self.status())
        out.extend(self._telemetry())
        return out

    # --- publications ------------------------------------------------------
    def _state_if_changed(self, status: PrinterStatus, *, force: bool = False) -> list[MqttPublish]:
        key = (status.state, status.message)
        if key == self._last_state and not force:
            return []
        self._last_state = key
        return [state_publish(status, int(self._clock() * 1000))]

    def _telemetry(self) -> list[MqttPublish]:
        now = self._clock()
        if self._telemetry_interval > 0 and now - self._last_telemetry < self._telemetry_interval:
            return []
        self._last_telemetry = now
        return [MqttPublish(TELEMETRY_TOPIC, json.dumps(self.telemetry_payload(int(now * 1000))))]

    def telemetry_payload(self, observed_at_ms: int) -> dict[str, Any]:
        stats = self._objects.get("print_stats", {})
        display = self._objects.get("display_status", {})
        sdcard = self._objects.get("virtual_sdcard", {})
        progress = _number(display.get("progress"))
        if progress is None:
            progress = _number(sdcard.get("progress"))

        def heater(name: str) -> dict[str, float | None]:
            values = self._objects.get(name, {})
            return {"temperature": _number(values.get("temperature")), "target": _number(values.get("target"))}

        filename = stats.get("filename")
        return {
            "observed_at": observed_at_ms,
            "state": self.status().state.value,
            "print_state": stats.get("state") if isinstance(stats.get("state"), str) else None,
            "filename": filename if isinstance(filename, str) and filename else None,
            "progress": progress,
            "print_duration_seconds": _number(stats.get("print_duration")),
            "extruder": heater("extruder"),
            "bed": heater("heater_bed"),
        }


def state_publish(status: PrinterStatus, observed_at_ms: int) -> MqttPublish:
    """The retained ``state`` message, with the payload that ``cmd/status`` publishes."""
    return MqttPublish(STATE_TOPIC, json.dumps({"state": status.state.value, "message": status.message, "observed_at": observed_at_ms}), retain=True)


class MoonrakerSubscriber:
    """Keeps one websocket to Moonraker open, feeds a ``PrinterObjectTracker`` and hands what it returns to ``publish``.

    ``healthy`` is true while the socket is open and the first snapshot has arrived; the bridge polls instead whenever it is false.
    """

    def __init__(
        self,
        url: str,
        publish: Callable[[MqttPublish], object],
        *,
        api_key: str | None = None,
        settings: WebSocketSettings | None = None,
        tracker: PrinterObjectTracker | None = None,
        connect: ConnectFunction = connect_with_websocket_client,
        read_timeout_seconds: float = 2.0,
    ) -> None:
        self.settings = settings or WebSocketSettings(enabled=True)
        self.settings.validate()
        self._url = url
        self._publish = publish
        self._headers = {API_KEY_HEADER: api_key} if api_key else {}
        self.tracker = tracker or PrinterObjectTracker(telemetry_interval_seconds=self.settings.telemetry_interval_seconds)
        self._connect = connect
        self._read_timeout = read_timeout_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._connected = False
        self.reconnects = 0

    @property
    def healthy(self) -> bool:
        return self._connected and self.tracker.have_snapshot

    def _send_all(self, messages: list[MqttPublish]) -> None:
        for message in messages:
            self._publish(message)

    def _subscribe_text(self) -> str:
        return json.dumps({"jsonrpc": "2.0", "method": "printer.objects.subscribe", "params": {"objects": SUBSCRIBED_OBJECTS}, "id": SUBSCRIBE_ID})

    def run_once(self) -> None:
        """One connection, from the connect to the loss of the socket (or the stop). Raises nothing: a failure is a loss."""
        try:
            connection = self._connect(self._url, self._headers, self._read_timeout)
        except Exception as error:  # noqa: BLE001 - a socket that cannot be opened is a loss like any other
            _LOG.warning("Moonraker websocket could not be opened: %s", error)
            self._send_all(self.tracker.lost(f"Moonraker websocket unavailable: {type(error).__name__}"))
            return
        self._connected = True
        try:
            connection.send(self._subscribe_text())
            while not self._stop.is_set():
                text = connection.recv()
                if text is None:
                    continue
                if len(text) > MAX_MESSAGE_BYTES:
                    _LOG.warning("a websocket message of %d bytes was ignored", len(text))
                    continue
                try:
                    message = json.loads(text)
                except ValueError:
                    continue
                self._send_all(self.tracker.handle(message))
                if isinstance(message, dict) and message.get("method") == "notify_klippy_ready":
                    connection.send(self._subscribe_text())
        except Exception as error:  # noqa: BLE001
            _LOG.warning("Moonraker websocket lost: %s", error)
            self._connected = False
            self._send_all(self.tracker.lost(f"Moonraker websocket lost: {type(error).__name__}"))
        finally:
            self._connected = False
            try:
                connection.close()
            except Exception:  # noqa: BLE001
                pass

    def run_forever(self) -> None:
        while not self._stop.is_set():
            self.run_once()
            if self._stop.is_set():
                break
            self.reconnects += 1
            self._stop.wait(self.settings.reconnect_seconds)

    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self.run_forever, name="moonraker-websocket", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self._read_timeout + self.settings.reconnect_seconds + 1.0)


def settings_from_table(table: Mapping[str, object]) -> WebSocketSettings:
    """Used by the service: the ``[websocket]`` table (already checked for unknown keys) -> settings, validated."""
    settings = WebSocketSettings(
        enabled=bool(table.get("enabled", False)),
        url=table.get("url") if isinstance(table.get("url"), str) else None,
        reconnect_seconds=float(table.get("reconnect_seconds", 5.0)),  # type: ignore[arg-type]
        telemetry_interval_seconds=float(table.get("telemetry_interval_seconds", 1.0)),  # type: ignore[arg-type]
    )
    settings.validate()
    return settings
