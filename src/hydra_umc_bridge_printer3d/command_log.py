# =============================================================================
# HYDRA-UMC-BRIDGE-PRINTER3D - src/hydra_umc_bridge_printer3d/command_log.py
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""One structured log line per command, and counters of what the bridge did with them.

Every command that reaches the bridge leaves one JSON line in the log `hydra_umc_bridge_printer3d.commands` with the verb, how it ended, how long it took
and the idempotency key of the job when the message carries one (cut to 64 characters; never the payload, never a file name). The same facts are counted
per verb and outcome and can be read with `cmd/metrics`, which answers on `metrics` (not retained). Outcomes: `ok` (answered and allowed), `refused`
(the gate or the global stop said no, or the message was malformed or too large), `failed` (allowed but Moonraker did not do it) and `error` (the
handling raised).
"""
from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any

COMMANDS_LOG = logging.getLogger("hydra_umc_bridge_printer3d.commands")
MAX_KEY_CHARS = 64


def outcome_of(result_payloads: list[str]) -> str:
    """How a command ended, read from the first answer that carries a verdict; an answer without one (a state, an event) is `ok`."""
    for text in result_payloads:
        try:
            body = json.loads(text)
        except (TypeError, ValueError):
            continue
        if isinstance(body, dict) and "allowed" in body:
            if body.get("allowed") is not True:
                return "refused"
            return "failed" if body.get("executed") is False else "ok"
    return "ok"


def key_of(payload: bytes) -> str | None:
    """The idempotency key a message carries (in `job` or at the top), or None; cut short, and None for anything that is not a JSON object."""
    try:
        body = json.loads(payload)
    except (TypeError, ValueError):
        return None
    if not isinstance(body, dict):
        return None
    job = body.get("job")
    key = job.get("idempotency_key") if isinstance(job, dict) else body.get("idempotency_key")
    return key[:MAX_KEY_CHARS] if isinstance(key, str) and key else None


class CommandStats:
    """Counters per verb and outcome; safe to call from the message thread and read from another."""

    def __init__(self, clock: Any = time.time) -> None:
        self._lock = threading.Lock()
        self._counts: dict[str, dict[str, int]] = {}
        self._since = clock()
        self._clock = clock

    def record(self, verb: str, outcome: str, duration_ms: float, key: str | None = None) -> None:
        with self._lock:
            per_verb = self._counts.setdefault(verb, {})
            per_verb[outcome] = per_verb.get(outcome, 0) + 1
        COMMANDS_LOG.info(json.dumps({"verb": verb, "outcome": outcome, "duration_ms": round(duration_ms, 1), "key": key}, sort_keys=True))

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            counts = {verb: dict(per) for verb, per in self._counts.items()}
        return {"since_s": int(self._since), "commands": counts}
