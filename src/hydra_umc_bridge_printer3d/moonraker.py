# =============================================================================
# HYDRA-UMC-BRIDGE-PRINTER3D - Moonraker readiness and job gate
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Read native printer readiness without controlling firmware or heaters."""

from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.error import URLError
from urllib.request import urlopen

from hydra_umc_sdk.bridge_contract import BridgeJob, CellState, GateDecision, MachineState, evaluate_job


@dataclass(frozen=True)
class PrinterStatus:
    state: MachineState
    message: str


class MoonrakerProbe:
    """Small stdlib probe for Moonraker's documented `/printer/info` endpoint."""

    @staticmethod
    def parse_info(payload: dict[str, object]) -> PrinterStatus:
        result = payload.get("result", payload)
        if not isinstance(result, dict):
            return PrinterStatus(MachineState.OFFLINE, "Moonraker response is not an object")
        state = str(result.get("state", "")).lower()
        message = str(result.get("state_message", ""))
        if state == "ready":
            return PrinterStatus(MachineState.IDLE, message or "printer ready")
        if state in {"startup", "shutdown", "error"}:
            return PrinterStatus(MachineState.FAULT, message or f"printer state {state}")
        return PrinterStatus(MachineState.OFFLINE, message or f"unknown printer state {state or 'missing'}")

    def fetch(self, base_url: str, timeout_seconds: float = 2.0) -> PrinterStatus:
        # parse_info() above already fails safe (OFFLINE) for a malformed
        # or unexpected-shape response - this was the one gap in that same
        # story: a real network failure (Moonraker unreachable, DNS error,
        # timeout) or a non-JSON response raised an unhandled exception
        # instead of the same safe OFFLINE fallback every other failure
        # mode here already gets. A printer that can't be reached is not
        # meaningfully different from one reporting an unknown state - both
        # mean "don't trust this printer as ready", not "crash the caller".
        try:
            with urlopen(f"{base_url.rstrip('/')}/printer/info", timeout=timeout_seconds) as response:  # nosec B310: configured local controller endpoint
                return self.parse_info(json.load(response))
        except (URLError, TimeoutError, OSError, json.JSONDecodeError) as error:
            return PrinterStatus(MachineState.OFFLINE, f"Moonraker unreachable: {error}")


class PrinterBridge:
    """Gate high-level auxiliary work around a native printer job."""

    def plan(self, job: BridgeJob, cell_state: CellState, printer: PrinterStatus) -> GateDecision:
        observed = BridgeJob(job.job_id, job.idempotency_key, job.source, job.phase, printer.state, job.parameters)
        return evaluate_job(observed, cell_state)
