<!-- =============================================================================
HYDRA-UMC-BRIDGE-PRINTER3D - 3D-printer software bridge
Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
GPL-3.0-or-later - see LICENSE
============================================================================= -->

<p align="center">
  <img src="images/HYDRA_UMC_BANNER.svg" alt="HYDRA-UMC-BRIDGE-PRINTER3D banner" width="100%">
</p>

# 🖨️ HYDRA-UMC-BRIDGE-PRINTER3D

<p align="center">🇺🇸 <b>English</b> | <a href="README_spa.md">🇪🇸 Español</a> | <a href="README_fra.md">🇫🇷 Français</a> | <a href="README_ita.md">🇮🇹 Italiano</a> | <a href="README_deu.md">🇩🇪 Deutsch</a> | <a href="README_zho.md">🇨🇳 简体中文</a> | <a href="README_jpn.md">🇯🇵 日本語</a></p>

### 🌡️ Fail-Safe Coordination Bridge for Open 3D-Printing Software

<p align="left">
  <img src="https://img.shields.io/badge/Licencia-GPL%203.0-blue.svg" alt="GPL 3.0">
  <img src="https://img.shields.io/badge/Python-3.11%2B-3776AB.svg" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/Safety-Fails%20Closed-red.svg" alt="Fails Closed">
</p>

---

## 1. 🛠️ TECHNICAL OVERVIEW

**HYDRA-UMC-BRIDGE-PRINTER3D** is the high-level coordinator for open 3D-printing software (Moonraker/Klipper) and HYDRA-UMC robotic auxiliaries. It also recognizes local slicer artifacts read-only, and can now send real, SDK-gated job commands (start/pause/resume/cancel an already-uploaded, already-sliced file) through Moonraker's own REST API. Native printer firmware remains responsible for motion, heaters, thermal protection and machine interlocks at all times — this bridge never streams raw G-code and never replaces that authority; it only reads readiness, records artifact evidence, sends already-safe job-level commands and coordinates auxiliaries around it.

It belongs to the **External Automation Bridges** family: a set of sibling repositories (CNC, LASER, OPENPNP, PRINTER3D, ROS2) that all speak the same shared safety contract from `HYDRA-UMC-SDK`, so no bridge can invent its own definition of "safe to work".

### Key Features:
* ✅ **Real Moonraker readiness probe:** `moonraker.py`'s `MoonrakerProbe` consumes Moonraker's documented `/printer/info` endpoint with a small stdlib-only client (`urlopen` + `json`) — no extra dependency beyond the Python standard library. *(implemented, tested in `tests/test_moonraker.py`)*
* ✅ **Real fail-closed state parsing:** `parse_info()` maps only the literal `"ready"` to `MachineState.IDLE`; `startup`/`shutdown`/`error` map to `FAULT`, and anything else (including a malformed response) maps to `OFFLINE` — never to a state that would allow a robot to be planned around the printer. *(implemented)*
* ✅ **Real shared safety gate:** every observed job is re-evaluated through `evaluate_job()` from `HYDRA-UMC-SDK`'s `bridge_contract`, the same gate every sibling bridge and HYDRA-UMC-SERVER use. *(implemented)*
* ✅ **Slicer-agnostic artifact inspection:** `artifacts.py` identifies plain FDM G-code from OrcaSlicer, Ultimaker Cura, PrusaSlicer, Bambu Studio and other slicers from local evidence only; it also recognizes 3MF packages and opaque Lychee-compatible resin slices without unpacking, parsing commands, uploading or printing. *(implemented, tested in `tests/test_artifacts.py`)*
* ✅ **Profile-evidence boundary:** `profiles.py` can match an inspected artifact to a declared FDM or resin profile, but returns `execution_authorized=False` even on a match. *(implemented, tested in `tests/test_profiles.py`)*
* ✅ **Real, SDK-gated job commands:** `MoonrakerJobControl` sends real `POST` requests to Moonraker's documented `/printer/print/start|pause|resume|cancel` endpoints — `start_job()` is gated through the same `evaluate_job()` decision every productive dispatch in this ecosystem uses; `pause_job()`/`cancel_job()` are always allowed (same de-escalation reasoning as `ABORT`); `resume_job()` requires a genuinely `HOLDING` printer. It only ever starts an already-uploaded, already-sliced file by name — it never streams raw G-code. *(implemented, tested in `tests/test_moonraker.py`)*
* ✅ **Non-mutating build/test:** `build-test.bat`/`.sh` compile the response parser and safety gate without sending a real command, changing versions or touching a printer. *(implemented, see BUILD & RUN below)*
* 🔜 **Raw G-code streaming** — deliberately still deferred: sending arbitrary low-level commands (not a named, already-sliced job) needs a tested profile, authentication and physical safety review this bridge doesn't have yet. *(planned)*

