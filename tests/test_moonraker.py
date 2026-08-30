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
    """Serve the documented read-only Moonraker readiness responses.

    Real Moonraker exposes /printer/info (klippy_state) and
    /printer/objects/query?print_stats=state (the real, separate print job
    state) as two distinct endpoints - this fixture branches on path the
    same way a real Moonraker instance does, instead of serving one fixed
    body for every request.
    """

    requested_paths: list[str] = []
    info_response_override: bytes | None = None
    print_stats_response_override: bytes | None = None

    def do_GET(self):  # noqa: N802 - BaseHTTPRequestHandler requires this name.
        type(self).requested_paths.append(self.path)
        if self.path.startswith("/printer/objects/query"):
            payload = type(self).print_stats_response_override or json.dumps(
                {"status": {"print_stats": {"state": "standby"}}}
            ).encode("utf-8")
        else:
            payload = type(self).info_response_override or json.dumps(
                {"state": "ready", "state_message": "Printer is ready"}
            ).encode("utf-8")
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

    def setUp(self):
        MoonrakerFixtureHandler.requested_paths = []
        MoonrakerFixtureHandler.info_response_override = None
        MoonrakerFixtureHandler.print_stats_response_override = None

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
        self.assertIn("/printer/info", MoonrakerFixtureHandler.requested_paths)

    def test_ready_klippy_state_also_confirms_the_real_separate_print_stats_object(self):
        # klippy_state=ready alone is not enough - see moonraker.py's own
        # comment. A genuinely idle printer (print_stats.state=standby)
        # must confirm that second, real, documented endpoint too.
        port = self.server.server_port
        status = MoonrakerProbe().fetch(f"http://127.0.0.1:{port}")
        self.assertEqual(status.state, MachineState.IDLE)
        self.assertIn("/printer/objects/query?print_stats=state", MoonrakerFixtureHandler.requested_paths)

    def test_printing_print_stats_overrides_a_bare_klippy_ready_reading(self):
        # Klipper itself stays klippy_state=ready throughout an entire
        # print - print_stats.state=printing is the real, separate signal
        # that the print head is not actually free.
        MoonrakerFixtureHandler.print_stats_response_override = json.dumps(
            {"status": {"print_stats": {"state": "printing"}}}
        ).encode("utf-8")
        status = MoonrakerProbe().fetch(f"http://127.0.0.1:{self.server.server_port}")
        self.assertEqual(status.state, MachineState.RUNNING)
        job = BridgeJob("print-1", "print-key-1", "moonraker", JobPhase.PROCESS, MachineState.IDLE, {})
        self.assertFalse(PrinterBridge().plan(job, CellState.READY, status).allowed)

    def test_paused_print_stats_maps_to_holding(self):
        MoonrakerFixtureHandler.print_stats_response_override = json.dumps(
            {"status": {"print_stats": {"state": "paused"}}}
        ).encode("utf-8")
        status = MoonrakerProbe().fetch(f"http://127.0.0.1:{self.server.server_port}")
        self.assertEqual(status.state, MachineState.HOLDING)

    def test_print_error_state_overrides_a_bare_klippy_ready_reading(self):
        MoonrakerFixtureHandler.print_stats_response_override = json.dumps(
            {"status": {"print_stats": {"state": "error"}}}
        ).encode("utf-8")
        status = MoonrakerProbe().fetch(f"http://127.0.0.1:{self.server.server_port}")
        self.assertEqual(status.state, MachineState.FAULT)

    def test_complete_and_cancelled_print_stats_do_not_block_the_free_printer(self):
        for state in ("complete", "cancelled"):
            with self.subTest(state=state):
                MoonrakerFixtureHandler.print_stats_response_override = json.dumps(
                    {"status": {"print_stats": {"state": state}}}
                ).encode("utf-8")
                status = MoonrakerProbe().fetch(f"http://127.0.0.1:{self.server.server_port}")
                self.assertEqual(status.state, MachineState.IDLE)

    def test_not_ready_klippy_state_skips_the_print_stats_request_entirely(self):
        # There is no point asking a printer that is not even connected
        # about its print job state.
        MoonrakerFixtureHandler.info_response_override = json.dumps({"state": "shutdown"}).encode("utf-8")
        status = MoonrakerProbe().fetch(f"http://127.0.0.1:{self.server.server_port}")
        self.assertEqual(status.state, MachineState.FAULT)
        self.assertNotIn("/printer/objects/query?print_stats=state", MoonrakerFixtureHandler.requested_paths)

    def test_unparseable_print_stats_response_fails_closed(self):
        MoonrakerFixtureHandler.print_stats_response_override = json.dumps({"status": {}}).encode("utf-8")
        status = MoonrakerProbe().fetch(f"http://127.0.0.1:{self.server.server_port}")
        self.assertEqual(status.state, MachineState.OFFLINE)
        self.assertIn("print_stats", status.message)

    def test_non_http_endpoint_is_rejected_without_a_request(self):
        status = MoonrakerProbe().fetch("file:///printer.cfg")
        self.assertEqual(status.state, MachineState.OFFLINE)
        self.assertIn("http(s)", status.message)

    def test_non_string_endpoint_is_rejected_without_crashing(self):
        status = MoonrakerProbe().fetch(None)  # type: ignore[arg-type]
        self.assertEqual(status.state, MachineState.OFFLINE)
        self.assertIn("http(s)", status.message)

    def test_oversized_moonraker_response_fails_closed_before_json_parsing(self):
        MoonrakerFixtureHandler.info_response_override = b"{" + b"x" * (64 * 1024 + 1)
        status = MoonrakerProbe().fetch(f"http://127.0.0.1:{self.server.server_port}")
        self.assertEqual(status.state, MachineState.OFFLINE)
        self.assertIn("64 KiB", status.message)


if __name__ == "__main__":
    unittest.main()
