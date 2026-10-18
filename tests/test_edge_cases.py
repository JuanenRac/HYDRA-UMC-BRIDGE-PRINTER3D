# =============================================================================
# HYDRA-UMC-BRIDGE-PRINTER3D - Stop commands, credentials, file names and artifact boundaries
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from hydra_umc_sdk.bridge_contract import BridgeJob, CellState, JobPhase, MachineState

from hydra_umc_bridge_printer3d import MoonrakerJobControl, MoonrakerProbe, PrinterStatus
from hydra_umc_bridge_printer3d.artifacts import PrintArtifact, PrintArtifactKind, PrintTechnology, inspect_artifact
from hydra_umc_bridge_printer3d.moonraker import API_KEY_ENV, API_KEY_HEADER, api_key_from_env, validate_gcode_filename
from hydra_umc_bridge_printer3d.profiles import PrintProfile, assess_artifact_profile


class Recorder(BaseHTTPRequestHandler):
    requests: list[tuple[str, str, str | None]] = []
    status = 200
    body = b'{"result": "ok"}'

    def _answer(self):
        type(self).requests.append((self.command, self.path, self.headers.get(API_KEY_HEADER)))
        self.send_response(type(self).status)
        self.send_header("Content-Length", str(len(type(self).body)))
        self.end_headers()
        self.wfile.write(type(self).body)

    do_GET = _answer
    do_POST = _answer

    def log_message(self, format, *args):  # noqa: A002
        return


class ServerCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Recorder)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.thread.join()
        cls.server.server_close()

    def setUp(self):
        Recorder.requests = []
        Recorder.status = 200
        Recorder.body = b'{"result": "ok"}'


class StopLaneTests(ServerCase):
    def test_cancel_pause_and_emergency_stop_are_sent_whatever_the_machine_is_doing(self):
        control = MoonrakerJobControl()
        for call, path in ((control.cancel_job, "/printer/print/cancel"), (control.pause_job, "/printer/print/pause"), (control.emergency_stop, "/printer/emergency_stop")):
            Recorder.requests = []
            result = call(self.url)
            self.assertTrue(result.executed, path)
            self.assertEqual(Recorder.requests, [("POST", path, None)])

    def test_the_emergency_stop_is_never_deduplicated(self):
        control = MoonrakerJobControl()
        control.emergency_stop(self.url)
        control.emergency_stop(self.url)
        self.assertEqual([r[1] for r in Recorder.requests], ["/printer/emergency_stop"] * 2)

    def test_a_refused_credential_is_named_for_every_stop_and_is_never_reported_as_stopped(self):
        for status in (401, 403):
            Recorder.status = status
            for call in (MoonrakerJobControl().cancel_job, MoonrakerJobControl().emergency_stop):
                result = call(self.url)
                self.assertFalse(result.executed)
                self.assertEqual(result.http_status, status)
                self.assertIn(API_KEY_ENV, result.reason)

    def test_a_stop_that_moonraker_rejects_or_does_not_confirm_is_not_reported_as_executed(self):
        Recorder.status = 500
        self.assertFalse(MoonrakerJobControl().emergency_stop(self.url).executed)
        Recorder.status = 200
        for body in (b"", b"not json", b'"ok"', b'{"result": "nope"}', b"[]", b"\xff\xfe"):
            Recorder.body = body
            self.assertFalse(MoonrakerJobControl().cancel_job(self.url).executed, body)

    def test_a_stop_to_an_address_that_is_not_http_never_leaves_the_machine(self):
        for url in ("ftp://127.0.0.1", "file:///etc/passwd", "127.0.0.1:7125", "", "http://", "http://h/?x=1", "http://h/#frag"):
            result = MoonrakerJobControl().emergency_stop(url)
            self.assertFalse(result.executed, url)
        self.assertEqual(Recorder.requests, [])

    def test_the_api_key_travels_on_every_request_and_a_trailing_slash_is_harmless(self):
        MoonrakerJobControl(api_key="secret").cancel_job(self.url + "/")
        self.assertEqual(Recorder.requests, [("POST", "/printer/print/cancel", "secret")])

    def test_the_probe_reports_refused_credentials_as_offline_with_the_hint(self):
        Recorder.status = 403
        status = MoonrakerProbe().fetch(self.url)
        self.assertEqual(status.state, MachineState.OFFLINE)
        self.assertIn(API_KEY_ENV, status.message)


