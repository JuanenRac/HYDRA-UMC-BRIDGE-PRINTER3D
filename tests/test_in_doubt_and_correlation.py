# =============================================================================
# HYDRA-UMC-BRIDGE-PRINTER3D - A key in doubt is looked up, and answers are matched to commands
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Both switches are off by default and then nothing changes. With them on: a repeated key whose first attempt left no answer is answered with what Moonraker reports and nothing is run again;
a request_id is repeated in the answers; a start may name the sha256 and the profile of its file. Moonraker fixture of the suite, evidence=simulator."""

import json
import os
import socket
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest import mock

from hydra_umc_sdk.bridge_contract import BridgeJob, CellState, JobPhase, MachineState, job_to_dict
from hydra_umc_sdk.job_intake import IdempotencyStore

from hydra_umc_bridge_printer3d import PrinterMqttBridge
from hydra_umc_bridge_printer3d.mqtt_transport import COMMAND_CORRELATION_ENVIRONMENT, IN_DOUBT_CONSULT_ENVIRONMENT, TOPIC_PREFIX
from test_mqtt_transport import MoonrakerFixtureHandler

DIGEST = "ab" * 32


def job_dict(key="key-1", phase=JobPhase.PROCESS):
    return job_to_dict(BridgeJob("job-1", key, "orchestrator", phase, MachineState.IDLE, {}))


def start_message(key="key-1", **extra):
    return json.dumps({"job": job_dict(key), "filename": "part.gcode", **extra}).encode("utf-8")


def job_message(key="key-1", **extra):
    return json.dumps({**job_dict(key, JobPhase.LOAD), **extra}).encode("utf-8")


def in_doubt_store(*keys):
    store = IdempotencyStore()
    for key in keys:
        assert store.claim(key)  # the first attempt claimed the key and never stored an answer
    return store


class FixtureCase(unittest.TestCase):
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

    def bridge(self, store=None, **options):
        return PrinterMqttBridge(self.base_url, lambda: CellState.READY, store, **options)

    def starts(self):
        return [path for path in MoonrakerFixtureHandler.requested_paths if path.startswith("/printer/print/start")]


class InDoubtTests(FixtureCase):
    def test_off_by_default_a_start_in_doubt_is_refused_as_before(self):
        out = self.bridge(in_doubt_store("start:key-1")).handle_message(f"{TOPIC_PREFIX}cmd/start", start_message())
        body = json.loads(out[0].payload)
        self.assertEqual((body["allowed"], body["executed"], body["reason"]), (False, False, "this idempotency_key was already handled"))
        self.assertEqual(MoonrakerFixtureHandler.requested_paths, [], "Moonraker is not even asked while the switch is off")

    def test_the_environment_switch_turns_it_on(self):
        with mock.patch.dict(os.environ, {IN_DOUBT_CONSULT_ENVIRONMENT: "1"}):
            bridge = self.bridge(in_doubt_store("job:key-1"))
        self.assertTrue(json.loads(bridge.handle_message(f"{TOPIC_PREFIX}cmd/job", job_message())[0].payload)["in_doubt"])

    def test_a_start_in_doubt_reports_a_print_that_is_running_and_starts_nothing(self):
        MoonrakerFixtureHandler.print_stats_state = "printing"
        out = self.bridge(in_doubt_store("start:key-1"), in_doubt_consult=True).handle_message(f"{TOPIC_PREFIX}cmd/start", start_message())
        body = json.loads(out[0].payload)
        self.assertEqual((body["allowed"], body["executed"], body["in_doubt"], body["machine_state"]), (False, False, True, "RUNNING"))
        self.assertEqual(self.starts(), [])
        self.assertEqual(out[0].qos, 1)

    def test_a_job_in_doubt_reports_the_state_and_keeps_the_shape_of_a_job_answer(self):
        out = self.bridge(in_doubt_store("job:key-1"), in_doubt_consult=True).handle_message(f"{TOPIC_PREFIX}cmd/job", job_message())
        body = json.loads(out[0].payload)
        self.assertEqual((body["allowed"], body["in_doubt"], body["machine_state"]), (False, True, "IDLE"))
        self.assertNotIn("executed", body)

    def test_an_idle_printer_does_not_turn_a_repeat_into_a_new_start(self):
        self.bridge(in_doubt_store("start:key-1"), in_doubt_consult=True).handle_message(f"{TOPIC_PREFIX}cmd/start", start_message())
        self.assertEqual(self.starts(), [])

    def test_the_answer_is_stored_so_a_further_repeat_gets_the_same_one_without_asking_again(self):
        MoonrakerFixtureHandler.print_stats_state = "paused"
        bridge = self.bridge(in_doubt_store("start:key-1"), in_doubt_consult=True)
        first = bridge.handle_message(f"{TOPIC_PREFIX}cmd/start", start_message())[0]
        MoonrakerFixtureHandler.print_stats_state = "standby"
        MoonrakerFixtureHandler.requested_paths = []
        second = bridge.handle_message(f"{TOPIC_PREFIX}cmd/start", start_message())[0]
        self.assertEqual(second.payload, first.payload)
        self.assertEqual(json.loads(first.payload)["machine_state"], "HOLDING")
        self.assertEqual(MoonrakerFixtureHandler.requested_paths, [])

    def test_a_printer_that_cannot_be_read_leaves_the_repeat_refused(self):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            dead = probe.getsockname()[1]
        bridge = PrinterMqttBridge(f"http://127.0.0.1:{dead}", lambda: CellState.READY, in_doubt_store("start:key-1"), in_doubt_consult=True)
        body = json.loads(bridge.handle_message(f"{TOPIC_PREFIX}cmd/start", start_message())[0].payload)
        self.assertEqual((body["allowed"], body["reason"]), (False, "this idempotency_key was already handled"))
        self.assertNotIn("in_doubt", body)

    def test_a_key_with_a_stored_answer_still_gets_that_answer_and_a_new_key_starts_normally(self):
        bridge = self.bridge(IdempotencyStore(), in_doubt_consult=True)
        first = bridge.handle_message(f"{TOPIC_PREFIX}cmd/start", start_message())[0]
        second = bridge.handle_message(f"{TOPIC_PREFIX}cmd/start", start_message())[0]
        self.assertEqual(second.payload, first.payload)
        self.assertTrue(json.loads(first.payload)["executed"])
        self.assertEqual(len(self.starts()), 1)

    def test_without_a_store_nothing_is_in_doubt(self):
        out = self.bridge(None, in_doubt_consult=True).handle_message(f"{TOPIC_PREFIX}cmd/start", start_message())
        self.assertTrue(json.loads(out[0].payload)["executed"])


class CorrelationOffByDefaultTests(FixtureCase):
    def test_a_request_id_is_not_repeated_and_start_fields_are_ignored_as_before(self):
        bridge = self.bridge()
        job_answer = json.loads(bridge.handle_message(f"{TOPIC_PREFIX}cmd/job", job_message(request_id="req-1"))[0].payload)
        self.assertNotIn("request_id", job_answer)
        start_answer = json.loads(bridge.handle_message(f"{TOPIC_PREFIX}cmd/start", start_message(sha256=DIGEST, profile_id="other"))[0].payload)
        self.assertTrue(start_answer["executed"])
        self.assertEqual(len(self.starts()), 1)

    def test_an_invalid_request_id_is_not_looked_at(self):
        out = self.bridge().handle_message(f"{TOPIC_PREFIX}cmd/job", job_message(request_id="has space"))
        self.assertIn("allowed", json.loads(out[0].payload))


class RequestIdTests(FixtureCase):
    def test_the_switch_can_come_from_the_environment(self):
        with mock.patch.dict(os.environ, {COMMAND_CORRELATION_ENVIRONMENT: "1"}):
            bridge = self.bridge()
        out = bridge.handle_message(f"{TOPIC_PREFIX}cmd/job", job_message(request_id="req-1"))
        self.assertEqual(json.loads(out[0].payload)["request_id"], "req-1")

    def test_every_answer_repeats_the_request_id_and_the_state_topic_is_left_alone(self):
        bridge = self.bridge(command_correlation=True)
        for suffix, payload in (("cmd/job", job_message(request_id="a.b:c-1")), ("cmd/start", start_message(request_id="a.b:c-1")),
                                ("cmd/pause", b'{"request_id": "a.b:c-1"}'), ("cmd/cancel", b'{"request_id": "a.b:c-1"}'), ("cmd/emergency_stop", b'{"request_id": "a.b:c-1"}')):
            out = bridge.handle_message(f"{TOPIC_PREFIX}{suffix}", payload)
            self.assertEqual(json.loads(out[0].payload)["request_id"], "a.b:c-1", suffix)
        status = bridge.handle_message(f"{TOPIC_PREFIX}cmd/status", b'{"request_id": "x"}')[0]
        self.assertNotIn("request_id", json.loads(status.payload))

    def test_two_clients_with_two_commands_each_get_their_own_id_back(self):
        bridge = self.bridge(command_correlation=True)
        first = bridge.handle_message(f"{TOPIC_PREFIX}cmd/job", job_message("k1", request_id="req-1"))[0]
        second = bridge.handle_message(f"{TOPIC_PREFIX}cmd/job", job_message("k2", request_id="req-2"))[0]
        self.assertEqual((json.loads(first.payload)["request_id"], json.loads(second.payload)["request_id"]), ("req-1", "req-2"))

    def test_a_repeat_gets_the_stored_answer_with_the_id_of_the_new_request(self):
        bridge = self.bridge(IdempotencyStore(), command_correlation=True)
        first = bridge.handle_message(f"{TOPIC_PREFIX}cmd/job", job_message(request_id="req-1"))[0]
        second = bridge.handle_message(f"{TOPIC_PREFIX}cmd/job", job_message(request_id="req-2"))[0]
        a, b = json.loads(first.payload), json.loads(second.payload)
        self.assertEqual((a["request_id"], b["request_id"]), ("req-1", "req-2"))
        a.pop("request_id")
        b.pop("request_id")
        self.assertEqual(a, b)

    def test_a_command_without_one_gets_the_answer_it_always_got(self):
        plain = self.bridge().handle_message(f"{TOPIC_PREFIX}cmd/job", job_message())[0].payload
        correlated = self.bridge(command_correlation=True).handle_message(f"{TOPIC_PREFIX}cmd/job", job_message())[0].payload
        self.assertEqual(plain, correlated)

    def test_an_invalid_request_id_refuses_a_job_a_start_and_a_resume_and_nothing_reaches_moonraker(self):
        bridge = self.bridge(command_correlation=True)
        for bad in ("has space", "", "x" * 65, 5):
            for suffix, payload in (("cmd/job", job_message(request_id=bad)), ("cmd/start", start_message(request_id=bad)), ("cmd/resume", json.dumps({"request_id": bad}).encode())):
                body = json.loads(bridge.handle_message(f"{TOPIC_PREFIX}{suffix}", payload)[0].payload)
                self.assertFalse(body["allowed"], (suffix, bad))
                self.assertIn("request_id", body["reason"])
        self.assertEqual(MoonrakerFixtureHandler.requested_paths, [])

    def test_a_stop_is_never_refused_for_a_bad_request_id(self):
        bridge = self.bridge(command_correlation=True)
        for suffix, path in (("cmd/pause", "/printer/print/pause"), ("cmd/cancel", "/printer/print/cancel"), ("cmd/emergency_stop", "/printer/emergency_stop")):
            body = json.loads(bridge.handle_message(f"{TOPIC_PREFIX}{suffix}", b'{"request_id": "has space"}')[0].payload)
            self.assertTrue(body["executed"], suffix)
            self.assertNotIn("request_id", body)
            self.assertIn(path, MoonrakerFixtureHandler.requested_paths)

    def test_a_payload_that_is_not_an_object_is_handled_as_before(self):
        bridge = self.bridge(command_correlation=True)
        for payload in (b"", b"[1]", b"not json", b'"text"'):
            out = bridge.handle_message(f"{TOPIC_PREFIX}cmd/pause", payload)
            self.assertTrue(json.loads(out[0].payload)["executed"])


class StartMetadataTests(FixtureCase):
    def facts(self, sha256=DIGEST, profile_id="profile-a"):
        self.asked = []

        def lookup(filename):
            self.asked.append(filename)
            return sha256, profile_id

        return lookup

    def start(self, bridge, **extra):
        return json.loads(bridge.handle_message(f"{TOPIC_PREFIX}cmd/start", start_message(**extra))[0].payload)

    def test_a_start_that_names_what_the_printer_confirms_starts(self):
        bridge = self.bridge(command_correlation=True, file_facts=self.facts())
        body = self.start(bridge, sha256=DIGEST.upper(), profile_id="profile-a")
        self.assertTrue(body["executed"])
        self.assertEqual(self.asked, ["part.gcode"])
        self.assertEqual(len(self.starts()), 1)

    def test_a_different_file_or_profile_refuses_the_start(self):
        bridge = self.bridge(command_correlation=True, file_facts=self.facts())
        for extra, words in (({"sha256": "cd" * 32}, "sha256"), ({"profile_id": "profile-b"}, "profile")):
            body = self.start(bridge, **extra)
            self.assertEqual((body["allowed"], body["executed"]), (False, False))
            self.assertIn(words, body["reason"])
        self.assertEqual(self.starts(), [])

    def test_what_the_command_does_not_name_is_not_checked(self):
        bridge = self.bridge(command_correlation=True, file_facts=self.facts(sha256=None, profile_id=None))
        self.assertTrue(self.start(bridge)["executed"])
        self.assertEqual(self.asked, [], "no facts are looked up for a start that names none")

    def test_a_value_the_printer_cannot_confirm_refuses_the_start(self):
        bridge = self.bridge(command_correlation=True, file_facts=self.facts(sha256=None))
        self.assertFalse(self.start(bridge, sha256=DIGEST)["executed"])
        no_source = self.bridge(command_correlation=True)
        self.assertFalse(self.start(no_source, profile_id="profile-a")["executed"])
        self.assertEqual(self.starts(), [])

    def test_a_malformed_value_is_a_refusal_before_the_key_is_used(self):
        store = IdempotencyStore()
        bridge = self.bridge(store, command_correlation=True, file_facts=self.facts())
        for extra in ({"sha256": "xyz"}, {"sha256": 5}, {"profile_id": "has space"}):
            body = self.start(bridge, **extra)
            self.assertFalse(body["allowed"])
            self.assertIn("malformed start payload", body["reason"])
        self.assertTrue(self.start(bridge)["executed"], "the key was never claimed by the malformed attempts")

    def test_a_refused_start_keeps_its_key_like_a_job_the_gate_refused(self):
        bridge = self.bridge(IdempotencyStore(), command_correlation=True, file_facts=self.facts())
        first = self.start(bridge, sha256="cd" * 32)
        again = self.start(bridge, sha256=DIGEST)
        self.assertEqual(again, first)
        self.assertEqual(self.starts(), [])

    def test_a_facts_source_that_raises_ends_in_a_refusal_not_a_crash(self):
        def broken(filename):
            raise OSError("no access")

        body = self.start(self.bridge(command_correlation=True, file_facts=broken), sha256=DIGEST)
        self.assertEqual((body["allowed"], body["executed"]), (False, False))
        self.assertEqual(self.starts(), [])


if __name__ == "__main__":
    unittest.main()
