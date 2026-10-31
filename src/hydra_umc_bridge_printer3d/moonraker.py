# =============================================================================
# HYDRA-UMC-BRIDGE-PRINTER3D - Moonraker readiness and job gate
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Read native printer readiness without controlling firmware or heaters."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from hydra_umc_sdk.bridge_contract import BridgeJob, CellState, GateDecision, JobPhase, MachineState, evaluate_job


_MAX_INFO_BYTES = 64 * 1024

# Moonraker answers 401 to a client it does not trust when [authorization] is
# configured; an API key goes in this header (the environment variable below is
# where a service supplies it, so that it never has to sit in a command line).
API_KEY_HEADER = "X-Api-Key"
API_KEY_ENV = "MOONRAKER_API_KEY"

# What Moonraker itself accepts as a printable G-code file.
_GCODE_SUFFIXES = {".gcode", ".gco", ".g", ".gc"}


def api_key_from_env(env: "dict[str, str] | None" = None) -> str | None:
    """The Moonraker API key of this service's environment, or None."""
    value = (os.environ if env is None else env).get(API_KEY_ENV, "").strip()
    return value or None


def _normalize_base_url(base_url: object) -> tuple[str | None, str]:
    """(normalized URL, "") for a usable Moonraker base URL, else (None, why)."""
    if not isinstance(base_url, str):
        return None, "Moonraker endpoint must be an absolute http(s) URL"
    normalized = base_url.strip()
    try:
        parsed = urlparse(normalized)
    except ValueError as error:
        return None, f"Moonraker endpoint is invalid: {error}"
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None, "Moonraker endpoint must be an absolute http(s) URL"
    if parsed.query or parsed.fragment or "?" in normalized or "#" in normalized:
        return None, "Moonraker endpoint must not carry a query or a fragment"
    return normalized.rstrip("/"), ""


def validate_gcode_filename(filename: object) -> str:
    """"" when `filename` is a safe path below Moonraker's gcodes root, else why not.

    The check is on path components, not on substrings: `part..v2.gcode` is a fine
    name, `a/../b.gcode` is not. Backslashes, control characters and NUL are refused
    (they mean something else on another host), and so is a name that is not a
    G-code file at all."""
    if not isinstance(filename, str) or not filename.strip():
        return "a non-empty gcode filename is required"
    if filename != filename.strip() or filename.startswith(("/", "~")):
        return "filename must not escape Moonraker's gcodes root"
    if "\\" in filename or any(ord(char) < 32 or ord(char) == 127 for char in filename):
        return "filename must not contain backslashes or control characters"
    path = PurePosixPath(filename)
    if any(part in {"", ".", ".."} for part in filename.split("/")):
        return "filename must not escape Moonraker's gcodes root"
    if path.suffix.lower() not in _GCODE_SUFFIXES:
        return "filename must be a G-code file (.gcode, .gco, .g or .gc)"
    return ""


@dataclass(frozen=True)
class PrinterStatus:
    state: MachineState
    message: str


