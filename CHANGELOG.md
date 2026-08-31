<!-- =============================================================================
HYDRA-UMC-BRIDGE-PRINTER3D - Change history
Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
GPL-3.0-or-later - see LICENSE
============================================================================= -->

# Changelog

## [0.1.0] - Real MQTT transport over the real broker

- **`mqtt_transport.py`** (new) - reaches this bridge's already-real logic
  (`MoonrakerJobControl.start_job`/`pause_job`/`resume_job`/`cancel_job`,
  `PrinterBridge.plan`) over `HYDRA-UMC-MQTT-BROKER`, per the ecosystem's
  own "MQTT via the real broker, real commands included" decision -
  `hydra/bridges/printer3d/cmd/{status,job,start,pause,resume,cancel}` in,
  `hydra/bridges/printer3d/state` (retained) and `.../cmd/<verb>/result`
  out. `PrinterMqttBridge.handle_message()` is a pure(ish) topic
  dispatcher over a Moonraker base URL - fully testable against the same
  local `ThreadingHTTPServer` Moonraker fixture `test_moonraker.py`
  already uses, no real broker required. Adds no new physical authority:
  every command sent is one `moonraker.py` already implemented, and the
  same boundary (never streams raw G-code, never touches firmware/
  heaters/motion directly) applies unchanged. `run_forever()` is the thin
  real-I/O glue, lazily importing the new optional `paho-mqtt` dependency.
  16 new tests.

## [0.0.9] - Real, SDK-gated job commands (pre-real: connected, not simulated)