class StartJobTests(ServerCase):
    def job(self, phase=JobPhase.PROCESS):
        return BridgeJob("j", "k", "orchestrator", phase, MachineState.IDLE, {})

    def idle(self):
        return PrinterStatus(MachineState.IDLE, "ready")

    def test_a_file_name_that_escapes_the_gcodes_root_is_refused_before_any_request(self):
        for name in ("../x.gcode", "a/../b.gcode", "/etc/x.gcode", "~/x.gcode", "a\\b.gcode", "a\nb.gcode", "a\x00b.gcode", " x.gcode", "x.gcode ", "a//b.gcode", "./x.gcode", "x.txt", "x", "", "   ", None, 5, ["x.gcode"]):
            result = MoonrakerJobControl().start_job(self.job(), CellState.READY, self.idle(), self.url, name)
            self.assertFalse(result.executed, repr(name))
        self.assertEqual(Recorder.requests, [])

    def test_names_that_only_look_suspicious_are_fine(self):
        for name in ("part..v2.gcode", "a/b/c.GCODE", "x.gco", "x.g", "x.gc", "dir.with.dots/x.gcode"):
            self.assertEqual(validate_gcode_filename(name), "", name)

    def test_only_the_process_phase_starts_a_print(self):
        for phase in (JobPhase.ABORT, JobPhase.LOAD, JobPhase.UNLOAD):
            result = MoonrakerJobControl().start_job(self.job(phase), CellState.READY, self.idle(), self.url, "x.gcode")
            self.assertFalse(result.executed, phase)
        self.assertEqual(Recorder.requests, [])

    def test_a_file_moonraker_does_not_have_is_not_started(self):
        Recorder.status = 404
        result = MoonrakerJobControl().start_job(self.job(), CellState.READY, self.idle(), self.url, "missing.gcode")
        self.assertFalse(result.executed)
        self.assertEqual([r[1].split("?")[0] for r in Recorder.requests], ["/server/files/metadata"])

    def test_resume_needs_a_paused_printer_in_a_ready_cell(self):
        control = MoonrakerJobControl()
        paused = PrinterStatus(MachineState.HOLDING, "paused")
        self.assertFalse(control.resume_job(CellState.FAULT, paused, self.url).executed)
        self.assertFalse(control.resume_job(CellState.READY, self.idle(), self.url).executed)
        self.assertEqual(Recorder.requests, [])
        self.assertTrue(control.resume_job(CellState.READY, paused, self.url).executed)


class ApiKeyTests(unittest.TestCase):
    def test_the_key_comes_from_the_environment_trimmed_and_blank_means_none(self):
        self.assertEqual(api_key_from_env({API_KEY_ENV: "  abc  "}), "abc")
        self.assertIsNone(api_key_from_env({API_KEY_ENV: "   "}))
        self.assertIsNone(api_key_from_env({}))


