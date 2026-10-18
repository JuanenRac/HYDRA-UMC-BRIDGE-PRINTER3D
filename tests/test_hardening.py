# =============================================================================
# HYDRA-UMC-BRIDGE-PRINTER3D - Hostile payloads, honest answers and the stop lane
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""What a client of the broker can do to this bridge must never end its loop, and what the bridge answers must not claim more than it did."""

import json
import sys
import threading
import types
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

from hydra_umc_sdk.bridge_contract import BridgeJob, CellState, JobPhase, MachineState, job_to_dict
from hydra_umc_sdk.job_intake import IdempotencyStore

from hydra_umc_bridge_printer3d import MoonrakerJobControl, MoonrakerProbe, PrinterMqttBridge
from hydra_umc_bridge_printer3d.moonraker import PrinterStatus, validate_gcode_filename
from hydra_umc_bridge_printer3d.mqtt_transport import (
    AVAILABILITY_TOPIC,
    MAX_PAYLOAD_BYTES,
    TOPIC_PREFIX,
    MessageDispatcher,
)


class RecordingHandler(BaseHTTPRequestHandler):
    """A Moonraker that records what it was asked and can demand an API key."""

    log: list[tuple[str, str, str | None]] = []
    required_key: str | None = None
    metadata_status = 200
    klippy_state = "ready"

    def _reply(self, status, body):
        payload = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _authorised(self):
        type(self).log.append((self.command, self.path, self.headers.get("X-Api-Key")))
        if type(self).required_key is not None and self.headers.get("X-Api-Key") != type(self).required_key:
            self._reply(401, {"error": "unauthorized"})
            return False
        return True

    def do_GET(self):  # noqa: N802
        if not self._authorised():
            return
        if self.path.startswith("/server/files/metadata"):
            self._reply(type(self).metadata_status, {"result": {}} if type(self).metadata_status == 200 else {"error": "x"})
        elif self.path.startswith("/printer/objects/query"):
            self._reply(200, {"result": {"status": {"print_stats": {"state": "standby"}}}})
        else:
            self._reply(200, {"result": {"state": type(self).klippy_state, "state_message": "x"}})

    def do_POST(self):  # noqa: N802
        if not self._authorised():
            return
        self._reply(200, {"result": "ok"})

    def log_message(self, format, *args):  # noqa: A002
        pass


def job(key="k1", phase=JobPhase.PROCESS):
    return BridgeJob("job-1", key, "orchestrator", phase, MachineState.IDLE, {})


def start_payload(key="k1", filename="part.gcode"):
    return json.dumps({"job": job_to_dict(job(key)), "filename": filename}).encode("utf-8")


class MoonrakerCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), RecordingHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.thread.join()
        cls.server.server_close()

    def setUp(self):
        RecordingHandler.log = []
        RecordingHandler.required_key = None
        RecordingHandler.metadata_status = 200
        RecordingHandler.klippy_state = "ready"

    def bridge(self, store=None, **kwargs):
        return PrinterMqttBridge(self.base_url, lambda: CellState.READY, store, **kwargs)

    def posts(self, suffix=""):
        return [path for method, path, _ in RecordingHandler.log if method == "POST" and path.startswith(suffix)]


class HostilePayloadTests(MoonrakerCase):
    def test_a_deeply_nested_json_is_a_refusal_not_an_exception(self):
        for verb in ("job", "start"):
            publishes = self.bridge().handle_message(f"{TOPIC_PREFIX}cmd/{verb}", b"[" * 100_000, retained=False)
            self.assertEqual(len(publishes), 1, verb)
            self.assertFalse(json.loads(publishes[0].payload)["allowed"])
            self.assertEqual(publishes[0].topic, f"{TOPIC_PREFIX}cmd/{verb}/result")

    def test_a_payload_over_the_limit_is_refused_before_it_is_parsed(self):
        publishes = self.bridge().handle_message(f"{TOPIC_PREFIX}cmd/start", b" " * (MAX_PAYLOAD_BYTES + 1))
        self.assertIn("larger than", json.loads(publishes[0].payload)["reason"])
        self.assertEqual(self.posts(), [])

    def test_an_unexpected_failure_while_handling_is_a_refusal(self):
        def broken():
            raise RuntimeError("the cell state source is down")

        bridge = PrinterMqttBridge(self.base_url, broken)
        publishes = bridge.handle_message(f"{TOPIC_PREFIX}cmd/resume", b"")
        self.assertEqual(len(publishes), 1)
        self.assertFalse(json.loads(publishes[0].payload)["executed"])

    def test_a_failure_in_the_middle_of_a_job_leaves_an_honest_answer_for_the_key(self):
        calls = []

        def broken():
            calls.append(1)
            raise RuntimeError("down")

        store = IdempotencyStore()
        bridge = PrinterMqttBridge(self.base_url, broken, store)
        first = bridge.handle_message(f"{TOPIC_PREFIX}cmd/start", start_payload())[0]
        again = bridge.handle_message(f"{TOPIC_PREFIX}cmd/start", start_payload())[0]
        self.assertFalse(json.loads(first.payload)["executed"])
        self.assertEqual(again.payload, first.payload)
        self.assertIn("could not be handled", json.loads(first.payload)["reason"])
        self.assertEqual(len(calls), 1)


class IdempotencyPerVerbTests(MoonrakerCase):
    def test_a_job_checked_with_the_gate_can_then_be_started_with_the_same_key(self):
        bridge = self.bridge(IdempotencyStore())
        gate = bridge.handle_message(f"{TOPIC_PREFIX}cmd/job", json.dumps(job_to_dict(job("same"))).encode("utf-8"))[0]
        self.assertTrue(json.loads(gate.payload)["allowed"])
        started = bridge.handle_message(f"{TOPIC_PREFIX}cmd/start", start_payload("same"))[0]
        self.assertTrue(json.loads(started.payload)["executed"])
        self.assertEqual(len(self.posts("/printer/print/start")), 1)

    def test_a_repeated_start_still_starts_once(self):
        bridge = self.bridge(IdempotencyStore())
        bridge.handle_message(f"{TOPIC_PREFIX}cmd/start", start_payload("again"))
        bridge.handle_message(f"{TOPIC_PREFIX}cmd/start", start_payload("again"))
        self.assertEqual(len(self.posts("/printer/print/start")), 1)


class AbortAnswerTests(MoonrakerCase):
    def test_an_abort_through_the_gate_says_that_nothing_was_stopped(self):
        abort = BridgeJob("job-1", "abort-1", "orchestrator", JobPhase.ABORT, MachineState.RUNNING, {})
        result = json.loads(self.bridge().handle_message(f"{TOPIC_PREFIX}cmd/job", json.dumps(job_to_dict(abort)).encode("utf-8"))[0].payload)
        self.assertIs(result["forwarded"], False)
        self.assertEqual(result["mode"], "gate-only")
        self.assertIn("nothing was stopped", result["reason"])
        self.assertEqual(self.posts(), [])


class EmergencyStopTests(MoonrakerCase):
    def test_the_hard_stop_reaches_moonraker_and_is_never_deduplicated(self):
        bridge = self.bridge(IdempotencyStore())
        for _ in range(2):
            result = json.loads(bridge.handle_message(f"{TOPIC_PREFIX}cmd/emergency_stop", b"")[0].payload)
            self.assertTrue(result["executed"])
        self.assertEqual(len(self.posts("/printer/emergency_stop")), 2)


class ApiKeyTests(MoonrakerCase):
    def test_the_key_is_sent_on_reads_and_on_commands(self):
        RecordingHandler.required_key = "secret-key"
        bridge = self.bridge(api_key="secret-key")
        state = json.loads(bridge.handle_message(f"{TOPIC_PREFIX}cmd/status", b"")[0].payload)
        self.assertEqual(state["state"], "IDLE")
        result = json.loads(bridge.handle_message(f"{TOPIC_PREFIX}cmd/pause", b"")[0].payload)
        self.assertTrue(result["executed"])
        self.assertTrue(all(key == "secret-key" for _, _, key in RecordingHandler.log))

    def test_a_missing_key_is_reported_as_unauthorised_not_as_unreachable(self):
        RecordingHandler.required_key = "secret-key"
        status = MoonrakerProbe().fetch(self.base_url)
        self.assertEqual(status.state, MachineState.OFFLINE)
        self.assertIn("refused the credentials", status.message)
        result = MoonrakerJobControl().cancel_job(self.base_url)
        self.assertFalse(result.executed)
        self.assertIn("refused the credentials", result.reason)

    def test_the_key_comes_from_the_environment_when_it_is_not_given(self):
        RecordingHandler.required_key = "from-env"
        with mock.patch.dict("os.environ", {"MOONRAKER_API_KEY": "from-env"}):
            bridge = self.bridge()
        result = json.loads(bridge.handle_message(f"{TOPIC_PREFIX}cmd/cancel", b"")[0].payload)
        self.assertTrue(result["executed"])


class BaseUrlTests(MoonrakerCase):
    def test_a_url_with_a_query_or_a_fragment_is_refused(self):
        for url in (f"{self.base_url}/?x=1", f"{self.base_url}#top"):
            self.assertEqual(MoonrakerProbe().fetch(url).state, MachineState.OFFLINE)
            self.assertFalse(MoonrakerJobControl().cancel_job(url).executed)
        self.assertEqual(RecordingHandler.log, [])


class StartupStateTests(unittest.TestCase):
    def test_klippy_starting_up_is_offline_not_a_fault(self):
        status = MoonrakerProbe.parse_info({"result": {"state": "startup", "state_message": ""}})
        self.assertEqual(status.state, MachineState.OFFLINE)
        self.assertEqual(MoonrakerProbe.parse_info({"result": {"state": "shutdown"}}).state, MachineState.FAULT)


class FilenameTests(MoonrakerCase):
    def test_a_legitimate_name_with_two_dots_is_fine(self):
        self.assertEqual(validate_gcode_filename("pieza..v2.gcode"), "")
        self.assertEqual(validate_gcode_filename("folder/part.GCODE"), "")

    def test_names_that_escape_or_are_not_gcode_are_refused(self):
        for name in ("a/../b.gcode", "../b.gcode", "/etc/x.gcode", "~/x.gcode", "a\\b.gcode", "a\x00b.gcode", "a\nb.gcode", "part.txt", "part", " part.gcode", "./part.gcode", "", None, 5):
            self.assertNotEqual(validate_gcode_filename(name), "", repr(name))

    def test_a_file_moonraker_does_not_have_is_not_started(self):
        RecordingHandler.metadata_status = 404
        printer = PrinterStatus(MachineState.IDLE, "ready")
        result = MoonrakerJobControl().start_job(job(), CellState.READY, printer, self.base_url, "ghost.gcode")
        self.assertFalse(result.executed)
        self.assertIn("no file", result.reason)
        self.assertEqual(self.posts(), [])


class StateTests(MoonrakerCase):
    def test_the_state_carries_the_moment_it_was_observed(self):
        bridge = self.bridge(clock=lambda: 1234.5)
        publish = bridge.handle_message(f"{TOPIC_PREFIX}cmd/status", b"")[0]
        self.assertTrue(publish.retain)
        self.assertEqual(json.loads(publish.payload)["observed_at"], 1234500)


class DispatcherTests(unittest.TestCase):
    def test_a_stop_is_not_held_up_by_a_slow_command(self):
        release = threading.Event()
        started = threading.Event()
        answered = threading.Event()

        class Bridge:
            def handle_message(self, topic, payload, *, retained=False):
                if topic.endswith("cmd/start"):
                    started.set()
                    release.wait(5)
                else:
                    answered.set()
                return []

        dispatcher = MessageDispatcher(Bridge())
        try:
            dispatcher.on_message(mock.MagicMock(), None, mock.MagicMock(topic=f"{TOPIC_PREFIX}cmd/start", payload=b"", retain=False))
            self.assertTrue(started.wait(2))
            dispatcher.on_message(mock.MagicMock(), None, mock.MagicMock(topic=f"{TOPIC_PREFIX}cmd/cancel", payload=b"", retain=False))
            self.assertTrue(answered.wait(2), "the stop waited behind the slow start")
        finally:
            release.set()
            dispatcher.close()

    def test_ordinary_commands_keep_their_order(self):
        seen = []

        class Bridge:
            def handle_message(self, topic, payload, *, retained=False):
                seen.append(topic)
                return []

        dispatcher = MessageDispatcher(Bridge())
        for verb in ("status", "job", "start"):
            dispatcher.on_message(mock.MagicMock(), None, mock.MagicMock(topic=f"{TOPIC_PREFIX}cmd/{verb}", payload=b"", retain=False))
        dispatcher.close()
        self.assertEqual(seen, [f"{TOPIC_PREFIX}cmd/{verb}" for verb in ("status", "job", "start")])

    def test_the_answers_are_published(self):
        client = mock.MagicMock()
        dispatcher = MessageDispatcher(PrinterMqttBridge("http://127.0.0.1:1", lambda: CellState.READY))
        dispatcher.on_message(client, None, mock.MagicMock(topic=f"{TOPIC_PREFIX}cmd/job", payload=b"{", retain=False))
        dispatcher.close()
        client.publish.assert_called_once()


class FakeClient:
    instances: list = []

    def __init__(self, *args, **kwargs):
        self.args, self.kwargs = args, kwargs
        self.will = None
        self.published = []
        self.subscribed = []
        self.reconnect = None
        FakeClient.instances.append(self)

    def username_pw_set(self, *args, **kwargs):
        pass

    def tls_set(self, *args, **kwargs):
        pass

    def reconnect_delay_set(self, min_delay=1, max_delay=120):
        self.reconnect = (min_delay, max_delay)

    def will_set(self, topic, payload=None, qos=0, retain=False):
        self.will = (topic, payload, qos, retain)

    def connect(self, *args, **kwargs):
        pass

    def subscribe(self, topic, *args, **kwargs):
        self.subscribed.append(topic)

    def publish(self, topic, payload=None, qos=0, retain=False):
        self.published.append((topic, payload, qos, retain))

    def loop_forever(self):
        return None


class RunForeverTests(unittest.TestCase):
    def run_it(self):
        paho = types.ModuleType("paho")
        mqtt_package = types.ModuleType("paho.mqtt")
        client_module = types.ModuleType("paho.mqtt.client")
        client_module.Client = FakeClient
        client_module.CallbackAPIVersion = types.SimpleNamespace(VERSION2="v2")
        paho.mqtt = mqtt_package
        mqtt_package.client = client_module
        modules = {"paho": paho, "paho.mqtt": mqtt_package, "paho.mqtt.client": client_module}
        from hydra_umc_bridge_printer3d import run_forever

        FakeClient.instances.clear()
        with mock.patch.dict(sys.modules, modules):
            run_forever(mock.MagicMock(), "127.0.0.1")
        return FakeClient.instances[-1]

    def test_the_client_uses_the_version_2_callbacks(self):
        self.assertEqual(self.run_it().args[0], "v2")

    def test_a_last_will_marks_the_bridge_offline_and_connecting_marks_it_online(self):
        client = self.run_it()
        self.assertEqual(client.will, (AVAILABILITY_TOPIC, "offline", 1, True))
        client.on_connect(client, None, {}, types.SimpleNamespace(is_failure=False), None)
        self.assertIn((AVAILABILITY_TOPIC, "online", 1, True), client.published)
        self.assertEqual(client.subscribed, [f"{TOPIC_PREFIX}cmd/#"])
        self.assertEqual(client.reconnect, (1, 30))

    def test_a_refused_connection_does_not_announce_the_bridge_online(self):
        client = self.run_it()
        client.on_connect(client, None, {}, types.SimpleNamespace(is_failure=True), None)
        self.assertEqual(client.published, [])


if __name__ == "__main__":
    unittest.main()
