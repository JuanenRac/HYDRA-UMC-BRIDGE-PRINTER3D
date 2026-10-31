<!-- =============================================================================
HYDRA-UMC-BRIDGE-PRINTER3D - Technical bridge guide
Copyright (C) JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
GPL-3.0-or-later - see LICENSE
============================================================================= -->

# HYDRA-UMC-BRIDGE-PRINTER3D Technical Guide

## Scope and operating model

The bridge separates four lanes: Moonraker readiness (`/printer/info` and `/printer/objects/query?print_stats=state`, both read-only), real SDK-gated job control, local slicer-artifact evidence, and declared artifact/profile compatibility. `MoonrakerProbe` maps only literal `ready` to idle and bounds each HTTP readiness payload to 64 KiB before JSON parsing; an oversized or malformed response is `OFFLINE`. A bare `klippy_state=ready` reading is not trusted as idle on its own - Klipper's own `klippy_state` stays `"ready"` throughout an entire print, so the probe also confirms the real, separate `print_stats.state` object (researched against moonraker.readthedocs.io/en/latest/printer_objects) before reporting `IDLE`: `printing` maps to `RUNNING`, `paused` to `HOLDING`, `error` to `FAULT`, and `standby`/`complete`/`cancelled` defer to the original reading. `inspect_artifact()` fingerprints G-code, 3MF and resin-slice candidates without unpacking or parsing commands. `assess_artifact_profile()` can confirm metadata compatibility but always returns `execution_authorized: false`.

