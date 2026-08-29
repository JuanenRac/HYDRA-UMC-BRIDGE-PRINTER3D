<!-- =============================================================================
HYDRA-UMC-BRIDGE-PRINTER3D - Change history
Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
GPL-3.0-or-later - see LICENSE
============================================================================= -->

# Changelog

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