---

## 2. 🔄 PRINTER COORDINATION FLOW

```mermaid
flowchart LR
    PRINTER["Moonraker / Klipper<br/>(/printer/info)"] --> BRIDGE["BRIDGE-PRINTER3D<br/>MoonrakerProbe.parse_info()"]
    BRIDGE -- "BridgeJob + observed MachineState" --> SDK["HYDRA-UMC-SDK<br/>evaluate_job()"]
    SDK -- GateDecision --> SERVER["HYDRA-UMC-SERVER"]
    SERVER -- "job / abort" --> CELL["Cell Safety"]
    SDK -- "allowed" --> JOBCTRL["MoonrakerJobControl<br/>start/pause/resume/cancel"]
    JOBCTRL -- "POST /printer/print/*" --> PRINTER
```

---

## 3. 🧱 ARCHITECTURE & DESIGN DECISIONS

* **Why only Moonraker's literal `"ready"` state maps to idle.** `parse_info()`'s state mapping is intentionally narrow: `ready` → `IDLE`, `startup`/`shutdown`/`error` → `FAULT` (fail closed), and every other or missing value → `OFFLINE`. There is no default-to-safe assumption for an unrecognized printer state.
* **Why parsing is a separate `@staticmethod` from the network fetch.** `MoonrakerProbe.parse_info()` takes a plain `dict` and is fully unit-testable without a network call or a running printer; `fetch()` is the thin, necessarily-network piece that calls it. The safety-relevant logic lives in the part that never needs a live printer to test.
* **Why the probe uses stdlib `urlopen`/`json` instead of a Moonraker client library.** Keeping the dependency surface to the Python standard library keeps the safety-relevant parsing minimal, auditable and free of a third-party client's own assumptions about retries, timeouts or error handling.
* **Why the bridge builds a new `BridgeJob` and delegates to the shared `evaluate_job()` instead of writing its own accept/reject logic.** All five External Automation Bridges (CNC, LASER, OPENPNP, PRINTER3D, ROS2) reuse the exact same `bridge_contract` from `HYDRA-UMC-SDK`, so "what counts as safe to start a job" cannot silently diverge between them.
* **Why job commands (start/pause/resume/cancel) are real but raw G-code streaming still isn't.** Moonraker's `/printer/print/*` endpoints only ever reference an already-uploaded, already-sliced file by name - the same safety envelope Moonraker/Klipper themselves already enforce on that file. Arbitrary raw G-code is a fundamentally different, much larger trust surface (it can contain anything) and still needs a tested profile, authentication and physical safety review this bridge doesn't have yet.
* **Why `resume_job()` doesn't reuse the generic `evaluate_job()` gate.** That gate is built around "productive work needs an IDLE machine" - backwards for resuming a paused job, which only makes sense from `HOLDING`. Same standalone-gate reasoning already used for DROIDS's `stand_request()`/`sit_request()`.
* **How this fits the rest of the ecosystem.** BRIDGE-PRINTER3D sits between Moonraker/Klipper and `HYDRA-UMC-SDK` → `HYDRA-UMC-SERVER` → cell safety — it coordinates auxiliary robot work around the printer and now sends real, gated job commands, but it never streams raw G-code and never replaces native firmware, heaters or thermal protection.

## 🧾 SLICER ARTIFACT COMPATIBILITY

