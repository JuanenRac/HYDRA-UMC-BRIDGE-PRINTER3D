# =============================================================================
# HYDRA-UMC-BRIDGE-PRINTER3D - The service: one entry point, one configuration file
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Run the bridge as a service: ``python -m hydra_umc_bridge_printer3d --config /etc/hydra-umc/bridge-printer3d.toml``.

Everything that depends on the machine lives in the configuration file and nothing in the code: where Moonraker is, the MQTT
broker, where the state of the cell comes from, the global stop, the limits of the transport and the heartbeat. The file is TOML;
a key the service does not know is refused, so a typo cannot silently leave a safeguard unconfigured.

Credentials do not go in the file: the MQTT user and password come from the service environment and the Moonraker API key from
``MOONRAKER_API_KEY``; systemd reads them from a file only root can read.

Fail-closed rules of the service:

* the state of the cell comes from ``[cell_state]``: a file that is missing, unknown or stale is ``SAFE_STOP``, and the default
  source is a fixed ``INHIBITED`` (nothing gets work);
* without a ``[moonraker]`` url the service does not start;
* every optional safeguard (global stop, limits, heartbeat) is off unless the file switches it on.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Sequence

from hydra_umc_sdk.bridge_contract import CellState
from hydra_umc_sdk.bridge_transport import BridgeHardening
from hydra_umc_sdk.global_stop import DEFAULT_TOPIC, GlobalStopSettings

from .heartbeat import MAX_INTERVAL_S, MIN_INTERVAL_S
from .moonraker_ws import MoonrakerSubscriber, PrintCompleteSettings, WebSocketSettings, websocket_url

CONFIG_ENVIRONMENT = "HYDRA_UMC_BRIDGE_PRINTER3D_CONFIG"
DEFAULT_CONFIG_PATH = "/etc/hydra-umc/bridge-printer3d.toml"

_LOG = logging.getLogger(__name__)


class ConfigError(ValueError):
    """The configuration file is wrong; the message names the key."""


@dataclass(frozen=True)
class MqttSettings:
    host: str = "127.0.0.1"
    port: int = 1883
    client_id: str = "hydra-umc-bridge-printer3d"
    max_connect_attempts: int = 5
    connect_retry_delay_seconds: float = 2.0


@dataclass(frozen=True)
class MoonrakerSettings:
    url: str | None = None


@dataclass(frozen=True)
class CellStateConfig:
    source: str = "fixed"
    value: CellState = CellState.INHIBITED
    path: str | None = None
    max_age_seconds: float = 30.0


@dataclass(frozen=True)
class ServiceConfig:
    mqtt: MqttSettings = field(default_factory=MqttSettings)
    moonraker: MoonrakerSettings = field(default_factory=MoonrakerSettings)
    cell_state: CellStateConfig = field(default_factory=CellStateConfig)
    idempotency_path: str | None = None
    global_stop: GlobalStopSettings = field(default_factory=GlobalStopSettings)
    hardening: BridgeHardening | None = None  # the [hardening] table; None: the environment of the service decides
    heartbeat_seconds: float | None = None  # the [heartbeat] table; None: the environment of the service decides; 0 is off
    websocket: WebSocketSettings = field(default_factory=WebSocketSettings)  # the [websocket] table; off by default
    print_complete: PrintCompleteSettings = field(default_factory=PrintCompleteSettings)  # the [print_complete] table; off by default
    publish_execution: bool = False  # the [execution] table: the MTConnect execution value after every state


def _table(parent: dict, key: str) -> dict:
    value = parent.get(key)
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ConfigError(f"[{key}] must be a table")
    return value


def _only(table: dict, allowed: set[str], where: str) -> None:
    unknown = sorted(set(table) - allowed)
    if unknown:
        raise ConfigError(f"unknown key in {where}: {', '.join(unknown)}")


def _kind(table: dict, key: str, kind: type, where: str, default: object = None):
    if key not in table:
        return default
    value = table[key]
    ok = isinstance(value, (int, float)) and not isinstance(value, bool) if kind is float else isinstance(value, kind) and (kind is not int or not isinstance(value, bool))
    if not ok:
        raise ConfigError(f"{where}.{key} must be a {kind.__name__}")
    return float(value) if kind is float else value


