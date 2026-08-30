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
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

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


@dataclass(frozen=True)
class JobCommandResult:
    """A real command outcome - distinct from a plan-only GateDecision.

    `allowed=False` means the SDK gate rejected the command before any network
    call was made. `allowed=True, executed=False` means the gate accepted it but
    a local validation (e.g. an empty filename) still stopped it before the
    network call. `executed` only ever becomes True after Moonraker's own REST
    API returned success.
    """

    allowed: bool
    executed: bool
    reason: str
    http_status: int | None = None


class MoonrakerJobControl:
    """Send fail-closed, SDK-gated real print-job commands to Moonraker.

    This is a genuine change from the rest of this module (read-only readiness
    only) - it can now make Moonraker actually start/pause/resume/cancel a job.
    It still never bypasses this ecosystem's own safety boundary: every command
    that starts new productive work is gated through the exact same
    evaluate_job()-based decision every other bridge in this ecosystem uses
    before a single byte reaches Moonraker (see PrinterBridge.plan() above), and
    it only ever asks Moonraker's own already-safe REST API to start/pause/
    resume/cancel an already-sliced, already-verified gcode file that is already
    sitting on the printer's own filesystem - it never streams raw G-code and
    never touches firmware, heaters or motion directly. Moonraker/Klipper keep
    all real-time thermal and motion authority, exactly as this bridge's own
    manifest has always said.
    """

    def start_job(
        self,
        job: BridgeJob,
        cell_state: CellState,
        printer: PrinterStatus,
        base_url: str,
        filename: str,
        timeout_seconds: float = 5.0,
    ) -> JobCommandResult:
        # Starting a job is exactly a PROCESS-phase productive action - it needs
        # the same READY cell + IDLE machine gate every other productive
        # dispatch in this ecosystem needs, not a bespoke rule.
        decision = PrinterBridge().plan(job, cell_state, printer)
        if not decision.allowed:
            return JobCommandResult(False, False, decision.reason)
        if not isinstance(filename, str) or not filename.strip():
            return JobCommandResult(True, False, "a non-empty gcode filename is required")
        if ".." in filename or filename.startswith("/"):
            return JobCommandResult(True, False, "filename must not escape Moonraker's gcodes root")
        return self._post(base_url, "/printer/print/start", timeout_seconds, {"filename": filename})

    def pause_job(self, base_url: str, timeout_seconds: float = 5.0) -> JobCommandResult:
        # Always allowed, same de-escalation reasoning as ABORT/HOLD_POSITION
        # elsewhere in this ecosystem - an operator must always be able to
        # pause an active job; pausing only ever reduces risk.
        return self._post(base_url, "/printer/print/pause", timeout_seconds, None)

    def resume_job(
        self,
        cell_state: CellState,
        printer: PrinterStatus,
        base_url: str,
        timeout_seconds: float = 5.0,
    ) -> JobCommandResult:
        # Resume deliberately does NOT reuse evaluate_job() (built around
        # "productive work needs an IDLE machine") - that precondition is
        # backwards for this specific action: resume only makes sense from a
        # genuinely paused (HOLDING) printer, never an idle one. Same reasoning
        # already applied this session to DROIDS's standalone stand_request()/
        # sit_request() gates instead of forcing them through the generic
        # phase-based gate.
        if cell_state is not CellState.READY:
            return JobCommandResult(False, False, f"cell is {cell_state.value}, not READY")
        if printer.state is not MachineState.HOLDING:
            return JobCommandResult(
                False, False, f"printer is {printer.state.value}, not HOLDING (nothing to resume)"
            )
        return self._post(base_url, "/printer/print/resume", timeout_seconds, None)

    def cancel_job(self, base_url: str, timeout_seconds: float = 5.0) -> JobCommandResult:
        # Always allowed, same reasoning as ABORT everywhere else in this
        # ecosystem - a controlled stop must never be gated on machine state.
        return self._post(base_url, "/printer/print/cancel", timeout_seconds, None)

    @staticmethod
    def _post(
        base_url: str,
        path: str,
        timeout_seconds: float,
        params: dict[str, str] | None,
    ) -> JobCommandResult:
        if not isinstance(base_url, str):
            return JobCommandResult(True, False, "Moonraker endpoint must be an absolute http(s) URL")
        normalized_base_url = base_url.strip()
        try:
            parsed = urlparse(normalized_base_url)
        except ValueError as error:
            return JobCommandResult(True, False, f"Moonraker endpoint is invalid: {error}")
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return JobCommandResult(True, False, "Moonraker endpoint must be an absolute http(s) URL")

        endpoint = f"{normalized_base_url.rstrip('/')}{path}"
        if params:
            endpoint = f"{endpoint}?{urlencode(params)}"
        request = Request(endpoint, method="POST", data=b"")  # nosec B310: configured controller endpoint, restricted to HTTP(S) above
        try:
            with urlopen(request, timeout=timeout_seconds) as response:  # nosec B310
                response.read(_MAX_INFO_BYTES + 1)
                return JobCommandResult(True, True, "Moonraker accepted the command", response.status)
        except HTTPError as error:
            error.close()
            return JobCommandResult(True, False, f"Moonraker rejected the command: HTTP {error.code}", error.code)
        except (URLError, TimeoutError, OSError, ValueError) as error:
            return JobCommandResult(True, False, f"Moonraker unreachable: {error}")
