# =============================================================================
# HYDRA-UMC-BRIDGE-PRINTER3D - tests/test_command_log.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""One log line per command, counters per verb and outcome, and the read-only `cmd/metrics` verb. Evidence: simulator (a Moonraker stand-in)."""

import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest import mock

from hydra_umc_sdk.bridge_contract import CellState, job_to_dict

from hydra_umc_bridge_printer3d import PrinterMqttBridge
from hydra_umc_bridge_printer3d.command_log import MAX_KEY_CHARS, CommandStats, key_of, outcome_of
from hydra_umc_bridge_printer3d.mqtt_transport import MAX_PAYLOAD_BYTES, TOPIC_PREFIX
from test_mqtt_transport import MoonrakerFixtureHandler, job

LOGGER = "hydra_umc_bridge_printer3d.commands"


class HelperTests(unittest.TestCase):
    def test_outcome_is_read_from_the_first_verdict(self):
        self.assertEqual(outcome_of([json.dumps({"allowed": True, "executed": True})]), "ok")
        self.assertEqual(outcome_of([json.dumps({"allowed": False})]), "refused")
        self.assertEqual(outcome_of([json.dumps({"allowed": True, "executed": False})]), "failed")
        self.assertEqual(outcome_of([]), "ok")
        self.assertEqual(outcome_of(["not json", json.dumps({"state": "idle"}), json.dumps({"allowed": False})]), "refused")

    def test_the_key_is_cut_and_only_a_json_object_has_one(self):
        self.assertEqual(key_of(json.dumps({"job": {"idempotency_key": "k" * 200}}).encode()), "k" * MAX_KEY_CHARS)
        self.assertEqual(key_of(b'{"idempotency_key": "top"}'), "top")
        for bad in (b"", b"[1]", b"nope", b'{"job": 3}', b'{"job": {"idempotency_key": 5}}'):
            self.assertIsNone(key_of(bad), bad)

    def test_the_counters_are_per_verb_and_outcome_and_copied_on_read(self):
        stats = CommandStats(clock=lambda: 1234.9)
        with self.assertLogs(LOGGER, level="INFO"):
            stats.record("cmd/pause", "ok", 1.0)
            stats.record("cmd/pause", "ok", 2.0)
            stats.record("cmd/pause", "refused", 3.0)
        snapshot = stats.snapshot()
        self.assertEqual(snapshot, {"since_s": 1234, "commands": {"cmd/pause": {"ok": 2, "refused": 1}}})
        snapshot["commands"]["cmd/pause"]["ok"] = 99
        self.assertEqual(stats.snapshot()["commands"]["cmd/pause"]["ok"], 2)


class BridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), MoonrakerFixtureHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.thread.join()
        cls.server.server_close()

    def setUp(self):
        MoonrakerFixtureHandler.requested_paths = []
        MoonrakerFixtureHandler.print_stats_state = "standby"
        MoonrakerFixtureHandler.post_status_code = 200

    def bridge(self):
        return PrinterMqttBridge(self.base_url, lambda: CellState.READY)

    def test_a_command_that_works_is_counted_ok_and_logged_with_its_verb(self):
        bridge = self.bridge()
        with self.assertLogs(LOGGER, level="INFO") as logged:
            bridge.handle_message(f"{TOPIC_PREFIX}cmd/pause", b"")
        line = json.loads(logged.records[0].getMessage())
        self.assertEqual((line["verb"], line["outcome"], line["key"]), ("cmd/pause", "ok", None))
        self.assertGreaterEqual(line["duration_ms"], 0)
        self.assertEqual(bridge.stats.snapshot()["commands"], {"cmd/pause": {"ok": 1}})

    def test_a_malformed_start_is_refused_and_the_payload_is_not_logged(self):
        bridge = self.bridge()
        with self.assertLogs(LOGGER, level="INFO") as logged:
            bridge.handle_message(f"{TOPIC_PREFIX}cmd/start", b'{"secret-looking": "value"}')
        text = logged.records[0].getMessage()
        self.assertEqual(json.loads(text)["outcome"], "refused")
        self.assertNotIn("secret-looking", text)
        self.assertNotIn("value", text)

    def test_the_key_of_a_job_goes_to_the_log(self):
        bridge = self.bridge()
        payload = json.dumps({"job": job_to_dict(job()), "filename": "part.gcode"}).encode()
        with self.assertLogs(LOGGER, level="INFO") as logged:
            bridge.handle_message(f"{TOPIC_PREFIX}cmd/start", payload)
        line = json.loads(logged.records[0].getMessage())
        self.assertEqual(line["key"], job().idempotency_key[:MAX_KEY_CHARS])
        self.assertNotIn("part.gcode", logged.records[0].getMessage())

    def test_a_message_that_is_too_large_is_refused_and_counted(self):
        bridge = self.bridge()
        with self.assertLogs(LOGGER, level="INFO"):
            bridge.handle_message(f"{TOPIC_PREFIX}cmd/start", b"x" * (MAX_PAYLOAD_BYTES + 1))
        self.assertEqual(bridge.stats.snapshot()["commands"], {"cmd/start": {"refused": 1}})

    def test_a_command_that_raises_is_counted_as_an_error_and_still_answered(self):
        bridge = self.bridge()
        with mock.patch.object(bridge, "_dispatch", side_effect=RuntimeError("boom")), self.assertLogs(LOGGER, level="INFO"), self.assertLogs(
            "hydra_umc_bridge_printer3d.mqtt_transport", level="ERROR"
        ):
            out = bridge.handle_message(f"{TOPIC_PREFIX}cmd/pause", b"")
        self.assertEqual(len(out), 1)
        self.assertFalse(json.loads(out[0].payload)["allowed"])
        self.assertEqual(bridge.stats.snapshot()["commands"], {"cmd/pause": {"error": 1}})

    def test_metrics_answers_the_counters_not_retained_and_is_not_counted_itself(self):
        bridge = self.bridge()
        with self.assertLogs(LOGGER, level="INFO"):
            bridge.handle_message(f"{TOPIC_PREFIX}cmd/status", b"")
        out = bridge.handle_message(f"{TOPIC_PREFIX}cmd/metrics", b"")
        self.assertEqual([item.topic for item in out], [f"{TOPIC_PREFIX}metrics"])
        self.assertFalse(out[0].retain)
        body = json.loads(out[0].payload)
        self.assertEqual(body["commands"], {"cmd/status": {"ok": 1}})
        self.assertNotIn("cmd/metrics", body["commands"])

    def test_a_retained_message_or_a_foreign_topic_is_not_a_command(self):
        bridge = self.bridge()
        bridge.handle_message(f"{TOPIC_PREFIX}cmd/pause", b"", retained=True)
        bridge.handle_message("other/topic", b"")
        bridge.handle_message(f"{TOPIC_PREFIX}state", b"")
        self.assertEqual(bridge.stats.snapshot()["commands"], {})


if __name__ == "__main__":
    unittest.main()