`MoonrakerJobControl` is this bridge's only write path: `start_job()`/`pause_job()`/`resume_job()`/`cancel_job()`/`emergency_stop()` send real `POST` requests to Moonraker's own `/printer/print/start|pause|resume|cancel` and `/printer/emergency_stop` endpoints, gated the same way every other productive dispatch in this ecosystem is (`start_job()` through `evaluate_job()`; `pause_job()`/`cancel_job()`/`emergency_stop()` always allowed like `ABORT` - the last one is Klipper's M112, heaters and motors off at once, and needs a `FIRMWARE_RESTART` afterwards; `resume_job()` through a standalone `HOLDING`-only gate). It only ever references an already-uploaded, already-sliced file by name - the name is checked by path components (a G-code suffix, no `..` or `.` component, no leading `/` or `~`, no backslash or control character) and Moonraker must know the file (`/server/files/metadata`) before a start is sent; no module here uploads a file, streams raw G-code, modifies a profile, or controls heaters directly.

`mqtt_transport.py` reaches this same real logic over `HYDRA-UMC-MQTT-BROKER`, this bridge's second real transport. `PrinterMqttBridge.handle_message()` routes `hydra/bridges/printer3d/cmd/{status,job,start,pause,resume,cancel,emergency_stop}` to the same `MoonrakerProbe`/`MoonrakerJobControl`/`PrinterBridge` calls above, publishing `hydra/bridges/printer3d/state` (retained) and one `.../cmd/<verb>/result` per command - no new physical authority, only a new way to reach what already existed. `start` accepts `{"job": <job_to_dict>, "filename": ...}`; `job` accepts a bare `BridgeJob` for a gate-only check and answers with `"mode": "gate-only"` - it never acts, so an `ABORT` through it is answered with `"forwarded": false` and the reason says that nothing was stopped (use `cmd/cancel` or `cmd/emergency_stop`). Idempotency keys are kept per verb (`job:<key>`, `start:<key>`), so a job checked with `cmd/job` can then be started with the same key; if handling fails after a key was claimed, the key keeps an explicit "could not be handled" answer. Every message is handled without ever raising: a payload over 16 KiB, deeply nested or unreadable JSON and any unexpected failure get a refusal on the verb's result topic. In `run_forever()` the messages are handled off the network thread, one at a time and in order, except `pause`, `cancel` and `emergency_stop`, which have a lane of their own so that a slow Moonraker never delays a stop. `state` carries `observed_at` (epoch milliseconds), and the bridge publishes `hydra/bridges/printer3d/availability` (`online` when connected; the broker publishes `offline`, the MQTT Last Will, when the connection is lost). The client uses paho-mqtt's version 2 callback API (`paho-mqtt>=2.1,<3`). Dispatch is pure enough to unit-test against the same local `ThreadingHTTPServer` Moonraker fixture `test_moonraker.py` already uses, no real broker required - `paho-mqtt` (optional `[mqtt]` extra) is only imported, lazily, inside `run_forever()`.

## Compatible software

FDM artifact evidence supports ordinary G-code from OrcaSlicer, Ultimaker Cura, PrusaSlicer, Bambu Studio and other slicers. `.gcode.3mf` and `.3mf` are identified only. Lychee-compatible resin outputs such as `.ctb` and `.goo` are opaque evidence, not decoded printer jobs. Moonraker/Klipper is the only printer API currently represented; job control is real, readiness is real, everything else stays read-only.

## Scripts and verification

| Script | Purpose | Changes version/CHANGELOG? |
|---|---|---|
| `build-test.bat` / `build-test.sh` | Compile and run offline adapter tests | No |
| `build.bat` / `build.sh` | Validate, then build (never changes the version or the CHANGELOG) | No |
| `tools/inspect_print_artifact.py` | Print JSON evidence for one local artifact | No |
| `tools/assess_print_profile.py` | Compare local profile JSON and artifact; never authorizes execution | No |

## Adding a new script

Use the standard header, declared mutation behavior, numbered console steps and `pause` in `.bat`. Keep reusable code in `src/` or `tools/`, compile it in `tools/build_test.py`, add a deterministic test and document it. A new script must not make artifact detection become a print command.

## Following the global stop

The server can announce a global stop on `<mqtt prefix>/safety/estop` (a retained `SafetyState` message: `SAFE_STOP`, later `READY`; the contract is `docs/GLOBAL_STOP.md` of HYDRA-UMC-SERVER). This bridge can follow it. It is off by default and then behaves exactly as before: it does not even subscribe to the topic.

| Switch | Default | Meaning |
|---|---|---|
| `HYDRA_UMC_PRINTER3D_GLOBAL_STOP` | off | `1` makes the bridge subscribe to the announcement (QoS 1, again after every reconnect) |
| `HYDRA_UMC_PRINTER3D_GLOBAL_STOP_TOPIC` | `hydra/swarm/safety/estop` | the topic, when the MQTT prefix of the server is not the default one |
| `HYDRA_UMC_PRINTER3D_GLOBAL_STOP_STRICT` | off | `1` also refuses before the first announcement has been heard |

While the last announcement says `SAFE_STOP`, says anything but `READY`, or cannot be read, the command handler of the bridge refuses `cmd/resume`, `cmd/start` and `cmd/job` (an abort job passes) with an answer that gives the reason (`global stop active (SAFE_STOP) - nothing moves until the server announces READY`); `cmd/pause`, `cmd/cancel`, `cmd/emergency_stop` and `cmd/status` keep working. Only a `READY` message ends it. The announcement is read although it is retained: it is the state, not a replayed command. When the broker is lost the bridge keeps the last state it heard; a bridge that has not heard the topic yet is left as it was, unless `HYDRA_UMC_PRINTER3D_GLOBAL_STOP_STRICT` is on. This is a refusal in software: the controller and the machine keep the last word, and the contract adds a stop, it never removes one. Tested against a real broker (`tests/test_global_stop_broker.py`); never run with the real server.

## Hardware acceptance gate

Use real exported jobs, identify a concrete printer/controller/profile, validate material/nozzle/volume constraints, read authenticated Moonraker state (the API key goes in `MOONRAKER_API_KEY` and is sent as `X-Api-Key`; a 401 or 403 is reported as refused credentials; this has only been tried against a local fixture), verify independent thermal/machine safety, then run a supervised HIL plan. Native firmware retains all print authority.