The read-only artifact lane supports ordinary FDM G-code (`.gcode`, `.gco`, `.gc`) produced by OrcaSlicer, Ultimaker Cura, PrusaSlicer, Bambu Studio and other slicers. Familiar comments supply an origin hint; a missing marker remains `unknown-slicer`. `.gcode.3mf` and generic `.3mf` are fingerprinted but never unpacked. Resin slices (`.ctb`, `.goo`, `.photon`, `.pwmo`, `.pws`, `.sl1`) from Lychee-compatible workflows are deliberately opaque and never attributed to a specific printer or slicer.

This is compatibility with **output artifacts**, not remote control of those applications. The bridge does not start slicers, alter profiles, parse/execute G-code, upload files, contact cloud services or start prints. See [Slicer Artifact Compatibility](docs/SLICER_ARTIFACT_COMPATIBILITY.md) for the precise matrix and future-control prerequisites.

An artifact/profile match is still evidence, never permission to print. [Print Profile Admission Boundary](docs/PRINT_PROFILE_BOUNDARY.md) documents the separate validation required before any future native-controller operation.

---

## 📂 DIRECTORY STRUCTURE

```text
HYDRA-UMC-BRIDGE-PRINTER3D/
├── src/
│   └── hydra_umc_bridge_printer3d/
│       ├── __init__.py
│       ├── artifacts.py         # Read-only G-code, 3MF and resin-slice evidence
│       ├── profiles.py          # Profile compatibility evidence; never print authorization
│       └── moonraker.py         # MoonrakerProbe + PrinterBridge safety gate
├── tests/
│   ├── test_artifacts.py         # Slicer artifact evidence tests (no printer I/O)
│   ├── test_profiles.py          # Profile matching always denies execution
│   └── test_moonraker.py        # Readiness parsing and fail-safe gate tests
├── tools/
│   ├── build_test.py            # Non-mutating compile + test runner (build-test.bat/.sh)
│   ├── inspect_print_artifact.py # Local artifact evidence JSON CLI
│   └── bump_version.py          # Synchronizes pyproject.toml, manifest and CHANGELOG.md
├── build-test.bat / build-test.sh  # Validate only, never modifies the repository
├── build.bat / build.sh            # Validate, then bump version + CHANGELOG on success
├── pyproject.toml               # Package metadata; depends on HYDRA-UMC-SDK (git)
├── hydra-umc.project.json       # Ecosystem manifest (version, maturity, family)
├── CHANGELOG.md
├── CODE_OF_CONDUCT.md / CONTRIBUTING.md / SECURITY.md / SUPPORT.md
├── LICENSE / LICENSE.md
└── README.md / README_*.md      # This file and its 6 translations
```

---

## 4. ⚙️ BUILD & RUN

Requires Python 3.11+. `tools/build_test.py` expects `HYDRA-UMC-SDK` checked out as a sibling directory (`../HYDRA-UMC-SDK`) or pointed at via the `HYDRA_UMC_SDK_ROOT` environment variable.

```bash
# Windows
build-test.bat      # validate only — no version/CHANGELOG change
build.bat            # validate, then bump version + CHANGELOG on success

# Linux/macOS
bash build-test.sh
bash build.sh
```

`build-test` compiles every module under `src/` and `tools/` with `py_compile` and runs the full `unittest` suite (`tests/test_moonraker.py` and `tests/test_artifacts.py`), proving readiness-response parsing, artifact inspection and the fail-safe gate — it sends no G-code, touches no printer and never modifies the repository. `build` runs that same validation first and, only on success, calls `tools/bump_version.py` to synchronize the version across `pyproject.toml`, `hydra-umc.project.json` and `CHANGELOG.md`. There is no live printer `run` command yet — that requires a tested profile, authentication and physical safety review.

To inspect a local slicer output without contacting a printer:

```bash
py tools/inspect_print_artifact.py path/to/job.gcode
```

---

## ✅ Current Status & Next Steps