- **`moonraker.py`** - added `MoonrakerJobControl`, this bridge's first real
  write capability: `start_job()`/`pause_job()`/`resume_job()`/`cancel_job()`
  send real `POST` requests to Moonraker's own documented REST API
  (`/printer/print/start|pause|resume|cancel`,
  [moonraker.readthedocs.io/en/latest/external_api/printer](https://moonraker.readthedocs.io/en/latest/external_api/printer/)).
  This is a deliberate, explicit expansion of this bridge's own boundary (see
  the updated manifest `notes`) - but it never bypasses this ecosystem's
  safety gate: `start_job()` routes through the exact same `evaluate_job()`
  decision every productive dispatch in this ecosystem uses (`PrinterBridge.
  plan()`) before a single byte reaches Moonraker; `pause_job()`/`cancel_job()`
  are always allowed, matching the same de-escalation reasoning already
  applied to `ABORT`/`HOLD_POSITION` elsewhere; `resume_job()` uses a
  standalone gate requiring a genuinely `HOLDING` printer (not the generic
  IDLE-based gate, which is backwards for resuming a paused job - same
  reasoning already applied to DROIDS's `stand_request()`/`sit_request()`).
  `start_job()` also rejects a path-traversal or empty filename before any
  network call. This still never streams raw G-code, touches firmware, or
  claims heater/motion authority - Moonraker/Klipper keep that, unchanged.
- 9 new regression tests against the same real fixture HTTP server pattern,
  now also serving real `POST` responses - 35/35 tests passing.

## [0.0.8] - Real print_stats confirmation, not just klippy_state

- Bound the read-only Moonraker readiness response to 64 KiB before JSON
  decoding. Oversized responses now fail closed as `OFFLINE` instead of
  consuming an unbounded response body.
- **`moonraker.py`** - `MoonrakerProbe` now also queries Moonraker's real,
  separate `print_stats` object
  (`/printer/objects/query?print_stats=state`, researched against
  [moonraker.readthedocs.io/en/latest/printer_objects](https://moonraker.readthedocs.io/en/latest/printer_objects/))
  before trusting a bare `klippy_state=ready` reading as `IDLE`. Klipper's
  own `klippy_state` stays `"ready"` throughout an entire print - it never
  distinguished "firmware connected" from "actively mid-print", a real gap
  that could let a new productive job be evaluated as safe to dispatch
  onto a printer that is genuinely busy. `print_stats.state` is a real,
  closed set (`standby`/`printing`/`paused`/`complete`/`error`/
  `cancelled`): `printing` now maps to `RUNNING`, `paused` to `HOLDING`,
  `error` to `FAULT`; `standby`/`complete`/`cancelled` defer to the
  original `klippy_state` reading. A failure to confirm `print_stats`
  itself fails closed to `OFFLINE`, matching this probe's own established
  reasoning that an unconfirmed printer is not safer to trust than one
  reporting an unknown state.
- 9 new/updated regression tests against a real path-aware fixture HTTP
  server - 25/25 tests passing.

## [0.0.7] - 2026-08-30

- Added `docs/BRIDGE_GUIDE.md`, complementing the slicer and profile-boundary
  documents with software compatibility, scripts and hardware acceptance flow.
- Removed the duplicated terminal BUILD & RUN section from all seven README files.
- Added an offline CLI that compares one local artifact with one local profile
  JSON and preserves `execution_authorized: false` in its output.
- Added CLI contract coverage; the full suite now has seventeen tests.
- Synchronized package metadata, ecosystem manifest and all seven README files.

## [0.0.6] - 2026-08-30

- Added `PrintProfile` and `assess_artifact_profile()` for declared local
  artifact/profile compatibility evidence.
- Made the non-escalation rule executable: every assessment returns
  `execution_authorized: false`, including a compatible profile match.
- Added three deterministic tests for compatible, incompatible and invalid
  profile evidence; the full suite now has sixteen tests.
- Synchronized package metadata, ecosystem manifest and all seven README files.

## [0.0.5] - 2026-08-30

- Added a safe, local artifact-inspection lane for ordinary FDM G-code from
  OrcaSlicer, Ultimaker Cura, PrusaSlicer, Bambu Studio and other slicers.
- Added read-only recognition and SHA-256 evidence for `.gcode.3mf`, generic
  `.3mf`, and opaque resin-slice formats used by Lychee-compatible workflows.
- Explicitly kept all slicer and printer control out of scope: no application
  launch, profile change, package extraction, G-code parsing/execution, upload
  or print start is performed.
- Added six deterministic artifact tests and compile validation for `tools/`;
  the full local suite now has thirteen tests.
- Synchronized package metadata, ecosystem manifest and all seven README files.

## [0.0.4] - 2026-08-29

- Synchronized the English README and all six translated README files with the
  released readiness-probe scope, current version and seven-test coverage.
- Successful incremental build: synchronized package metadata and
  `hydra-umc.project.json`.

## [0.0.3] - 2026-08-29

- Normalized surrounding whitespace in a configured Moonraker base URL before
  opening the documented readiness request.
- Made a non-string endpoint value fail safe as `OFFLINE` instead of allowing
  a configuration-type error to escape the probe.
- Successful incremental build: synchronized package metadata and
  `hydra-umc.project.json`.

## [0.0.2] - 2026-08-29

- Added a deterministic local HTTP integration test for Moonraker's read-only
  `GET /printer/info` readiness endpoint; it verifies the endpoint path and
  the `ready` state mapping without contacting a printer.
- Rejected non-HTTP(S) controller URLs before any request is opened, keeping a
  malformed or accidental local-file endpoint fail-safe as `OFFLINE`.
- Successful incremental build: synchronized package metadata and
  `hydra-umc.project.json`.

## [0.0.1]

- Added Moonraker readiness parser, SDK safety gate and local tests.
- Added non-mutating build-test scripts and CI SDK checkout.
- Standardized README (all 7 languages) and project banner to match the
  rest of the ecosystem's established-project structure.
- Fixed a real gap: `MoonrakerProbe.fetch()`'s own `parse_info()` already
  failed safe (`OFFLINE`) for a malformed or unexpected response shape,
  but the network call around it had no equivalent handling - Moonraker
  being unreachable, a DNS/timeout error, or a non-JSON response raised
  an unhandled exception instead of that same safe fallback. Now wrapped
  and mapped to the same `OFFLINE` state - verified with a new test
  against a real closed port (no mocking).
- Promoted to `established`: manifest, docs, build-test/CI and this
  project's own real functional gap (above) all verified locally.
