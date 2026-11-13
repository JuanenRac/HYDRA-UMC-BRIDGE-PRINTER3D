# =============================================================================
# HYDRA-UMC-BRIDGE-PRINTER3D - Service configuration and wiring tests
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The configuration file, the cell-state sources and the wiring of the service."""

import contextlib
import io
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from hydra_umc_sdk.bridge_contract import CellState

from hydra_umc_bridge_printer3d import service
from hydra_umc_bridge_printer3d.service import (
    CellStateConfig,
    ConfigError,
    build_bridge,
    cell_state_reader,
    load_config,
    main,
    parse_config,
)

DEPLOY = Path(__file__).resolve().parents[1] / "docs" / "deploy"
EXAMPLE = DEPLOY / "bridge-printer3d.example.toml"
UNIT = DEPLOY / "hydra-umc-bridge-printer3d.service"
MINIMAL = {"moonraker": {"url": "http://127.0.0.1:7125"}}


def with_(**changes):
    data = json.loads(json.dumps(MINIMAL))
    data.update(changes)
    return data


class ParseTests(unittest.TestCase):
    def test_defaults_are_the_conservative_ones(self):
        config = parse_config(MINIMAL)
        self.assertEqual(config.cell_state.source, "fixed")
        self.assertEqual(config.cell_state.value, CellState.INHIBITED)
        self.assertFalse(config.global_stop.enabled)
        self.assertIsNone(config.hardening)
        self.assertIsNone(config.heartbeat_seconds)
        self.assertEqual(config.mqtt.host, "127.0.0.1")

    def test_the_example_file_is_valid_and_switches_nothing_optional_on(self):
        config = load_config(EXAMPLE)
        self.assertEqual(config.moonraker.url, "http://127.0.0.1:7125")
        self.assertEqual(config.cell_state.source, "file")
        self.assertFalse(config.global_stop.enabled)
        self.assertFalse(config.hardening.enabled)
        self.assertEqual(config.heartbeat_seconds, 0.0)

    def test_moonraker_is_required_and_must_be_a_url(self):
        with self.assertRaisesRegex(ConfigError, "moonraker.url is required"):
            parse_config({})
        with self.assertRaisesRegex(ConfigError, "absolute http"):
            parse_config({"moonraker": {"url": "printer.local"}})

    def test_unknown_keys_and_wrong_values_are_refused(self):
        with self.assertRaisesRegex(ConfigError, "unknown key in the file: moonrakr"):
            parse_config(with_(moonrakr={}))
        with self.assertRaisesRegex(ConfigError, "unknown key in global_stop: enable"):
            parse_config(with_(global_stop={"enable": True}))
        with self.assertRaisesRegex(ConfigError, "must be a int"):
            parse_config(with_(mqtt={"port": "1883"}))
        with self.assertRaisesRegex(ConfigError, "mqtt.port"):
            parse_config(with_(mqtt={"port": 70000}))
        with self.assertRaisesRegex(ConfigError, "cell_state.source"):
            parse_config(with_(cell_state={"source": "magic"}))
        with self.assertRaisesRegex(ConfigError, "cell_state.value"):
            parse_config(with_(cell_state={"value": "GO"}))
        with self.assertRaisesRegex(ConfigError, "cell_state.path"):
            parse_config(with_(cell_state={"source": "file"}))
        with self.assertRaisesRegex(ConfigError, "heartbeat.interval_seconds"):
            parse_config(with_(heartbeat={"interval_seconds": 0.2}))

    def test_the_optional_safeguards_read_from_the_file(self):
        config = parse_config(
            with_(
                global_stop={"enabled": True, "strict": True},
                hardening={"enabled": True, "max_queue": 8},
                heartbeat={"interval_seconds": 15},
                idempotency={"path": "/tmp/x.sqlite"},
            )
        )
        self.assertTrue(config.global_stop.enabled and config.global_stop.strict)
        self.assertEqual(config.hardening.max_queue, 8)
        self.assertEqual(config.heartbeat_seconds, 15.0)
        self.assertEqual(config.idempotency_path, "/tmp/x.sqlite")

    def test_a_file_that_is_missing_or_not_toml_is_a_configuration_error(self):
        with self.assertRaisesRegex(ConfigError, "cannot read"):
            load_config(DEPLOY / "nothing.toml")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.toml"
            path.write_text("[moonraker\n", encoding="utf-8")
            with self.assertRaisesRegex(ConfigError, "not valid TOML"):
                load_config(path)


class CellStateTests(unittest.TestCase):
    def test_a_fixed_source_gives_its_value(self):
        read = cell_state_reader(CellStateConfig("fixed", CellState.READY))
        self.assertIs(read(), CellState.READY)

    def test_a_file_that_is_missing_unknown_or_stale_is_safe_stop(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "cell_state")
            read = cell_state_reader(CellStateConfig("file", path=path, max_age_seconds=30.0))
            self.assertIs(read(), CellState.SAFE_STOP)  # missing
            Path(path).write_text("READY\n", encoding="utf-8")
            self.assertIs(read(), CellState.READY)
            Path(path).write_text("GO\n", encoding="utf-8")
            self.assertIs(read(), CellState.SAFE_STOP)  # unknown word
            Path(path).write_text("READY\n", encoding="utf-8")
            stale = cell_state_reader(CellStateConfig("file", path=path, max_age_seconds=30.0), clock=lambda: time.time() + 3600)
            self.assertIs(stale(), CellState.SAFE_STOP)


class WiringTests(unittest.TestCase):
    def test_the_bridge_gets_the_url_and_the_global_stop_of_the_file(self):
        bridge = build_bridge(parse_config(with_(global_stop={"enabled": True})))
        self.assertEqual(bridge._base_url, "http://127.0.0.1:7125")
        self.assertTrue(bridge.global_stop.enabled)

    def test_check_validates_and_exits_without_connecting(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), mock.patch("hydra_umc_bridge_printer3d.mqtt_transport.run_forever") as run:
            self.assertEqual(main(["--config", str(EXAMPLE), "--check"]), 0)
        run.assert_not_called()
        self.assertIn("CONFIG=PASS", out.getvalue())

    def test_a_bad_file_stops_the_start_with_status_2(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(main(["--config", str(DEPLOY / "nothing.toml")]), 2)
        self.assertIn("configuration error", err.getvalue())

    def test_a_misspelt_environment_limit_stops_the_start(self):
        err = io.StringIO()
        env = {"HYDRA_UMC_PRINTER3D_HARDENED": "1", "HYDRA_UMC_PRINTER3D_MAX_QUEUE": "many"}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "p.toml"
            path.write_text('[moonraker]\nurl = "http://127.0.0.1:7125"\n', encoding="utf-8")
            with mock.patch.dict(os.environ, env), contextlib.redirect_stderr(err):
                self.assertEqual(main(["--config", str(path), "--check"]), 2)
        self.assertIn("HYDRA_UMC_PRINTER3D_MAX_QUEUE", err.getvalue())

    def test_run_passes_the_file_values_to_the_transport_and_exits_non_zero_when_it_ends(self):
        config = parse_config(with_(mqtt={"host": "broker.local", "port": 1884}, heartbeat={"interval_seconds": 30}))
        with mock.patch.object(service, "load_config", return_value=config), mock.patch("hydra_umc_bridge_printer3d.mqtt_transport.run_forever") as run:
            self.assertEqual(main(["--config", "x.toml"]), 1)
        args, kwargs = run.call_args
        self.assertEqual(args[1:3], ("broker.local", 1884))
        self.assertEqual(kwargs["heartbeat_interval_s"], 30.0)

    def test_the_unit_runs_only_with_a_valid_configuration(self):
        text = UNIT.read_text(encoding="utf-8")
        self.assertIn("ConditionPathExists=/etc/hydra-umc/bridge-printer3d.toml", text)
        self.assertIn("ExecStartPre=/usr/bin/python3 -m hydra_umc_bridge_printer3d --check", text)
        self.assertIn("NoNewPrivileges=true", text)


if __name__ == "__main__":
    unittest.main()