**Real today:** version `0.0.9`, a locally tested Moonraker readiness adapter (`MoonrakerProbe` + `PrinterBridge`) backed by `HYDRA-UMC-SDK`'s shared job gate, real SDK-gated job commands (`MoonrakerJobControl`: start/pause/resume/cancel an already-uploaded file through Moonraker's own REST API), read-only G-code/3MF/resin-slice and profile-compatibility evidence for the major slicer families, a deterministic thirty-five-test `unittest` suite including local HTTP `/printer/info`, the real, separate `/printer/objects/query?print_stats=state` contract, and real `POST` job-command verification, and non-mutating build-test scripts wired into CI with an SDK checkout.

**Integration boundary:** native printer firmware (Klipper via Moonraker) retains motion, heaters, thermal protection and machine interlocks at all times; this bridge reads readiness, sends only already-safe job-level commands (never raw G-code) and gates *auxiliary* robot work around it.

**Still ahead:** the bridge has not been exercised against a real printer, hotend or robot yet (only against a local fixture HTTP server) — raw G-code streaming still requires a tested printer profile, authentication and a physical safety review first.

---

## 🔗 Related Projects

This project is part of a larger robotics ecosystem by the same author (JuanenRac / Electro Hobby 3D), spanning firmware, control software, AI nodes and fleet tooling. Worth knowing about, since a request might actually be about one of these rather than this repository.

### Directly Related

- **[HYDRA-UMC-SDK](https://github.com/JuanenRac/HYDRA-UMC-SDK)** — the shared `bridge_contract` job gate every bridge (including this one) evaluates jobs through.
- **[HYDRA-UMC-SERVER](https://github.com/JuanenRac/HYDRA-UMC-SERVER)** — the authorised coordination endpoint this bridge reports to.
- **[HYDRA-UMC-MQTT-BROKER](https://github.com/JuanenRac/HYDRA-UMC-MQTT-BROKER)** — `mqtt_transport.py`'s real transport for this bridge's own `hydra/bridges/printer3d/...` topics (status, real Moonraker start/pause/resume/cancel, the shared job gate) - see that repo's own `docs/BRIDGE_TOPICS.md`.
- **[HYDRA-UMC-SAFETY-ZONES](https://github.com/JuanenRac/HYDRA-UMC-SAFETY-ZONES)** — future workspace safety evidence.

### Rest of the Ecosystem

**HYDRA-UMC platform** — the multi-robot micro-factory cell this bridge coordinates auxiliaries for
- **[HYDRA-UMC](https://github.com/JuanenRac/HYDRA-UMC)** — the CM5 + STM32H745 motherboard orchestrating up to 8 robot arms.
- **[HYDRA-UMC-SERVER](https://github.com/JuanenRac/HYDRA-UMC-SERVER)** — the Express/WebSocket backend every control client and bridge talks to.
- **[HYDRA-UMC-STUDIO](https://github.com/JuanenRac/HYDRA-UMC-STUDIO)** — web-based control dashboard, multi-robot 3D visualization.

**External Automation Bridges** — sibling repos sharing this same `HYDRA-UMC-SDK` job gate
- **[HYDRA-UMC-BRIDGE-CNC](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-CNC)** — CNC cell coordination bridge.
- **[HYDRA-UMC-BRIDGE-LASER](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-LASER)** — laser-cell coordination bridge.
- **[HYDRA-UMC-BRIDGE-OPENPNP](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-OPENPNP)** — board-flow bridge for OpenPnP.
- **[HYDRA-UMC-BRIDGE-ROS2](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-ROS2)** — bidirectional coordination boundary with ROS 2.

**Safety & Integration Evidence**
- **[HYDRA-UMC-SAFETY-ZONES](https://github.com/JuanenRac/HYDRA-UMC-SAFETY-ZONES)** — cell-zone safety evidence used across the bridge family.
- **[HYDRA-UMC-HIL-BRIDGE](https://github.com/JuanenRac/HYDRA-UMC-HIL-BRIDGE)** — hardware-in-the-loop test evidence.

## 👤 AUTHOR
**JuanenRac** (Electro Hobby 3D)
📧 electrohobby3d@gmail.com
📺 [youtube.com/@electrohobby3d](https://youtube.com/@electrohobby3d)

## 📜 LICENSE
GPL-3.0 - See LICENSE for details.
