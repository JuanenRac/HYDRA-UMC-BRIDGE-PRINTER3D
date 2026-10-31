# Changelog

All notable changes to this project are documented here.

## [Unreleased]

- **The MQTT transport is tested against a real broker:** `tests/test_broker_integration.py` starts a `HYDRA-UMC-MQTT-BROKER` on a free local port and runs the bridge through the shared client: the retained availability, a command answered at QoS 0, 1 and 2, a retained command that is only a replay, messages published at each QoS, the last will after an unclean loss of the link and the way back after the broker went down and up. It skips itself when node, `paho-mqtt` or the installed broker (`HYDRA_UMC_TEST_BROKER_DIR`, default the folder next to this one) are missing.

## [0.2.0] - The universal README and its check in the CI

- **README in the universal layout:** the README and its seven translations follow the layout that the four families share (22 sections in a fixed order), with an architecture picture and a repository-structure picture drawn from `docs/architecture.json` and `docs/structure.json`; the CI validator checks both pictures and the file tree. Where the repository has a service or an MQTT transport, the README now says how to start it and which environment variables it reads.

- **The layout of the README is checked in the CI:** the validator runs `tools/universal_readme_check.py` and lists, as a warning, what differs from the universal layout of the README.

## [0.1.9] - The MQTT transport comes from the SDK and pinned to SDK 0.3.6

- Building no longer changes the version; raising it is the explicit `bump` command (`python tools/hydra_project_tool.py bump`). The build scripts only report the version they built, and CI fails if a build script runs a bump.
- **The MQTT transport comes from the SDK.** Connecting with retries, the publish record and the message dispatcher are the shared `hydra_umc_sdk.bridge_transport` of SDK 0.3.6 instead of a copy of their own; what is specific to this bridge (its topics and what it does with a message) stays here, and its tests are unchanged.

- **Pinned to SDK 0.3.6** (dependency and contract checkout in CI). From this version the shared bridge gate fails closed: a productive job is refused when the bridge did not pass the state it read from its machine. The bridge passes what Moonraker reported.
- The banner follows the animated style of the ecosystem banners, with the name, the kind and the technologies of the project.
- Added `tools/hydra_project_tool.py`: the same `validate`, `test`, `version`, `status` and `bump` commands in every repository. The checks run with `HYDRA_UMC_CI=1` and fail if the version changes; only `bump` changes it.
- The SDK is now fetched at a release tag instead of the main branch, so a change of the SDK cannot break this repository by itself.
- Successful incremental build: synchronized package metadata and `hydra-umc.project.json`.

## [0.1.8]

- Successful incremental build: synchronized package metadata and `hydra-umc.project.json`.
- The licence is written as GPL-3.0-or-later in every header and in the package metadata.

## [0.1.7] - Maturity lowered to functional

- Maturity is functional: the code, tests and documentation are in place, but nothing here has been verified on real hardware yet, so the manifest no longer claims the established level.

## [0.1.6] - A hostile payload can no longer stop the bridge, a stop never waits, and the answers say what was done

