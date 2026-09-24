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
        # real Moonraker confirms these endpoints with {"result":
        # "ok"}, never a bare JSON string - see test_moonraker.py's own
        # matching fixture comment.
        payload = b'{"result": "ok"}'
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
        # accepts (see this project's own fix) - a real caller always asks to
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
        # a cmd/start request carrying anything other than a
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

    def test_resume_always_refreshes_and_never_reuses_a_stale_cached_status_regression_for_H005(self):
        # resume/start/cmd-job used to remember whatever status the
        # last cmd/status (or the first gated command) had fetched, and
        # reuse it indefinitely - a printer that changed state for real
        # between two commands would still be gated against the earlier
        # reading. bridge instances used to live for a whole process, so
        # this reuses one bridge across two calls, exactly the case where
        # the old cache would have masked a real state change.
        bridge = self.bridge()
        MoonrakerFixtureHandler.print_stats_state = "paused"  # -> HOLDING
        first = json.loads(bridge.handle_message(f"{TOPIC_PREFIX}cmd/resume", b"")[0].payload)
        self.assertTrue(first["allowed"], first)

        # The real printer moves on (job finished/cancelled) before the
        # next command - nothing to resume anymore.
        MoonrakerFixtureHandler.print_stats_state = "standby"  # -> IDLE
        second = json.loads(bridge.handle_message(f"{TOPIC_PREFIX}cmd/resume", b"")[0].payload)
        self.assertFalse(second["allowed"], "a stale cached HOLDING status would wrongly allow this")
        self.assertIn("not HOLDING", second["reason"])

    def test_start_and_job_gate_also_always_refresh_regression_for_H005(self):
        bridge = self.bridge()
        # A first cmd/status warms nothing that should ever be trusted later.
        bridge.handle_message(f"{TOPIC_PREFIX}cmd/status", b"")

        MoonrakerFixtureHandler.print_stats_state = "printing"  # -> RUNNING, not free
        request = {"job": job_to_dict(job(phase=JobPhase.PROCESS)), "filename": "part.gcode"}
        start_result = json.loads(
            bridge.handle_message(f"{TOPIC_PREFIX}cmd/start", json.dumps(request).encode("utf-8"))[0].payload
        )
        self.assertFalse(start_result["allowed"], "a printer that is now RUNNING must refuse a new start")

        job_result = json.loads(
            bridge.handle_message(f"{TOPIC_PREFIX}cmd/job", json.dumps(job_to_dict(job())).encode("utf-8"))[0].payload
        )
        self.assertFalse(job_result["allowed"], "cmd/job must reflect the same fresh RUNNING reading")


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

    def test_password_without_username_is_rejected_before_ever_touching_paho_mqtt(self):
        # catches the most likely real misconfiguration (a password
        # set without a username) as a real, immediate error - never a
        # silent unauthenticated connection to a broker that actually
        # requires MQTT_AUTH_JSON credentials.
        from hydra_umc_bridge_printer3d import run_forever

        bridge = PrinterMqttBridge("http://127.0.0.1:1", lambda: CellState.READY)
        with self.assertRaises(ValueError) as context:
            run_forever(bridge, "127.0.0.1", password="secret")
        self.assertIn("password was given without a username", str(context.exception))

    def test_configures_broker_credentials_when_given(self):
        # HYDRA-UMC-MQTT-BROKER's own MQTT_AUTH_JSON authentication
        # is real but this bridge previously had no way at all to supply
        # a username/password to reach a broker that requires it.
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            self.skipTest("paho-mqtt is not installed in this environment - nothing to prove here")
        from unittest.mock import MagicMock, patch

        from hydra_umc_bridge_printer3d import run_forever

        bridge = PrinterMqttBridge("http://127.0.0.1:1", lambda: CellState.READY)
        fake_client = MagicMock()
        with patch.object(mqtt, "Client", return_value=fake_client):
            run_forever(bridge, "127.0.0.1", username="hydra-umc-bridge-printer3d", password="s3cret")
        fake_client.username_pw_set.assert_called_once_with("hydra-umc-bridge-printer3d", "s3cret")

    def test_does_not_touch_credentials_when_none_are_given(self):
        # Authentication stays opt-in on the client side too, matching the
        # broker's own opt-in MQTT_AUTH_JSON.
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            self.skipTest("paho-mqtt is not installed in this environment - nothing to prove here")
        from unittest.mock import MagicMock, patch

        from hydra_umc_bridge_printer3d import run_forever

        bridge = PrinterMqttBridge("http://127.0.0.1:1", lambda: CellState.READY)
        fake_client = MagicMock()
        with patch.object(mqtt, "Client", return_value=fake_client):
            run_forever(bridge, "127.0.0.1")
        fake_client.username_pw_set.assert_not_called()

    def test_on_message_passes_the_real_retain_flag_through_to_handle_message(self):
        # end to end: a real paho-mqtt MQTTMessage's own `.retain`
        # flag must reach handle_message(), or every retained-command
        # protection below would be dead code in the one real path that
        # actually needs it.
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            self.skipTest("paho-mqtt is not installed in this environment - nothing to prove here")
        from unittest.mock import MagicMock, patch

        from hydra_umc_bridge_printer3d import run_forever

        bridge = PrinterMqttBridge("http://127.0.0.1:1", lambda: CellState.READY)
        fake_client = MagicMock()
        with patch.object(mqtt, "Client", return_value=fake_client):
            run_forever(bridge, "127.0.0.1")
        on_message = fake_client.on_message
        message = MagicMock(topic=f"{TOPIC_PREFIX}cmd/pause", payload=b"", retain=True)
        on_message(fake_client, None, message)
        fake_client.publish.assert_not_called()


