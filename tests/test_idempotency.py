# =============================================================================
# HYDRA-UMC-BRIDGE-PRINTER3D - A repeated idempotency key never starts a second print
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""docs/BRIDGE_CONTRACT.md: the idempotency key of a job is handled once. A `cmd/start` that arrives twice (QoS 1, a retrying client) must not start the print twice."""

import json
import threading
import unittest
from http.server import ThreadingHTTPServer

from hydra_umc_sdk.bridge_contract import BridgeJob, CellState, JobPhase, MachineState, job_to_dict
from hydra_umc_sdk.job_intake import IdempotencyStore

from hydra_umc_bridge_printer3d import PrinterMqttBridge
from hydra_umc_bridge_printer3d.mqtt_transport import TOPIC_PREFIX
from test_mqtt_transport import MoonrakerFixtureHandler


def start_message(key="key-1"):
    job = BridgeJob("job-1", key, "orchestrator", JobPhase.PROCESS, MachineState.IDLE, {})
    return json.dumps({"job": job_to_dict(job), "filename": "part.gcode"}).encode("utf-8")


def job_message(key="key-1"):
    job = BridgeJob("job-1", key, "orchestrator", JobPhase.LOAD, MachineState.IDLE, {})
    return json.dumps(job_to_dict(job)).encode("utf-8")


class IdempotencyTests(unittest.TestCase):
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

    def bridge(self, store):
        return PrinterMqttBridge(self.base_url, lambda: CellState.READY, store)

    def starts(self):
        return [path for path in MoonrakerFixtureHandler.requested_paths if path.startswith("/printer/print/start")]

    def test_a_repeated_start_does_not_start_a_second_print(self):
        bridge = self.bridge(IdempotencyStore())
        first = bridge.handle_message(f"{TOPIC_PREFIX}cmd/start", start_message())[0]
        second = bridge.handle_message(f"{TOPIC_PREFIX}cmd/start", start_message())[0]
        self.assertTrue(json.loads(first.payload)["executed"])
        self.assertEqual(second.payload, first.payload)
        self.assertEqual(len(self.starts()), 1)

    def test_a_new_key_starts_again(self):
        bridge = self.bridge(IdempotencyStore())
        bridge.handle_message(f"{TOPIC_PREFIX}cmd/start", start_message("a"))
        bridge.handle_message(f"{TOPIC_PREFIX}cmd/start", start_message("b"))
        self.assertEqual(len(self.starts()), 2)

    def test_a_repeated_job_gets_the_first_answer(self):
        bridge = self.bridge(IdempotencyStore())
        first = bridge.handle_message(f"{TOPIC_PREFIX}cmd/job", job_message())[0]
        second = bridge.handle_message(f"{TOPIC_PREFIX}cmd/job", job_message())[0]
        self.assertEqual(second.payload, first.payload)

    def test_without_a_store_a_repeat_runs_again(self):
        bridge = self.bridge(None)
        bridge.handle_message(f"{TOPIC_PREFIX}cmd/start", start_message())
        bridge.handle_message(f"{TOPIC_PREFIX}cmd/start", start_message())
        self.assertEqual(len(self.starts()), 2)


if __name__ == "__main__":
    unittest.main()
