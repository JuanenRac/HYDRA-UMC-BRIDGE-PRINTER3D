# =============================================================================
# HYDRA-UMC-BRIDGE-PRINTER3D - Moonraker readiness and job gate
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Read native printer readiness without controlling firmware or heaters."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import urlopen

from hydra_umc_sdk.bridge_contract import BridgeJob, CellState, GateDecision, MachineState, evaluate_job


_MAX_INFO_BYTES = 64 * 1024


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

    @staticmethod
    def parse_print_stats(payload: dict[str, object]) -> PrinterStatus | None:
        # Real, closed set of print_stats.state values, researched against
        # https://moonraker.readthedocs.io/en/latest/printer_objects/ :
        # standby/printing/paused/complete/error/cancelled. This is a real,
        # separate axis from klippy_state ("ready"/"startup"/"shutdown"/
        # "error") - Klipper itself stays klippy_state="ready" throughout an
        # entire print, so /printer/info alone cannot tell "firmware
        # connected" apart from "actively mid-print". Returning None means
        # "no override, defer to klippy_state" (standby/complete/cancelled
        # all mean the print head is free); RUNNING/HOLDING/FAULT are real
        # overrides that must win over a bare klippy_state=ready reading.
        status = payload.get("status", payload)
        if not isinstance(status, dict):
            return PrinterStatus(MachineState.OFFLINE, "Moonraker objects/query response is not an object")
        print_stats = status.get("print_stats")
        if not isinstance(print_stats, dict):
            return PrinterStatus(MachineState.OFFLINE, "Moonraker objects/query response is missing print_stats")
        state = str(print_stats.get("state", "")).lower()
        if state == "printing":
            return PrinterStatus(MachineState.RUNNING, "a print is actively in progress")
        if state == "paused":
            return PrinterStatus(MachineState.HOLDING, "the current print job is paused")
        if state == "error":
            return PrinterStatus(MachineState.FAULT, "the last print job exited with an error")
        if state in {"standby", "complete", "cancelled"}:
            return None
        return PrinterStatus(MachineState.OFFLINE, f"unknown print_stats state {state or 'missing'}")

    def fetch(self, base_url: str, timeout_seconds: float = 2.0) -> PrinterStatus:
        # parse_info() above already fails safe (OFFLINE) for a malformed
        # or unexpected-shape response - this was the one gap in that same
        # story: a real network failure (Moonraker unreachable, DNS error,
        # timeout) or a non-JSON response raised an unhandled exception
        # instead of the same safe OFFLINE fallback every other failure
        # mode here already gets. A printer that can't be reached is not
        # meaningfully different from one reporting an unknown state - both
        # mean "don't trust this printer as ready", not "crash the caller".
        if not isinstance(base_url, str):
            return PrinterStatus(
                MachineState.OFFLINE,
                "Moonraker endpoint must be an absolute http(s) URL",
            )

        normalized_base_url = base_url.strip()
        try:
            parsed = urlparse(normalized_base_url)
        except ValueError as error:
            return PrinterStatus(MachineState.OFFLINE, f"Moonraker endpoint is invalid: {error}")

        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return PrinterStatus(
                MachineState.OFFLINE,
                "Moonraker endpoint must be an absolute http(s) URL",
            )

        info_status = self._get(f"{normalized_base_url.rstrip('/')}/printer/info", timeout_seconds, self.parse_info)
        if info_status.state != MachineState.IDLE:
            # klippy is not ready (startup/shutdown/error) or unreachable -
            # that already fails closed, so there is no point asking a
            # printer that is not even connected about its print_stats.
            return info_status

        # klippy_state=ready alone does not mean the print head is free -
        # see parse_print_stats()'s own comment. Query the real, separate
        # print_stats object before trusting IDLE.
        print_status = self._get(
            f"{normalized_base_url.rstrip('/')}/printer/objects/query?print_stats=state",
            timeout_seconds,
            self.parse_print_stats,
        )
        if print_status is None:
            # standby/complete/cancelled - the print head is genuinely
            # free, so the original klippy_state=ready reading stands.
            return info_status
        # printing/paused/error is a real override that must win over a
        # bare klippy_state=ready reading; a transport/parse failure here
        # also comes back as a PrinterStatus(OFFLINE, ...) from _get()'s
        # own except clause, which correctly fails closed the same way -
        # a printer whose real print state cannot be confirmed is not
        # meaningfully safer to trust than one reporting an unknown state.
        return print_status

    @staticmethod
    def _get(
        endpoint: str,
        timeout_seconds: float,
        parser: Callable[[dict[str, object]], "PrinterStatus | None"],
    ) -> "PrinterStatus | None":
        # Shared transport for both /printer/info and /printer/objects/query -
        # the same real failure modes (unreachable, malformed, oversized)
        # apply to either endpoint, so both fail the same safe way.
        try:
            with urlopen(endpoint, timeout=timeout_seconds) as response:  # nosec B310: configured controller endpoint, restricted to HTTP(S) above
                payload = response.read(_MAX_INFO_BYTES + 1)
            if len(payload) > _MAX_INFO_BYTES:
                return PrinterStatus(MachineState.OFFLINE, "Moonraker response exceeds the 64 KiB readiness limit")
            parsed_payload = json.loads(payload.decode("utf-8"))
            return parser(parsed_payload)
        except (URLError, TimeoutError, OSError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
            return PrinterStatus(MachineState.OFFLINE, f"Moonraker unreachable: {error}")


class PrinterBridge:
    """Gate high-level auxiliary work around a native printer job."""

    def plan(self, job: BridgeJob, cell_state: CellState, printer: PrinterStatus) -> GateDecision:
        observed = BridgeJob(job.job_id, job.idempotency_key, job.source, job.phase, printer.state, job.parameters)
        return evaluate_job(observed, cell_state)