def parse_config(data: dict) -> ServiceConfig:
    """Turn the parsed TOML into the configuration, refusing what is unknown or wrong."""

    _only(data, {"mqtt", "moonraker", "cell_state", "idempotency", "global_stop", "hardening", "heartbeat", "websocket", "print_complete", "execution"}, "the file")
    mqtt_table = _table(data, "mqtt")
    _only(mqtt_table, {"host", "port", "client_id", "max_connect_attempts", "connect_retry_delay_seconds"}, "mqtt")
    d = MqttSettings()
    mqtt = MqttSettings(
        _kind(mqtt_table, "host", str, "mqtt", d.host),
        _kind(mqtt_table, "port", int, "mqtt", d.port),
        _kind(mqtt_table, "client_id", str, "mqtt", d.client_id),
        _kind(mqtt_table, "max_connect_attempts", int, "mqtt", d.max_connect_attempts),
        _kind(mqtt_table, "connect_retry_delay_seconds", float, "mqtt", d.connect_retry_delay_seconds),
    )
    if not 0 < mqtt.port <= 65535:
        raise ConfigError("mqtt.port must be 1 to 65535")

    moon_table = _table(data, "moonraker")
    _only(moon_table, {"url"}, "moonraker")
    moonraker = MoonrakerSettings(_kind(moon_table, "url", str, "moonraker"))
    if not moonraker.url:
        raise ConfigError("moonraker.url is required")
    if not moonraker.url.startswith(("http://", "https://")):
        raise ConfigError("moonraker.url must be an absolute http(s) URL")

    cell_table = _table(data, "cell_state")
    _only(cell_table, {"source", "value", "path", "max_age_seconds"}, "cell_state")
    source = _kind(cell_table, "source", str, "cell_state", "fixed")
    if source not in {"fixed", "file"}:
        raise ConfigError("cell_state.source must be fixed or file")
    try:
        value = CellState(_kind(cell_table, "value", str, "cell_state", CellState.INHIBITED.value))
    except ValueError as error:
        raise ConfigError(f"cell_state.value must be one of {', '.join(item.value for item in CellState)}") from error
    cell = CellStateConfig(source, value, _kind(cell_table, "path", str, "cell_state"), _kind(cell_table, "max_age_seconds", float, "cell_state", 30.0))
    if source == "file" and not cell.path:
        raise ConfigError("cell_state.path is required when the source is file")
    if cell.max_age_seconds <= 0:
        raise ConfigError("cell_state.max_age_seconds must be positive")

    idem = _table(data, "idempotency")
    _only(idem, {"path"}, "idempotency")
    stop_table = _table(data, "global_stop")
    _only(stop_table, {"enabled", "topic", "strict"}, "global_stop")
    try:
        global_stop = GlobalStopSettings(
            _kind(stop_table, "enabled", bool, "global_stop", False),
            _kind(stop_table, "topic", str, "global_stop", DEFAULT_TOPIC),
            _kind(stop_table, "strict", bool, "global_stop", False),
        )
    except ValueError as error:
        raise ConfigError(f"global_stop.topic: {error}") from error

    hardening_table = _table(data, "hardening")
    _only(hardening_table, {"enabled", "max_queue", "max_payload_bytes", "connect_backoff_factor", "connect_max_delay_seconds", "connect_jitter"}, "hardening")
    hardening = None
    if hardening_table:  # no table: the environment of the service decides (and, with nothing set there, nothing is limited)
        defaults = BridgeHardening(enabled=True)
        try:
            hardening = BridgeHardening(
                _kind(hardening_table, "enabled", bool, "hardening", False),
                _kind(hardening_table, "max_queue", int, "hardening", defaults.max_queue),
                _kind(hardening_table, "max_payload_bytes", int, "hardening"),
                _kind(hardening_table, "connect_backoff_factor", float, "hardening", defaults.connect_backoff_factor),
                _kind(hardening_table, "connect_max_delay_seconds", float, "hardening", defaults.connect_max_delay_seconds),
                _kind(hardening_table, "connect_jitter", float, "hardening", defaults.connect_jitter),
            )
        except ValueError as error:
            raise ConfigError(f"hardening: {error}") from error

    heartbeat_table = _table(data, "heartbeat")
    _only(heartbeat_table, {"interval_seconds"}, "heartbeat")
    heartbeat = _kind(heartbeat_table, "interval_seconds", float, "heartbeat")
    if heartbeat is not None and heartbeat != 0.0 and not MIN_INTERVAL_S <= heartbeat <= MAX_INTERVAL_S:
        raise ConfigError(f"heartbeat.interval_seconds must be 0 (off) or {MIN_INTERVAL_S:g} to {MAX_INTERVAL_S:g}")
    ws_table = _table(data, "websocket")
    _only(ws_table, {"enabled", "url", "reconnect_seconds", "telemetry_interval_seconds"}, "websocket")
    ws_defaults = WebSocketSettings()
    websocket = WebSocketSettings(
        _kind(ws_table, "enabled", bool, "websocket", False),
        _kind(ws_table, "url", str, "websocket"),
        _kind(ws_table, "reconnect_seconds", float, "websocket", ws_defaults.reconnect_seconds),
        _kind(ws_table, "telemetry_interval_seconds", float, "websocket", ws_defaults.telemetry_interval_seconds),
    )
    try:
        websocket.validate()
    except ValueError as error:
        raise ConfigError(f"websocket: {error}") from error
    exec_table = _table(data, "execution")
    _only(exec_table, {"enabled"}, "execution")
    execution = _kind(exec_table, "enabled", bool, "execution", False)
    pc_table = _table(data, "print_complete")
    _only(pc_table, {"enabled", "bed_cold_celsius"}, "print_complete")
    print_complete = PrintCompleteSettings(
        _kind(pc_table, "enabled", bool, "print_complete", False),
        _kind(pc_table, "bed_cold_celsius", float, "print_complete", PrintCompleteSettings().bed_cold_celsius),
    )
    try:
        print_complete.validate()
    except ValueError as error:
        raise ConfigError(f"print_complete: {error}") from error
    if print_complete.enabled and not websocket.enabled:
        raise ConfigError("print_complete needs [websocket] enabled: the event is made from the stream of the bed temperature")
    return ServiceConfig(mqtt, moonraker, cell, _kind(idem, "path", str, "idempotency"), global_stop, hardening, heartbeat, websocket, print_complete, execution)


