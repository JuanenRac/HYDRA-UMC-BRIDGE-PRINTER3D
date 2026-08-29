# =============================================================================
# HYDRA-UMC-BRIDGE-PRINTER3D - Moonraker bridge tests
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from hydra_umc_sdk.bridge_contract import BridgeJob, CellState, JobPhase, MachineState
from hydra_umc_bridge_printer3d import MoonrakerProbe, PrinterBridge


class MoonrakerFixtureHandler(BaseHTTPRequestHandler):
    """Serve the documented read-only Moonraker readiness response."""

    request_path = ""

    def do_GET(self):  # noqa: N802 - BaseHTTPRequestHandler requires this name.
        type(self).request_path = self.path
        payload = json.dumps({"state": "ready", "state_message": "Printer is ready"}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format, *args):  # noqa: A002 - inherited API name.
        """Keep the deterministic test output focused on assertions."""


class MoonrakerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), MoonrakerFixtureHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.thread.join()
        cls.server.server_close()

    def test_ready_response_maps_to_idle(self):
        status = MoonrakerProbe.parse_info({"result": {"state": "ready", "state_message": "ready"}})
        self.assertEqual(status.state, MachineState.IDLE)

    def test_error_response_never_permits_productive_work(self):
        status = MoonrakerProbe.parse_info({"result": {"state": "error", "state_message": "heater fault"}})
        job = BridgeJob("print-1", "print-key-1", "moonraker", JobPhase.PROCESS, MachineState.IDLE, {})
        self.assertFalse(PrinterBridge().plan(job, CellState.READY, status).allowed)

    def test_abort_remains_available_when_printer_faults(self):
        status = MoonrakerProbe.parse_info({"result": {"state": "shutdown"}})
        job = BridgeJob("print-1", "print-key-1", "moonraker", JobPhase.ABORT, MachineState.IDLE, {})
        self.assertTrue(PrinterBridge().plan(job, CellState.FAULT, status).allowed)

    def test_unreachable_moonraker_fails_safe_instead_of_crashing(self):
        # A real connection attempt (no mocking) against a port nothing is
        # listening on - reproduces the exact failure fetch() must survive:
        # Moonraker down, wrong URL, or the CM5 not booted yet.
        status = MoonrakerProbe().fetch("http://127.0.0.1:1", timeout_seconds=0.5)
        self.assertEqual(status.state, MachineState.OFFLINE)

    def test_http_probe_uses_documented_printer_info_endpoint(self):
        port = self.server.server_port
        status = MoonrakerProbe().fetch(f"  http://127.0.0.1:{port}/  ")
        self.assertEqual(status.state, MachineState.IDLE)
        self.assertEqual(MoonrakerFixtureHandler.request_path, "/printer/info")

    def test_non_http_endpoint_is_rejected_without_a_request(self):
        status = MoonrakerProbe().fetch("file:///printer.cfg")
        self.assertEqual(status.state, MachineState.OFFLINE)
        self.assertIn("http(s)", status.message)

    def test_non_string_endpoint_is_rejected_without_crashing(self):
        status = MoonrakerProbe().fetch(None)  # type: ignore[arg-type]
        self.assertEqual(status.state, MachineState.OFFLINE)
        self.assertIn("http(s)", status.message)


if __name__ == "__main__":
    unittest.main()
