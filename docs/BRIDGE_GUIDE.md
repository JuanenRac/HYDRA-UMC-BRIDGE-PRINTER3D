<!-- =============================================================================
HYDRA-UMC-BRIDGE-PRINTER3D - Technical bridge guide
Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
GPL-3.0-or-later - see LICENSE
============================================================================= -->

# HYDRA-UMC-BRIDGE-PRINTER3D Technical Guide

## Scope and operating model

The bridge separates three read-only lanes: Moonraker readiness (`/printer/info`), local slicer-artifact evidence, and declared artifact/profile compatibility. `MoonrakerProbe` maps only literal `ready` to idle and bounds an HTTP readiness payload to 64 KiB before JSON parsing; an oversized or malformed response is `OFFLINE`. `inspect_artifact()` fingerprints G-code, 3MF and resin-slice candidates without unpacking or parsing commands. `assess_artifact_profile()` can confirm metadata compatibility but always returns `execution_authorized: false`.

No module starts a slicer, modifies a profile, sends G-code, uploads a file, controls heaters or starts a print.

## Compatible software

FDM artifact evidence supports ordinary G-code from OrcaSlicer, Ultimaker Cura, PrusaSlicer, Bambu Studio and other slicers. `.gcode.3mf` and `.3mf` are identified only. Lychee-compatible resin outputs such as `.ctb` and `.goo` are opaque evidence, not decoded printer jobs. Moonraker/Klipper is the only readiness API currently represented, and it is read-only.

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