- **The loop survives anything a client sends.** A deeply nested JSON (a few kilobytes of `[` raised `RecursionError`, which escaped and ended `loop_forever()`), a payload larger than 16 KiB, an unreadable payload and any unexpected failure while handling a message are now answered with a refusal on the verb's result topic. Nothing a message does can end the loop.
- **A stop never waits.** Messages are handled off the network thread; `cmd/pause`, `cmd/cancel` and the new `cmd/emergency_stop` have a lane of their own, so a slow Moonraker answering a start or a status request does not delay them.
- **New `cmd/emergency_stop`.** Calls Moonraker's `POST /printer/emergency_stop` (Klipper M112: heaters and motors off at once). It is never gated and never deduplicated; a `FIRMWARE_RESTART` afterwards stays a human decision.
- **One idempotency key space per verb.** Asking the gate with `cmd/job` and then starting with the same job (the same key) used to answer the start with the gate's stored "allowed" and never reach Moonraker. Keys are now `job:<key>` and `start:<key>`. A failure after a key was claimed leaves an explicit "could not be handled" answer for that key instead of a silent "already handled".
- **`cmd/job` answers say what they are.** The result carries `"mode": "gate-only"`; an `ABORT` through that topic says `"forwarded": false` and that nothing was stopped, and points to `cmd/cancel` and `cmd/emergency_stop`.
- **Moonraker API key.** `MoonrakerProbe` and `MoonrakerJobControl` take an `api_key` (the bridge reads `MOONRAKER_API_KEY` when none is given) and send it as `X-Api-Key`. A 401 or 403 is reported as refused credentials instead of "unreachable".
- **Safer start.** The file name is checked by path components (a legitimate `part..v2.gcode` is no longer refused; `..` and `.` components, a leading `/` or `~`, backslashes, control characters and anything that is not a G-code file are), and Moonraker must know the file (`/server/files/metadata`) or no start is sent. A Moonraker URL with a query or a fragment is refused.
- **Klippy `startup` is `OFFLINE`**, not `FAULT`: it is the normal, brief state after a `FIRMWARE_RESTART`.
- **A retained state can be judged.** `state` carries `observed_at` (epoch milliseconds); `availability` is `online` once connected and the broker publishes `offline` (Last Will) when the bridge dies; the reconnect delay is bounded.
- **paho-mqtt.** The client uses the version 2 callback API (`mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, ...)`), which also starts with paho-mqtt 2.0; the extra now requires `paho-mqtt>=2.1,<3`.
- `inspect_artifact()` accepts an optional `max_bytes` and refuses a larger file instead of hashing it.
- `LICENSE` now carries the complete GPL-3.0-or-later text; the unused `subprocess` import of `tools/ci_validate.py` is gone.
- README (all eight languages) and `docs/` updated: test counts and test file list, the Spanish, German, French, Italian, Japanese, Chinese and Portuguese introductions no longer say the bridge only reads, the HYDRA-UMC-SERVER path that does not exist is no longer drawn, and the artifact commands show `python3` as well as `py`.
- 23 new tests (`tests/test_hardening.py`).

## [0.1.5] - Connects to a broker that demands credentials: user, password and TLS from the environment

- The MQTT client now takes its credentials and TLS from the environment of the service (`HYDRA_MQTT_USERNAME`, `HYDRA_MQTT_PASSWORD` or `HYDRA_MQTT_PASSWORD_FILE`, `HYDRA_MQTT_TLS_CA`) through `hydra_umc_sdk.mqtt_connection`, so it can reach a production HYDRA-UMC-MQTT-BROKER, which refuses anonymous clients and evaluates its ACL for the identity of the credential.
- An explicit `username`/`password` argument still wins, and a password without a user name is refused.
- The client ID must start with the `clientIdPrefix` of the bridge's credential.
- New `tests/test_mqtt_environment.py` (a fake paho client, so it runs without paho-mqtt) proves that the environment credentials and the CA reach the client, that the explicit ones win, that nothing set is an anonymous plain connection, and that a lonely password is refused.

## [0.1.4] - A repeated idempotency key never starts a second print

- **Idempotency keys.** `PrinterMqttBridge` accepts an `IdempotencyStore` from HYDRA-UMC-SDK. A `cmd/start` begins a real print: QoS 1 may deliver it twice and a client may retry it, and the repeat started the print again. Now the first time a key arrives the command runs and its answer is kept; a repeat gets that answer and nothing is sent to Moonraker. The same holds for `cmd/job`.
- Four new tests (tests/test_idempotency.py).

## [0.1.3] - configurable MQTT authentication, and a retained command can no longer replay as a live one

- **.** `run_forever` had no way to authenticate against
  HYDRA-UMC-MQTT-BROKER's own real, opt-in `MQTT_AUTH_JSON` username/
  password CONNECT authentication - a broker deployed with credentials
  required was simply unreachable from this bridge. New optional
  `username`/`password` keyword arguments call paho-mqtt's own
  `username_pw_set()`; a `password` given without a `username` is
  rejected outright rather than silently connecting unauthenticated.
