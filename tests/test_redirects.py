# =============================================================================
# HYDRA-UMC-BRIDGE-PRINTER3D - redirect handling tests
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from hydra_umc_sdk.bridge_contract import MachineState
from hydra_umc_bridge_printer3d import MoonrakerJobControl, MoonrakerProbe
from hydra_umc_bridge_printer3d.service import ConfigError, parse_config


class _Target(BaseHTTPRequestHandler):
    """Where a redirect points to: it records every request it gets."""

    seen: list[tuple[str, str]] = []

    def _answer(self):
        type(self).seen.append((self.command, self.path))
        if self.path.startswith("/printer/objects/query"):
            body = json.dumps({"result": {"status": {"print_stats": {"state": "standby"}}}}).encode()
        else:
            body = json.dumps({"state": "ready", "state_message": "ok"}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    do_GET = _answer  # noqa: N815
    do_POST = _answer  # noqa: N815

    def log_message(self, *args):  # noqa: D401
        pass


def _redirector(target_port: int):
    class Redirect(BaseHTTPRequestHandler):
        requests: list[tuple[str, str]] = []

        def _go(self):
            type(self).requests.append((self.command, self.path))
            self.send_response(302)
            self.send_header("Location", f"http://127.0.0.1:{target_port}{self.path}")
            self.send_header("Content-Length", "0")
            self.end_headers()

        do_GET = _go  # noqa: N815
        do_POST = _go  # noqa: N815

        def log_message(self, *args):
            pass

    return Redirect


class RedirectTests(unittest.TestCase):
    def setUp(self):
        _Target.seen = []
        self.target = ThreadingHTTPServer(("127.0.0.1", 0), _Target)
        self.redirector_class = _redirector(self.target.server_address[1])
        self.redirector = ThreadingHTTPServer(("127.0.0.1", 0), self.redirector_class)
        for server in (self.target, self.redirector):
            threading.Thread(target=server.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.redirector.server_address[1]}"

    def tearDown(self):
        for server in (self.target, self.redirector):
            server.shutdown()
            server.server_close()

    def test_a_redirect_is_followed_by_default_as_it_always_was(self):
        status = MoonrakerProbe(single_request=False).fetch(self.base)
        self.assertEqual(status.state, MachineState.IDLE)
        self.assertTrue(any(path.startswith("/printer/info") for _, path in _Target.seen))

    def test_with_following_off_the_readiness_reading_stops_at_the_redirect(self):
        status = MoonrakerProbe(single_request=False, follow_redirects=False).fetch(self.base)
        self.assertEqual(status.state, MachineState.OFFLINE)
        self.assertIn("redirect (HTTP 302)", status.message)
        self.assertIn("moonraker.follow_redirects", status.message)
        self.assertEqual(_Target.seen, [], "nothing reached the address the redirect pointed to")

    def test_with_following_off_a_command_is_refused_and_never_sent_on(self):
        control = MoonrakerJobControl(follow_redirects=False)
        result = control.cancel_job(self.base)
        self.assertTrue(result.allowed)
        self.assertFalse(result.executed)
        self.assertIn("redirect (HTTP 302)", result.reason)
        self.assertEqual(result.http_status, 302)
        self.assertEqual(_Target.seen, [])
        self.assertEqual(self.redirector_class.requests, [("POST", "/printer/print/cancel")])

    def test_with_following_off_the_file_check_stops_at_the_redirect(self):
        control = MoonrakerJobControl(follow_redirects=False)
        problem = control._file_problem(self.base, "part.gcode", 2.0)
        self.assertIn("redirect (HTTP 302)", problem or "")
        self.assertEqual(_Target.seen, [])

    def test_an_answer_without_a_redirect_is_the_same_with_following_off(self):
        status = MoonrakerProbe(single_request=False, follow_redirects=False).fetch(f"http://127.0.0.1:{self.target.server_address[1]}")
        self.assertEqual(status.state, MachineState.IDLE)

    def test_the_configuration_key(self):
        base = {"mqtt": {"host": "127.0.0.1"}}
        self.assertTrue(parse_config(dict(base, moonraker={"url": "http://127.0.0.1:7125"})).moonraker.follow_redirects)
        self.assertFalse(parse_config(dict(base, moonraker={"url": "http://127.0.0.1:7125", "follow_redirects": False})).moonraker.follow_redirects)
        for bad in ("false", 0, None):
            with self.subTest(bad=bad), self.assertRaises(ConfigError):
                parse_config(dict(base, moonraker={"url": "http://127.0.0.1:7125", "follow_redirects": bad}))


if __name__ == "__main__":
    unittest.main()
