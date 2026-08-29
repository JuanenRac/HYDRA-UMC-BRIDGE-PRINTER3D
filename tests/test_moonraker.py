# =============================================================================
# HYDRA-UMC-BRIDGE-PRINTER3D - Moonraker bridge tests
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
import unittest

from hydra_umc_sdk.bridge_contract import BridgeJob, CellState, JobPhase, MachineState
from hydra_umc_bridge_printer3d import MoonrakerProbe, PrinterBridge


class MoonrakerTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