- **.** `on_connect`'s `subscribe("cmd/#")` makes the broker replay
  every currently-retained message on that wildcard immediately - on
  *every* reconnect, not just once at startup. A retained `cmd/start` or
  `cmd/resume` would otherwise re-start or re-resume a real print job
  with no new operator intent behind it, every single time this bridge
  reconnects. `handle_message()` now takes a `retained` flag and ignores
  any retained delivery before it ever reaches Moonraker; `on_message()`
  passes the real MQTT message's own `.retain` flag through.
- 8 new tests (4 confirming `cmd/start`/`cmd/resume`/`cmd/cancel` never
  reach the real local Moonraker fixture server when retained, plus the
  same auth/retain-passthrough coverage as sibling bridges), confirmed to
  fail against the pre-fix code (7 real failures) via a local revert of
  just `mqtt_transport.py`, tests kept. 72/72 `unittest` cases pass
  (`python tools/build_test.py`, up from 64).

## [0.1.2] - stale gate reuse, non-object JSON roots, unconfirmed POSTs

- `refresh_status` cached its result in `_last_status` with no
  expiry, and `cmd/resume`, `cmd/start` and `cmd/job` all reused that stale
  reading (`self._last_status or self.refresh_status()`) instead of
  fetching current readiness. A printer that changed state seconds after
  the last `cmd/status` fetch was still gated against the old reading.
  Fixed: every command now calls `refresh_status()` unconditionally right
  before deciding, exactly like CNC/LASER's own per-command refresh; the
  cache field is gone.
