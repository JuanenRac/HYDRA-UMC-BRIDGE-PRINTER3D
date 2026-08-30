<!-- =============================================================================
HYDRA-UMC-BRIDGE-PRINTER3D - Technical bridge guide
Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
GPL-3.0-or-later - see LICENSE
============================================================================= -->

# HYDRA-UMC-BRIDGE-PRINTER3D Technical Guide

## Scope and operating model

The bridge separates four lanes: Moonraker readiness (`/printer/info` and `/printer/objects/query?print_stats=state`, both read-only), real SDK-gated job control, local slicer-artifact evidence, and declared artifact/profile compatibility. `MoonrakerProbe` maps only literal `ready` to idle and bounds each HTTP readiness payload to 64 KiB before JSON parsing; an oversized or malformed response is `OFFLINE`. A bare `klippy_state=ready` reading is not trusted as idle on its own - Klipper's own `klippy_state` stays `"ready"` throughout an entire print, so the probe also confirms the real, separate `print_stats.state` object (researched against moonraker.readthedocs.io/en/latest/printer_objects) before reporting `IDLE`: `printing` maps to `RUNNING`, `paused` to `HOLDING`, `error` to `FAULT`, and `standby`/`complete`/`cancelled` defer to the original reading. `inspect_artifact()` fingerprints G-code, 3MF and resin-slice candidates without unpacking or parsing commands. `assess_artifact_profile()` can confirm metadata compatibility but always returns `execution_authorized: false`.

`MoonrakerJobControl` is this bridge's only write path: `start_job()`/`pause_job()`/`resume_job()`/`cancel_job()` send real `POST` requests to Moonraker's own `/printer/print/start|pause|resume|cancel` endpoints, gated the same way every other productive dispatch in this ecosystem is (`start_job()` through `evaluate_job()`; `pause_job()`/`cancel_job()` always allowed like `ABORT`; `resume_job()` through a standalone `HOLDING`-only gate). It only ever references an already-uploaded, already-sliced file by name - no module here uploads a file, streams raw G-code, modifies a profile, or controls heaters directly.

## Compatible software

FDM artifact evidence supports ordinary G-code from OrcaSlicer, Ultimaker Cura, PrusaSlicer, Bambu Studio and other slicers. `.gcode.3mf` and `.3mf` are identified only. Lychee-compatible resin outputs such as `.ctb` and `.goo` are opaque evidence, not decoded printer jobs. Moonraker/Klipper is the only printer API currently represented; job control is real, readiness is real, everything else stays read-only.

## Scripts and verification

| Script | Purpose | Changes version/CHANGELOG? |
|---|---|---|
| `build-test.bat` / `build-test.sh` | Compile and run offline adapter tests | No |
| `build.bat` / `build.sh` | Validate, then increment version and CHANGELOG | Yes, after success |
| `tools/inspect_print_artifact.py` | Print JSON evidence for one local artifact | No |
| `tools/assess_print_profile.py` | Compare local profile JSON and artifact; never authorizes execution | No |

## Adding a new script

Use the standard header, declared mutation behavior, numbered console steps and `pause` in `.bat`. Keep reusable code in `src/` or `tools/`, compile it in `tools/build_test.py`, add a deterministic test and document it. A new script must not make artifact detection become a print command.

## Hardware acceptance gate

Use real exported jobs, identify a concrete printer/controller/profile, validate material/nozzle/volume constraints, read authenticated Moonraker state, verify independent thermal/machine safety, then run a supervised HIL plan. Native firmware retains all print authority.