class RetainedMessageTests(unittest.TestCase):
    """a real broker replays every currently-retained message on the
    subscribed wildcard immediately upon (re)subscribe - which happens on
    every reconnect, not just once at startup. `cmd/start`/`cmd/resume` in
    particular would otherwise re-start or re-resume a real print job with
    no new operator intent behind it, so a retained delivery must never
    reach a real action on any of this bridge's `cmd/*` topics."""

    def bridge(self, cell_state=CellState.READY):
        return PrinterMqttBridge(self.base_url, lambda: cell_state)

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
        MoonrakerFixtureHandler.print_stats_state = "paused"  # -> HOLDING, so resume WOULD otherwise succeed

    def test_a_retained_start_never_reaches_moonraker(self):
        request = {"job": job_to_dict(job(phase=JobPhase.PROCESS)), "filename": "part.gcode"}
        publishes = self.bridge().handle_message(
            f"{TOPIC_PREFIX}cmd/start", json.dumps(request).encode("utf-8"), retained=True
        )
        self.assertEqual(publishes, [])
        self.assertFalse(any(p.startswith("/printer/print/start") for p in MoonrakerFixtureHandler.requested_paths))

    def test_a_retained_resume_never_reaches_moonraker(self):
        publishes = self.bridge().handle_message(f"{TOPIC_PREFIX}cmd/resume", b"", retained=True)
        self.assertEqual(publishes, [])
        self.assertFalse(any(p.startswith("/printer/print/resume") for p in MoonrakerFixtureHandler.requested_paths))

    def test_a_retained_cancel_never_reaches_moonraker(self):
        publishes = self.bridge().handle_message(f"{TOPIC_PREFIX}cmd/cancel", b"", retained=True)
        self.assertEqual(publishes, [])
        self.assertEqual(MoonrakerFixtureHandler.requested_paths, [])

    def test_a_live_non_retained_resume_is_unaffected(self):
        publishes = self.bridge().handle_message(f"{TOPIC_PREFIX}cmd/resume", b"", retained=False)
        self.assertTrue(json.loads(publishes[0].payload)["allowed"])


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