def load_config(path: str | os.PathLike[str]) -> ServiceConfig:
    try:
        data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as error:
        raise ConfigError(f"cannot read {path}: {error.strerror or error}") from error
    except tomllib.TOMLDecodeError as error:
        raise ConfigError(f"{path} is not valid TOML: {error}") from error
    return parse_config(data)


def _fresh_text(path: str, max_age_seconds: float, clock: Callable[[], float]) -> str | None:
    """The first word of a small file written by someone else; ``None`` when it is missing, unreadable, empty or stale."""

    try:
        age = clock() - os.stat(path).st_mtime
        if age > max_age_seconds or age < -max_age_seconds:
            return None
        with open(path, encoding="utf-8") as handle:
            words = handle.read(256).split()
    except (OSError, UnicodeDecodeError):
        return None
    return words[0] if words else None


def cell_state_reader(config: CellStateConfig, *, clock: Callable[[], float] = time.time) -> Callable[[], CellState]:
    """The ``cell_state`` callable of the bridge: always the current reading, and ``SAFE_STOP`` whenever it cannot be trusted."""

    if config.source == "fixed":
        value = config.value
        return lambda: value
    path, max_age = config.path or "", config.max_age_seconds

    def read() -> CellState:
        word = _fresh_text(path, max_age, clock)
        try:
            return CellState(word) if word is not None else CellState.SAFE_STOP
        except ValueError:
            return CellState.SAFE_STOP

    return read


def build_bridge(config: ServiceConfig, *, clock: Callable[[], float] = time.time):
    """The bridge of the configuration (nothing is opened until it runs)."""

    from hydra_umc_sdk.job_intake import IdempotencyStore

    from .mqtt_transport import PrinterMqttBridge

    idempotency = IdempotencyStore(config.idempotency_path) if config.idempotency_path else IdempotencyStore()
    return PrinterMqttBridge(
        config.moonraker.url or "",
        cell_state_reader(config.cell_state, clock=clock),
        idempotency,
        clock=clock,
        global_stop=config.global_stop,
        publish_execution=config.publish_execution,
    )


def subscriber_factory(config: ServiceConfig, *, connect=None):
    """None when the websocket is off; otherwise the function that ``run_forever`` calls with the publish function to get the subscriber."""

    if not config.websocket.enabled:
        return None
    from .moonraker import api_key_from_env

    url = websocket_url(config.moonraker.url or "", config.websocket.url)
    extra = {} if connect is None else {"connect": connect}
    return lambda publish: MoonrakerSubscriber(url, publish, api_key=api_key_from_env(), settings=config.websocket, print_complete=config.print_complete, publish_execution=config.publish_execution, **extra)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hydra_umc_bridge_printer3d", description="HYDRA-UMC 3D-printer bridge service")
    parser.add_argument("--config", default=os.environ.get(CONFIG_ENVIRONMENT, DEFAULT_CONFIG_PATH), help=f"configuration file (default: ${CONFIG_ENVIRONMENT} or {DEFAULT_CONFIG_PATH})")
    parser.add_argument("--check", action="store_true", help="read and validate the configuration, then exit")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        config = load_config(args.config)
    except ConfigError as error:
        print(f"hydra-umc-bridge-printer3d: configuration error: {error}", file=sys.stderr)
        return 2
    # A limit that is misspelt must not be taken for none: it stops the start here, naming the variable (and `--check` says so too).
    from hydra_umc_sdk.bridge_transport import hardening_from_environment

    from .mqtt_transport import GLOBAL_STOP_ENVIRONMENT_NAME, run_forever

    hardening = config.hardening
    if hardening is None:
        try:
            hardening = hardening_from_environment(GLOBAL_STOP_ENVIRONMENT_NAME)
        except ValueError as error:
            print(f"hydra-umc-bridge-printer3d: configuration error: {error}", file=sys.stderr)
            return 2
    if args.check:
        print(f"CONFIG=PASS {args.config}")
        return 0

    try:
        bridge = build_bridge(config)
    except (RuntimeError, OSError, ValueError) as error:
        print(f"hydra-umc-bridge-printer3d: {error}", file=sys.stderr)
        return 3
    mqtt = config.mqtt
    # Restart=on-failure: a non-zero exit when the loop ends brings the service back
    try:
        run_forever(
            bridge,
            mqtt.host,
            mqtt.port,
            mqtt.client_id,
            max_connect_attempts=mqtt.max_connect_attempts,
            connect_retry_delay_seconds=mqtt.connect_retry_delay_seconds,
            hardening=hardening,
            heartbeat_interval_s=config.heartbeat_seconds,
            subscriber_factory=subscriber_factory(config),
        )
    except Exception:  # noqa: BLE001
        _LOG.exception("the bridge stopped")
    return 1
