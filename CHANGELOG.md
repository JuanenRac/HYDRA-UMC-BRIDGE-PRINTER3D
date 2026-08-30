<!-- =============================================================================
HYDRA-UMC-BRIDGE-PRINTER3D - Change history
Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
GPL-3.0-or-later - see LICENSE
============================================================================= -->

# Changelog

## Unreleased

- Bound the read-only Moonraker readiness response to 64 KiB before JSON
  decoding. Oversized responses now fail closed as `OFFLINE` instead of
  consuming an unbounded response body.

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
