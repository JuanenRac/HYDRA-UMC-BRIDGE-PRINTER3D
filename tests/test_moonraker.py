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


if __name__ == "__main__":
    unittest.main()