class MoonrakerProbe:
    """Small stdlib probe for Moonraker's documented `/printer/info` endpoint."""

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key

    @staticmethod
    def parse_info(payload: dict[str, object]) -> PrinterStatus:
        # valid JSON whose root is not an object (a bare array,
        # string, number, bool or null) is a real possibility from any
        # HTTP endpoint - a misconfigured proxy, an unrelated service on
        # the same host/port - and payload.get(...) below would otherwise
        # raise AttributeError on it, an exception _get()'s own except
        # clause never catches (it only catches transport/JSON-decode
        # errors, not "valid JSON, wrong shape"), crashing this call
        # instead of failing closed like every other malformed-response
        # case here already does.
        if not isinstance(payload, dict):
            return PrinterStatus(MachineState.OFFLINE, "Moonraker response is not an object")
        result = payload.get("result", payload)
        if not isinstance(result, dict):
            return PrinterStatus(MachineState.OFFLINE, "Moonraker response is not an object")
        state = str(result.get("state", "")).lower()
        message = str(result.get("state_message", ""))
        if state == "ready":
            return PrinterStatus(MachineState.IDLE, message or "printer ready")
        if state == "startup":
            # normal and brief after a FIRMWARE_RESTART: not a fault, just not ready yet (the gate refuses either way)
            return PrinterStatus(MachineState.OFFLINE, message or "printer is starting up")
        if state in {"shutdown", "error"}:
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
        # a real Moonraker `objects/query` response wraps its own
        # `status` object inside a `result` envelope
        # (`{"result": {"status": {"print_stats": {...}}}}`,
        # moonraker.readthedocs.io/en/latest/external_api/introduction/) -
        # this used to look for `status` directly on the OUTER payload
        # (confusing the JSON-RPC-style envelope with the object it
        # contains, unlike parse_info() just above, which already unwraps
        # `result` correctly), so it silently fell through to treating the
        # whole envelope as `status`, found no `print_stats` inside IT, and
        # reported a perfectly healthy standby printer as OFFLINE with
        # "missing print_stats". Unwrap `result` first, exactly like
        # parse_info() already does, before reaching for `status`.
        #
        # same real gap as parse_info above - a non-object JSON
        # root must fail closed here too, before payload.get(...) below
        # can raise AttributeError on it.
        if not isinstance(payload, dict):
            return PrinterStatus(MachineState.OFFLINE, "Moonraker objects/query response is not an object")
        result = payload.get("result", payload)
        if not isinstance(result, dict):
            return PrinterStatus(MachineState.OFFLINE, "Moonraker objects/query response is not an object")
        status = result.get("status", result)
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
        normalized_base_url, problem = _normalize_base_url(base_url)
        if normalized_base_url is None:
            return PrinterStatus(MachineState.OFFLINE, problem)

        info_status = self._get(f"{normalized_base_url}/printer/info", timeout_seconds, self.parse_info, self._api_key)
        if info_status.state != MachineState.IDLE:  # type: ignore[union-attr]
            # klippy is not ready (startup/shutdown/error) or unreachable -
            # that already fails closed, so there is no point asking a
            # printer that is not even connected about its print_stats.
            return info_status  # type: ignore[return-value]

        # klippy_state=ready alone does not mean the print head is free -
        # see parse_print_stats()'s own comment. Query the real, separate
        # print_stats object before trusting IDLE.
        print_status = self._get(
            f"{normalized_base_url}/printer/objects/query?print_stats=state",
            timeout_seconds,
            self.parse_print_stats,
            self._api_key,
        )
        if print_status is None:
            # standby/complete/cancelled - the print head is genuinely
            # free, so the original klippy_state=ready reading stands.
            return info_status  # type: ignore[return-value]
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
        api_key: str | None = None,
    ) -> "PrinterStatus | None":
        # Shared transport for both /printer/info and /printer/objects/query -
        # the same real failure modes (unreachable, malformed, oversized)
        # apply to either endpoint, so both fail the same safe way.
        request = Request(endpoint, headers={API_KEY_HEADER: api_key} if api_key else {})  # nosec B310: configured controller endpoint, restricted to HTTP(S) above
        try:
            with urlopen(request, timeout=timeout_seconds) as response:  # nosec B310
                payload = response.read(_MAX_INFO_BYTES + 1)
            if len(payload) > _MAX_INFO_BYTES:
                return PrinterStatus(MachineState.OFFLINE, "Moonraker response exceeds the 64 KiB readiness limit")
            parsed_payload = json.loads(payload.decode("utf-8"))
            return parser(parsed_payload)
        except HTTPError as error:
            error.close()
            if error.code in (401, 403):
                return PrinterStatus(MachineState.OFFLINE, f"Moonraker refused the credentials (HTTP {error.code}): set {API_KEY_ENV}")
            return PrinterStatus(MachineState.OFFLINE, f"Moonraker unreachable: {error}")
        except (URLError, TimeoutError, OSError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as error:
            return PrinterStatus(MachineState.OFFLINE, f"Moonraker unreachable: {error}")


class PrinterBridge:
    """Gate high-level auxiliary work around a native printer job."""

    def plan(self, job: BridgeJob, cell_state: CellState, printer: PrinterStatus) -> GateDecision:
        observed = BridgeJob(job.job_id, job.idempotency_key, job.source, job.phase, printer.state, job.parameters)
        return evaluate_job(observed, cell_state, printer.state)


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

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key

    def start_job(
        self,
        job: BridgeJob,
        cell_state: CellState,
        printer: PrinterStatus,
        base_url: str,
        filename: str,
        timeout_seconds: float = 5.0,
    ) -> JobCommandResult:
        # evaluate_job - the shared gate PrinterBridge.plan
        # calls - deliberately always allows JobPhase.ABORT, "so that an
        # external integration can request a controlled stop" (see that
        # function's own docstring in HYDRA-UMC-SDK). That rule is correct
        # for a STOP-class action (this bridge's own cancel_job()), but
        # start_job() is a START-class action - reused verbatim, it meant
        # a BridgeJob carrying phase=ABORT (even one built from a real
        # SAFE_STOP/FAULT machine state) sailed straight through the gate
        # as allowed=True and this function then actually POSTed
        # /printer/print/start, starting a NEW print in response to what
        # was labeled a request to STOP. Only JobPhase.PROCESS is a real
        # "begin printing" request; every other phase (ABORT included) is
        # refused here before the shared gate is ever consulted, since the
        # gate's own ABORT-always-allowed rule was never meant to reach a
        # start action at all.
        if job.phase is not JobPhase.PROCESS:
            return JobCommandResult(False, False, f"start_job only accepts phase PROCESS, got {job.phase.value}")
        decision = PrinterBridge().plan(job, cell_state, printer)
        if not decision.allowed:
            return JobCommandResult(False, False, decision.reason)
        problem = validate_gcode_filename(filename)
        if problem:
            return JobCommandResult(True, False, problem)
        # the file must really be on the printer: a name that exists nowhere is refused here, not left to Klipper
        unknown = self._file_problem(base_url, filename, timeout_seconds)
        if unknown is not None:
            return JobCommandResult(True, False, unknown)
        return self._post(base_url, "/printer/print/start", timeout_seconds, {"filename": filename}, self._api_key)

    def pause_job(self, base_url: str, timeout_seconds: float = 5.0) -> JobCommandResult:
        # Always allowed, same de-escalation reasoning as ABORT/HOLD_POSITION
        # elsewhere in this ecosystem - an operator must always be able to
        # pause an active job; pausing only ever reduces risk.
        return self._post(base_url, "/printer/print/pause", timeout_seconds, None, self._api_key)

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
        return self._post(base_url, "/printer/print/resume", timeout_seconds, None, self._api_key)

    def cancel_job(self, base_url: str, timeout_seconds: float = 5.0) -> JobCommandResult:
        # Always allowed, same reasoning as ABORT everywhere else in this
        # ecosystem - a controlled stop must never be gated on machine state.
        return self._post(base_url, "/printer/print/cancel", timeout_seconds, None, self._api_key)

    def emergency_stop(self, base_url: str, timeout_seconds: float = 5.0) -> JobCommandResult:
        # The hard stop (Klipper M112): heaters and motors off at once. Never gated and
        # never deduplicated - a stop must always get through. Klipper needs a
        # FIRMWARE_RESTART afterwards, which is a human decision this bridge never takes.
        return self._post(base_url, "/printer/emergency_stop", timeout_seconds, None, self._api_key)

    def _file_problem(self, base_url: str, filename: str, timeout_seconds: float) -> str | None:
        """None when Moonraker knows `filename`; otherwise why the start must not go ahead."""
        normalized_base_url, problem = _normalize_base_url(base_url)
        if normalized_base_url is None:
            return problem
        endpoint = f"{normalized_base_url}/server/files/metadata?{urlencode({'filename': filename})}"
        request = Request(endpoint, headers={API_KEY_HEADER: self._api_key} if self._api_key else {})  # nosec B310: configured controller endpoint, restricted to HTTP(S) above
        try:
            with urlopen(request, timeout=timeout_seconds) as response:  # nosec B310
                response.read(_MAX_INFO_BYTES + 1)
        except HTTPError as error:
            error.close()
            if error.code == 404:
                return f"Moonraker has no file {filename!r} to print"
            if error.code in (401, 403):
                return f"Moonraker refused the credentials (HTTP {error.code}): set {API_KEY_ENV}"
            return f"Moonraker could not check the file: HTTP {error.code}"
        except (URLError, TimeoutError, OSError, ValueError) as error:
            return f"Moonraker unreachable: {error}"
        return None

    @staticmethod
    def _post(
        base_url: str,
        path: str,
        timeout_seconds: float,
        params: dict[str, str] | None,
        api_key: str | None = None,
    ) -> JobCommandResult:
        normalized_base_url, problem = _normalize_base_url(base_url)
        if normalized_base_url is None:
            return JobCommandResult(True, False, problem)

        endpoint = f"{normalized_base_url}{path}"
        if params:
            endpoint = f"{endpoint}?{urlencode(params)}"
        headers = {API_KEY_HEADER: api_key} if api_key else {}
        request = Request(endpoint, method="POST", data=b"", headers=headers)  # nosec B310: configured controller endpoint, restricted to HTTP(S) above
        try:
            with urlopen(request, timeout=timeout_seconds) as response:  # nosec B310
                body = response.read(_MAX_INFO_BYTES + 1)
                status_code = response.status
        except HTTPError as error:
            error.close()
            if error.code in (401, 403):
                return JobCommandResult(True, False, f"Moonraker refused the credentials (HTTP {error.code}): set {API_KEY_ENV}", error.code)
            return JobCommandResult(True, False, f"Moonraker rejected the command: HTTP {error.code}", error.code)
        except (URLError, TimeoutError, OSError, ValueError) as error:
            return JobCommandResult(True, False, f"Moonraker unreachable: {error}")

        # an HTTP 200 alone is not Moonraker's own confirmation - a
        # misconfigured proxy, captive portal, or unrelated service on the
        # same host/port could all answer 200 with a body that never came
        # from Moonraker at all. Moonraker's own documented contract for
        # every one of these action endpoints is a JSON body of exactly
        # {"result": "ok"} (moonraker.readthedocs.io/en/latest/external_api/
        # printer/#print-management) - verify that contract instead of
        # trusting the bare status code, the same real-response-shape
        # discipline parse_info()/parse_print_stats() already apply to
        # Moonraker's read endpoints.
        if len(body) > _MAX_INFO_BYTES:
            return JobCommandResult(
                True, False, "Moonraker response exceeds the 64 KiB confirmation limit", status_code
            )
        try:
            parsed_body = json.loads(body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as error:
            return JobCommandResult(True, False, f"Moonraker response is not valid JSON: {error}", status_code)
        if not (isinstance(parsed_body, dict) and parsed_body.get("result") == "ok"):
            return JobCommandResult(
                True, False, "Moonraker did not confirm the command (unexpected response body)", status_code
            )
        return JobCommandResult(True, True, "Moonraker accepted the command", status_code)