class ArtifactBoundaryTests(unittest.TestCase):
    def test_a_file_larger_than_the_allowance_is_refused_without_reading_it(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "big.gcode"
            path.write_bytes(b"x" * 100)
            refused = inspect_artifact(path, max_bytes=99)
            self.assertFalse(refused.available)
            self.assertEqual(refused.sha256, "")
            self.assertEqual(refused.size_bytes, 100)
            self.assertTrue(inspect_artifact(path, max_bytes=100).available)

    def test_a_directory_and_an_unreadable_candidate_fail_safely(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertFalse(inspect_artifact(directory).available)
        self.assertFalse(inspect_artifact(None).available)

    def test_an_unknown_extension_is_hashed_but_not_admitted(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.stl"
            path.write_bytes(b"solid")
            artifact = inspect_artifact(path)
            self.assertEqual(artifact.kind, PrintArtifactKind.UNKNOWN)
            self.assertEqual(len(artifact.sha256), 64)

    def test_the_slicer_marker_is_only_read_from_the_start_of_the_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "late.gcode"
            path.write_bytes(b"G1 X1\n" * 20000 + b"; OrcaSlicer\n")
            self.assertEqual(inspect_artifact(path).source_hint, "unknown-slicer")

    def test_the_json_view_has_plain_values_only(self):
        artifact = PrintArtifact(True, PrintArtifactKind.FDM_GCODE, PrintTechnology.FDM, "x", "m")
        values = artifact.as_json()
        self.assertEqual((values["kind"], values["technology"]), ("fdm-gcode", "fdm"))


class ProfileTests(unittest.TestCase):
    fdm = PrintProfile("p1", PrintTechnology.FDM, frozenset({PrintArtifactKind.FDM_GCODE}))
    gcode = PrintArtifact(True, PrintArtifactKind.FDM_GCODE, PrintTechnology.FDM, "x", "m")

    def test_a_compatible_artifact_never_authorizes_execution(self):
        verdict = assess_artifact_profile(self.fdm, self.gcode)
        self.assertTrue(verdict.profile_compatible)
        self.assertFalse(verdict.execution_authorized)

    def test_each_mismatch_is_refused_with_its_own_reason(self):
        cases = [
            (PrintProfile("", PrintTechnology.FDM, frozenset({PrintArtifactKind.FDM_GCODE})), self.gcode, "identifier"),
            (PrintProfile("   ", PrintTechnology.FDM, frozenset({PrintArtifactKind.FDM_GCODE})), self.gcode, "identifier"),
            (self.fdm, PrintArtifact(False, PrintArtifactKind.FDM_GCODE, PrintTechnology.FDM, "x", "m"), "unavailable"),
            (self.fdm, PrintArtifact(True, PrintArtifactKind.UNKNOWN, PrintTechnology.FDM, "x", "m"), "unavailable"),
            (self.fdm, PrintArtifact(True, PrintArtifactKind.RESIN_SLICE, PrintTechnology.RESIN, "x", "m"), "technology"),
            (self.fdm, PrintArtifact(True, PrintArtifactKind.FDM_GCODE_3MF, PrintTechnology.FDM, "x", "m"), "kind"),
        ]
        for profile, artifact, word in cases:
            verdict = assess_artifact_profile(profile, artifact)
            self.assertFalse(verdict.profile_compatible, word)
            self.assertFalse(verdict.execution_authorized, word)
            self.assertIn(word, verdict.reason)


class StartPayloadTests(unittest.TestCase):
    """cmd/start carries a job and a file name; whatever else arrives must be refused, never raised."""

    def bridge(self):
        from hydra_umc_bridge_printer3d import PrinterMqttBridge

        return PrinterMqttBridge("http://127.0.0.1:9", lambda: CellState.READY, api_key="")

    def answer(self, payload):
        import json
        from hydra_umc_bridge_printer3d.mqtt_transport import TOPIC_PREFIX

        publishes = self.bridge().handle_message(f"{TOPIC_PREFIX}cmd/start", payload)
        self.assertEqual(len(publishes), 1, payload)
        self.assertEqual(publishes[0].topic, f"{TOPIC_PREFIX}cmd/start/result")
        return json.loads(publishes[0].payload)

    def test_payloads_that_are_not_a_start_request_are_refused(self):
        for payload in (b"null", b"[]", b"7", b'"x"', b"", b"{", bytes([255, 254]), b"{}", b'{"job": 5, "filename": "x.gcode"}', b'{"job": {}, "filename": "x.gcode"}'):
            result = self.answer(payload)
            self.assertIs(result["executed"], False, payload)
            self.assertIs(result["allowed"], False, payload)

    def test_a_retained_start_is_ignored_and_a_status_is_always_answered_even_when_moonraker_is_down(self):
        import json
        from hydra_umc_bridge_printer3d.mqtt_transport import TOPIC_PREFIX

        b = self.bridge()
        self.assertEqual(b.handle_message(f"{TOPIC_PREFIX}cmd/start", b"{}", retained=True), [])
        state = json.loads(b.handle_message(f"{TOPIC_PREFIX}cmd/status", b"")[0].payload)
        self.assertEqual(state["state"], MachineState.OFFLINE.value)


if __name__ == "__main__":
    unittest.main()
