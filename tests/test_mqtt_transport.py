# =============================================================================
# HYDRA-UMC-BRIDGE-PRINTER3D - Real MQTT transport tests
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Tests PrinterMqttBridge's real topic dispatch against a real local
Moonraker fixture server - no real MQTT broker required, same local
ThreadingHTTPServer pattern test_moonraker.py already uses."""

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from hydra_umc_sdk.bridge_contract import BridgeJob, CellState, JobPhase, MachineState, job_to_dict
from hydra_umc_bridge_printer3d import PrinterMqttBridge
from hydra_umc_bridge_printer3d.mqtt_transport import TOPIC_PREFIX


class MoonrakerFixtureHandler(BaseHTTPRequestHandler):
    requested_paths: list[str] = []
    print_stats_state = "standby"
    post_status_code = 200

    def do_GET(self):  # noqa: N802
        type(self).requested_paths.append(self.path)
        if self.path.startswith("/printer/objects/query"):
            payload = json.dumps({"status": {"print_stats": {"state": type(self).print_stats_state}}}).encode("utf-8")
        else:
            payload = json.dumps({"state": "ready", "state_message": "Printer is ready"}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self):  # noqa: N802
        type(self).requested_paths.append(self.path)
        payload = b'"ok"'
        self.send_response(type(self).post_status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format, *args):  # noqa: A002
        pass


def job(phase=JobPhase.LOAD, machine_state=MachineState.IDLE):
    return BridgeJob("job-1", "key-1", "orchestrator", phase, machine_state, {})


class PrinterMqttBridgeTests(unittest.TestCase):
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

    def bridge(self, cell_state=CellState.READY):
        return PrinterMqttBridge(self.base_url, lambda: cell_state)

    def test_unknown_prefix_is_ignored(self):
        self.assertEqual(self.bridge().handle_message("some/other/topic", b""), [])

    def test_unrecognised_cmd_topic_is_ignored_not_an_error(self):
        self.assertEqual(self.bridge().handle_message(f"{TOPIC_PREFIX}cmd/does_not_exist", b""), [])

    def test_status_publishes_retained_state_from_a_real_http_round_trip(self):
        publishes = self.bridge().handle_message(f"{TOPIC_PREFIX}cmd/status", b"")
        self.assertEqual(len(publishes), 1)
        self.assertEqual(publishes[0].topic, f"{TOPIC_PREFIX}state")
        self.assertTrue(publishes[0].retain)
        payload = json.loads(publishes[0].payload)
        self.assertEqual(payload["state"], "IDLE")
        self.assertIn("/printer/info", MoonrakerFixtureHandler.requested_paths)

    def test_pause_is_always_allowed_and_posts_the_real_endpoint(self):
        publishes = self.bridge().handle_message(f"{TOPIC_PREFIX}cmd/pause", b"")
        self.assertEqual(publishes[0].topic, f"{TOPIC_PREFIX}cmd/pause/result")
        self.assertTrue(json.loads(publishes[0].payload)["executed"])
        self.assertIn("/printer/print/pause", MoonrakerFixtureHandler.requested_paths)

    def test_cancel_is_always_allowed(self):
        publishes = self.bridge().handle_message(f"{TOPIC_PREFIX}cmd/cancel", b"")
        self.assertTrue(json.loads(publishes[0].payload)["executed"])

    def test_resume_requires_a_holding_printer_not_idle(self):
        MoonrakerFixtureHandler.print_stats_state = "standby"  # -> IDLE
        publishes = self.bridge().handle_message(f"{TOPIC_PREFIX}cmd/resume", b"")
        result = json.loads(publishes[0].payload)
        self.assertFalse(result["allowed"])

    def test_resume_succeeds_on_a_genuinely_paused_printer(self):
        MoonrakerFixtureHandler.print_stats_state = "paused"  # -> HOLDING
        publishes = self.bridge().handle_message(f"{TOPIC_PREFIX}cmd/resume", b"")
        result = json.loads(publishes[0].payload)
        self.assertTrue(result["allowed"])
        self.assertTrue(result["executed"])

    def test_start_posts_the_real_filename_when_gate_and_status_allow_it(self):
        # PROCESS is the only real phase cmd/start's own start_job() ever
        # accepts (see PRINT-01's own fix) - a real caller always asks to
        # start a job with a PROCESS-phase BridgeJob.
        request = {"job": job_to_dict(job(phase=JobPhase.PROCESS)), "filename": "part.gcode"}
        publishes = self.bridge().handle_message(f"{TOPIC_PREFIX}cmd/start", json.dumps(request).encode("utf-8"))
        result = json.loads(publishes[0].payload)
        self.assertTrue(result["executed"])
        self.assertTrue(any(p.startswith("/printer/print/start") for p in MoonrakerFixtureHandler.requested_paths))

    def test_start_is_gated_when_the_cell_is_not_ready(self):
        request = {"job": job_to_dict(job(phase=JobPhase.PROCESS)), "filename": "part.gcode"}
        publishes = self.bridge(cell_state=CellState.FAULT).handle_message(
            f"{TOPIC_PREFIX}cmd/start", json.dumps(request).encode("utf-8")
        )
        result = json.loads(publishes[0].payload)
        self.assertFalse(result["allowed"])

    def test_start_refuses_a_non_process_phase_job_regression_for_print_01(self):
        # PRINT-01 (P0): a cmd/start request carrying anything other than a
        # PROCESS-phase job - ABORT in particular - must never reach
        # Moonraker's own /printer/print/start.
        request = {"job": job_to_dict(job(phase=JobPhase.ABORT)), "filename": "part.gcode"}
        publishes = self.bridge().handle_message(f"{TOPIC_PREFIX}cmd/start", json.dumps(request).encode("utf-8"))
        result = json.loads(publishes[0].payload)
        self.assertFalse(result["allowed"])
        # A real status refresh may still happen before the phase is
        # checked (see start_job() - the gate itself runs first) - what
        # must never happen is the actual print/start POST.
        self.assertFalse(any(p.startswith("/printer/print/start") for p in MoonrakerFixtureHandler.requested_paths))

    def test_start_rejects_a_missing_filename_without_crashing(self):
        request = {"job": job_to_dict(job())}
        publishes = self.bridge().handle_message(f"{TOPIC_PREFIX}cmd/start", json.dumps(request).encode("utf-8"))
        result = json.loads(publishes[0].payload)
        self.assertFalse(result["allowed"])
        self.assertIn("malformed start payload", result["reason"])

    def test_start_rejects_malformed_json_without_crashing(self):
        publishes = self.bridge().handle_message(f"{TOPIC_PREFIX}cmd/start", b"{not valid")
        result = json.loads(publishes[0].payload)
        self.assertFalse(result["allowed"])

    def test_job_gate_reflects_real_moonraker_readiness(self):
        publishes = self.bridge().handle_message(
            f"{TOPIC_PREFIX}cmd/job", json.dumps(job_to_dict(job())).encode("utf-8")
        )
        self.assertTrue(json.loads(publishes[0].payload)["allowed"])

    def test_job_gate_malformed_payload_fails_closed(self):
        publishes = self.bridge().handle_message(f"{TOPIC_PREFIX}cmd/job", b"{not valid")
        decision = json.loads(publishes[0].payload)
        self.assertFalse(decision["allowed"])
        self.assertIn("malformed job payload", decision["reason"])


class RunForeverTests(unittest.TestCase):
    def test_missing_paho_mqtt_raises_a_clear_runtime_error_not_an_import_error(self):
        try:
            import paho.mqtt.client  # noqa: F401

            self.skipTest("paho-mqtt is installed in this environment - nothing to prove here")
        except ImportError:
            pass
        from hydra_umc_bridge_printer3d import run_forever

        bridge = PrinterMqttBridge("http://127.0.0.1:1", lambda: CellState.READY)
        with self.assertRaises(RuntimeError) as context:
            run_forever(bridge, "127.0.0.1")
        self.assertIn("paho-mqtt is not installed", str(context.exception))


class ConnectWithRetryTests(unittest.TestCase):
    """connect_with_retry() is pure - no real paho-mqtt/broker needed to
    prove the real startup-race tolerance that was missing here (this bridge's process used to die outright
    if it started before HYDRA-UMC-MQTT-BROKER was listening yet)."""

    def test_succeeds_on_the_first_try_without_sleeping(self):
        from hydra_umc_bridge_printer3d import connect_with_retry

        sleeps: list = []
        connect_with_retry(lambda: None, sleep=sleeps.append)
        self.assertEqual(sleeps, [])

    def test_retries_a_transient_connection_failure_then_succeeds(self):
        from hydra_umc_bridge_printer3d import connect_with_retry

        attempts = {"n": 0}
        sleeps: list = []

        def flaky_connect() -> None:
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise ConnectionRefusedError("broker not up yet")

        connect_with_retry(flaky_connect, max_attempts=5, retry_delay_seconds=1.5, sleep=sleeps.append)
        self.assertEqual(attempts["n"], 3)
        self.assertEqual(sleeps, [1.5, 1.5])

    def test_gives_up_after_max_attempts_with_a_clear_error(self):
        from hydra_umc_bridge_printer3d import connect_with_retry

        def always_fails() -> None:
            raise ConnectionRefusedError("broker still not up")

        with self.assertRaises(RuntimeError) as context:
            connect_with_retry(always_fails, max_attempts=3, retry_delay_seconds=0.01, sleep=lambda _: None)
        self.assertIn("after 3 attempts", str(context.exception))
        self.assertIn("broker still not up", str(context.exception))

    def test_a_non_os_error_is_never_retried(self):
        from hydra_umc_bridge_printer3d import connect_with_retry

        def broken_connect() -> None:
            raise ValueError("not an OSError - a real bug, not a broker being down")

        with self.assertRaises(ValueError):
            connect_with_retry(broken_connect, sleep=lambda _: None)



if __name__ == "__main__":
    unittest.main()