- `parse_info` and `parse_print_stats` called `payload.get(...)`
  assuming a JSON object root. Valid JSON whose root is a bare array,
  string, number, bool or null - a real possibility from a misconfigured
  proxy or an unrelated service on the same host/port - raised
  `AttributeError`, an exception `_get()`'s own except clause never
  catches (it only catches transport/JSON-decode errors, not "valid JSON,
  wrong shape"), crashing the call instead of failing closed like every
  other malformed-response case already does. Fixed: both now check
  `isinstance(payload, dict)` before touching it.
- `MoonrakerJobControl`'s POST-based job commands treated a bare
  HTTP 200 as Moonraker's own confirmation. A misconfigured proxy,
  captive portal, or unrelated service on the same host/port could all
  answer 200 with a body that never came from Moonraker at all. Fixed:
  the response body is now parsed and checked against Moonraker's
  documented `{"result": "ok"}` contract for these endpoints before the
  command is reported as accepted - the same real-response-shape
  discipline `parse_info()`/`parse_print_stats()` already apply to
  Moonraker's read endpoints.
- Fixed a latent bug in this suite's own HTTP fixture: `override or
  default` silently discarded a deliberately-empty (`b""`) override
  response body because it is falsy in Python, hiding exactly the "HTTP
  200 with an unexpected body" case needed to exercise. Replaced
  with an explicit `is not None` check everywhere the fixture applies an
  override.
- **(docs):** `SLICER_ARTIFACT_COMPATIBILITY.md` and
  `PRINT_PROFILE_BOUNDARY.md` described "no printer contact" and
  "future...printer-control capability" as if that applied to the whole
  bridge, when `MoonrakerJobControl` already sends real, gated
  start/pause/resume/cancel commands to Moonraker today. Reworded both to
  scope those claims to artifact/profile inspection specifically, link to
  the real (separate, already-implemented, already-gated) command-dispatch
  module by name, and spell out precisely what remains genuinely
  unimplemented (profile compatibility never gates a start) versus merely
  unvalidated against real hardware (every test of that path runs against
  this repo's own HTTP fixture, never a physical printer).

## [0.1.1] - Real phase gating and a real envelope fix

- **Fixed a real START-via-ABORT gating bug (P0):** `evaluate_job()` (the shared gate `PrinterBridge.plan()` calls)
  deliberately always allows `JobPhase.ABORT`, "so that an external
  integration can request a controlled stop" - correct for a STOP-class
  action, but `MoonrakerJobControl.start_job()` reused that same generic
  gate for a START-class action. Reproduced: a `BridgeJob` carrying
  `phase=ABORT`, even built from a real `SAFE_STOP`/`FAULT` machine
  state, sailed through as `allowed=True`, and `start_job()` then
  actually POSTed `/printer/print/start` - starting a NEW print in
  response to what was labeled a request to STOP. Fixed: `start_job()`
  now refuses any job whose `phase` is not `PROCESS` before the shared
  gate is ever consulted.
- **Fixed a real Moonraker envelope-unwrapping bug (P1):** `parse_print_stats()`
  looked for `status` directly on the outer HTTP response instead of
  unwrapping Moonraker's own real `result` envelope first
  (`{"result": {"status": {"print_stats": {...}}}}` - moonraker.readthedocs.io,
  unlike `parse_info()` just above it, which already unwrapped `result`
  correctly). A perfectly healthy standby printer was reported OFFLINE
  with "missing print_stats". Every test fixture in this repo's own
  suite also used the wrong (unwrapped) shape, which is why this went
  unnoticed - none of them exercised the real wire format. Fixed the
  parser and every fixture; added a direct regression test against the
  real envelope shape.
- 5 tests added/updated (56 total, up from 53) - `python -m unittest
  discover -s tests`: all passing.
- **Fixed a missing translation section:** the English README's own
  "artifact/profile match is still evidence, never permission to print"
  paragraph, linking `docs/PRINT_PROFILE_BOUNDARY.md`, was missing from
  all 6 translations even though the file was already listed in each
  one's own Directory Structure tree. Added the equivalent paragraph +
  link to all 6.
- **`tools/bump_version.py`'s own auto-generated CHANGELOG heading
  embedded a literal calendar date** (`date.today().isoformat()`) into
  this public file - every real entry here is otherwise dated only by
  its position, never a literal date. The same bug, copied from the same
  template, found and fixed in the same pass across all 5 sibling
  bridges (BRIDGE-CNC/LASER/OPENPNP/PRINTER3D/ROS2) plus HYDRA-UMC-SDK
  and HYDRA-UMC-OS. Removed before it could ever actually land one (no
  prior real build in this repo's own history shows the script running
  mechanically without a hand-written entry replacing the stub first).
  Repo-hygiene fix, no runtime code changed, no version bump.
- **`run_forever()`'s initial MQTT connect now retries with backoff**
  (`connect_with_retry()`, new) - this bridge's process used to die
  outright if it started before HYDRA-UMC-MQTT-BROKER was listening yet,
  a real race between two independent systemd units with no ordering
  guarantee across a reboot. Only `OSError` (what an unreachable broker
  actually raises) is retried; anything else surfaces immediately as a
  real bug. Once connected, paho-mqtt's own `loop_forever()` already
  handles a later mid-session drop on its own - only the first connect
  needed this.

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

## [0.0.7]

- Added `docs/BRIDGE_GUIDE.md`, complementing the slicer and profile-boundary
  documents with software compatibility, scripts and hardware acceptance flow.
- Removed the duplicated terminal BUILD & RUN section from all seven README files.
- Added an offline CLI that compares one local artifact with one local profile
  JSON and preserves `execution_authorized: false` in its output.
- Added CLI contract coverage; the full suite now has seventeen tests.
- Synchronized package metadata, ecosystem manifest and all seven README files.

## [0.0.6]

- Added `PrintProfile` and `assess_artifact_profile()` for declared local
  artifact/profile compatibility evidence.
- Made the non-escalation rule executable: every assessment returns
  `execution_authorized: false`, including a compatible profile match.
- Added three deterministic tests for compatible, incompatible and invalid
  profile evidence; the full suite now has sixteen tests.
- Synchronized package metadata, ecosystem manifest and all seven README files.

## [0.0.5]

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

## [0.0.4]

- Synchronized the English README and all six translated README files with the
  released readiness-probe scope, current version and seven-test coverage.
- Successful incremental build: synchronized package metadata and
  `hydra-umc.project.json`.

## [0.0.3]

- Normalized surrounding whitespace in a configured Moonraker base URL before
  opening the documented readiness request.
- Made a non-string endpoint value fail safe as `OFFLINE` instead of allowing
  a configuration-type error to escape the probe.
- Successful incremental build: synchronized package metadata and
  `hydra-umc.project.json`.

## [0.0.2]

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
