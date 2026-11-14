# =============================================================================
# HYDRA-UMC-BRIDGE-PRINTER3D - tests/test_single_request.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The state of the printer from ONE request (off by default): the same verdicts as the two requests, and fail-closed on anything else. Evidence: simulator (a Moonraker stand-in)."""

import json
import os
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

from hydra_umc_sdk.bridge_contract import MachineState

from hydra_umc_bridge_printer3d import MoonrakerProbe
from hydra_umc_bridge_printer3d.moonraker import SINGLE_REQUEST_ENV


class Handler(BaseHTTPRequestHandler):
    paths: list[str] = []
    webhooks = {"state": "ready", "state_message": "Printer is ready"}
    print_stats: object = {"state": "standby"}
    raw: bytes | None = None
    code = 200

    def do_GET(self):  # noqa: N802
        type(self).paths.append(self.path)
        if type(self).raw is not None:
            body = type(self).raw
        elif self.path.startswith("/printer/objects/query"):
            status: dict = {}
            if "webhooks" in self.path:
                status["webhooks"] = type(self).webhooks
            if "print_stats" in self.path:
                status["print_stats"] = type(self).print_stats
            body = json.dumps({"result": {"status": status}}).encode()
        else:
            body = json.dumps({"result": type(self).webhooks}).encode()
        self.send_response(type(self).code)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):  # noqa: A002
        pass


class SingleRequestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.thread.join()
        cls.server.server_close()

    def setUp(self):
        Handler.paths = []
        Handler.webhooks = {"state": "ready", "state_message": "Printer is ready"}
        Handler.print_stats = {"state": "standby"}
        Handler.raw = None
        Handler.code = 200

    def test_off_by_default_the_two_requests_are_made(self):
        with mock.patch.dict(os.environ):
            os.environ.pop(SINGLE_REQUEST_ENV, None)
            probe = MoonrakerProbe()
        self.assertFalse(probe.single_request)
        self.assertEqual(probe.fetch(self.url).state, MachineState.IDLE)
        self.assertEqual(len(Handler.paths), 2)

    def test_the_environment_and_the_argument_switch_it_on(self):
        for raw, expected in (("1", True), ("0", False), ("true", False), ("", False)):
            with mock.patch.dict(os.environ, {SINGLE_REQUEST_ENV: raw}):
                self.assertEqual(MoonrakerProbe().single_request, expected, raw)
        self.assertTrue(MoonrakerProbe(single_request=True).single_request)
        with mock.patch.dict(os.environ, {SINGLE_REQUEST_ENV: "1"}):
            self.assertFalse(MoonrakerProbe(single_request=False).single_request)

    def test_on_one_request_gives_the_same_verdicts(self):
        cases = [
            ({"state": "ready", "state_message": ""}, {"state": "standby"}, MachineState.IDLE),
            ({"state": "ready", "state_message": ""}, {"state": "complete"}, MachineState.IDLE),
            ({"state": "ready", "state_message": ""}, {"state": "printing"}, MachineState.RUNNING),
            ({"state": "ready", "state_message": ""}, {"state": "paused"}, MachineState.HOLDING),
            ({"state": "ready", "state_message": ""}, {"state": "error"}, MachineState.FAULT),
            ({"state": "startup", "state_message": ""}, {"state": "standby"}, MachineState.OFFLINE),
            ({"state": "shutdown", "state_message": "mcu lost"}, {"state": "standby"}, MachineState.FAULT),
            ({"state": "error", "state_message": ""}, {"state": "printing"}, MachineState.FAULT),
            ({"state": "ready", "state_message": ""}, {"state": "something-new"}, MachineState.OFFLINE),
        ]
        for webhooks, stats, expected in cases:
            Handler.webhooks, Handler.print_stats, Handler.paths = webhooks, stats, []
            two = MoonrakerProbe(single_request=False).fetch(self.url).state
            Handler.paths = []
            one = MoonrakerProbe(single_request=True).fetch(self.url)
            self.assertEqual(len(Handler.paths), 1, (webhooks, stats))
            self.assertEqual(one.state, two, (webhooks, stats))
            self.assertEqual(one.state, expected, (webhooks, stats))

    def test_the_one_request_asks_for_both_objects(self):
        MoonrakerProbe(single_request=True).fetch(self.url)
        self.assertEqual(Handler.paths, ["/printer/objects/query?webhooks&print_stats=state"])

    def test_a_missing_part_fails_closed(self):
        for payload in ({"result": {"status": {"print_stats": {"state": "standby"}}}}, {"result": {"status": {"webhooks": {"state": "ready"}}}}, {"result": {"status": []}}, {"result": 5}, [1, 2]):
            Handler.raw = json.dumps(payload).encode()
            self.assertEqual(MoonrakerProbe(single_request=True).fetch(self.url).state, MachineState.OFFLINE, payload)

    def test_a_refusal_an_error_and_garbage_fail_closed(self):
        Handler.code = 403
        status = MoonrakerProbe(single_request=True).fetch(self.url)
        self.assertEqual(status.state, MachineState.OFFLINE)
        self.assertIn("refused the credentials", status.message)
        Handler.code, Handler.raw = 200, b"not json"
        self.assertEqual(MoonrakerProbe(single_request=True).fetch(self.url).state, MachineState.OFFLINE)
        self.assertEqual(MoonrakerProbe(single_request=True).fetch("http://127.0.0.1:9").state, MachineState.OFFLINE)

    def test_the_parser_alone_never_raises_on_a_bad_shape(self):
        for payload in (None, 3, "x", [], {}, {"result": None}):
            self.assertEqual(MoonrakerProbe.parse_combined(payload).state, MachineState.OFFLINE)  # type: ignore[arg-type,union-attr]


if __name__ == "__main__":
    unittest.main()
