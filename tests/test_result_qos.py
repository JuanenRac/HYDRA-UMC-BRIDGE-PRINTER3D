# =============================================================================
# HYDRA-UMC-BRIDGE-PRINTER3D - tests/test_result_qos.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The answer to a command is published at least once (QoS 1) and the retained state is not."""

import json
import threading
import unittest
from http.server import ThreadingHTTPServer

from hydra_umc_sdk.bridge_contract import CellState, JobPhase, job_to_dict

from hydra_umc_bridge_printer3d import PrinterMqttBridge
from hydra_umc_bridge_printer3d.mqtt_transport import RESULT_QOS, TOPIC_PREFIX
from test_mqtt_transport import MoonrakerFixtureHandler, job


class ResultQosTests(unittest.TestCase):
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

    def test_the_constant_is_at_least_once(self):
        self.assertEqual(RESULT_QOS, 1)

    def test_answers_to_commands_are_qos_1(self):
        for verb in ("pause", "cancel", "resume"):
            for publish in self.bridge().handle_message(f"{TOPIC_PREFIX}cmd/{verb}", b""):
                self.assertTrue(publish.topic.endswith("/result"), publish.topic)
                self.assertEqual(publish.qos, 1, verb)

    def test_the_answer_to_a_start_and_to_a_gated_start_are_qos_1(self):
        request = json.dumps({"job": job_to_dict(job(phase=JobPhase.PROCESS)), "filename": "part.gcode"}).encode("utf-8")
        for cell in (CellState.READY, CellState.FAULT):
            publishes = self.bridge(cell_state=cell).handle_message(f"{TOPIC_PREFIX}cmd/start", request)
            self.assertTrue(publishes)
            self.assertTrue(all(p.qos == 1 for p in publishes))

    def test_a_refusal_for_a_bad_payload_is_qos_1(self):
        publishes = self.bridge().handle_message(f"{TOPIC_PREFIX}cmd/start", b"not json")
        self.assertTrue(publishes)
        self.assertTrue(all(p.qos == 1 for p in publishes))

    def test_the_retained_state_stays_at_qos_0(self):
        publishes = self.bridge().handle_message(f"{TOPIC_PREFIX}cmd/status", b"")
        self.assertEqual(len(publishes), 1)
        self.assertTrue(publishes[0].retain)
        self.assertEqual(publishes[0].qos, 0)


if __name__ == "__main__":
    unittest.main()
