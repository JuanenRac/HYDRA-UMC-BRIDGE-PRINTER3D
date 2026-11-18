# =============================================================================
# HYDRA-UMC-BRIDGE-PRINTER3D - file facts (sha256 and profile) tests
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
import hashlib
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

from hydra_umc_bridge_printer3d.file_facts import MoonrakerFileFacts, profile_from_header
from hydra_umc_bridge_printer3d.service import ConfigError, build_bridge, parse_config

GCODE = b"; generated\n; hydra_profile: prusa-mk4\nG28\nG1 X10\n"


class _Handler(BaseHTTPRequestHandler):
    files: dict[str, tuple[bytes, float]] = {}
    downloads: list[str] = []
    seen_keys: list[str | None] = []

    def log_message(self, *args):  # noqa: ANN002
        pass

    def do_GET(self):  # noqa: N802
        cls = type(self)
        cls.seen_keys.append(self.headers.get("X-Api-Key"))
        url = urlparse(self.path)
        if url.path == "/server/files/metadata":
            name = parse_qs(url.query).get("filename", [""])[0]
            entry = cls.files.get(name)
            if entry is None:
                self.send_error(404)
                return
            body = json.dumps({"result": {"size": len(entry[0]), "modified": entry[1]}}).encode()
        elif url.path.startswith("/server/files/gcodes/"):
            name = unquote(url.path[len("/server/files/gcodes/"):])
            entry = cls.files.get(name)
            if entry is None:
                self.send_error(404)
                return
            cls.downloads.append(name)
            body = entry[0]
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class FileFactsTests(unittest.TestCase):
    def setUp(self):
        _Handler.files = {"part.gcode": (GCODE, 100.0), "plain.gcode": (b"G28\n", 5.0), "dir/a b.gcode": (GCODE, 7.0)}
        _Handler.downloads = []
        _Handler.seen_keys = []
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(5)

    def test_sha256_is_computed_from_the_file_and_profile_from_its_header(self):
        sha, profile = MoonrakerFileFacts(self.base)("part.gcode")
        self.assertEqual(hashlib.sha256(GCODE).hexdigest(), sha)
        self.assertEqual("prusa-mk4", profile)

    def test_a_file_without_header_has_no_profile(self):
        sha, profile = MoonrakerFileFacts(self.base)("plain.gcode")
        self.assertEqual(hashlib.sha256(b"G28\n").hexdigest(), sha)
        self.assertIsNone(profile)

    def test_cache_by_name_and_mtime_downloads_once(self):
        facts = MoonrakerFileFacts(self.base)
        first = facts("part.gcode")
        self.assertEqual(first, facts("part.gcode"))
        self.assertEqual(["part.gcode"], _Handler.downloads)
        _Handler.files["part.gcode"] = (b"G28\nG1 X1\n", 101.0)
        changed = facts("part.gcode")
        self.assertNotEqual(first[0], changed[0])
        self.assertEqual(2, len(_Handler.downloads))

    def test_a_file_over_the_ceiling_is_not_downloaded(self):
        self.assertEqual((None, None), MoonrakerFileFacts(self.base, max_bytes=10)("part.gcode"))
        self.assertEqual([], _Handler.downloads)

    def test_zero_ceiling_turns_it_off(self):
        self.assertEqual((None, None), MoonrakerFileFacts(self.base, max_bytes=0)("part.gcode"))
        self.assertEqual([], _Handler.seen_keys)

    def test_unknown_file_and_unreachable_server_give_nothing(self):
        self.assertEqual((None, None), MoonrakerFileFacts(self.base)("missing.gcode"))
        self.assertEqual((None, None), MoonrakerFileFacts("http://127.0.0.1:1", timeout_seconds=1.0)("part.gcode"))
        self.assertEqual((None, None), MoonrakerFileFacts("not a url")("part.gcode"))

    def test_name_with_a_space_and_folder_is_quoted(self):
        sha, _profile = MoonrakerFileFacts(self.base)("dir/a b.gcode")
        self.assertEqual(hashlib.sha256(GCODE).hexdigest(), sha)

    def test_api_key_is_sent(self):
        MoonrakerFileFacts(self.base, "k-1")("plain.gcode")
        self.assertTrue(_Handler.seen_keys)
        self.assertTrue(all(key == "k-1" for key in _Handler.seen_keys))

    def test_a_growing_download_is_cut_at_the_ceiling(self):
        facts = MoonrakerFileFacts(self.base, max_bytes=len(GCODE))
        self.assertEqual(hashlib.sha256(GCODE).hexdigest(), facts("part.gcode")[0])
        # the size announced by the metadata is honest but the body is longer: the read stops at the ceiling
        _Handler.files["part.gcode"] = (GCODE + b"G1 X99\n", 100.0)
        original = facts._stamp
        facts._stamp = lambda base, name: (100.5, len(GCODE))  # type: ignore[method-assign]
        self.assertEqual((None, None), facts("part.gcode"))
        facts._stamp = original  # type: ignore[method-assign]


class HeaderTests(unittest.TestCase):
    def test_profile_comment_forms(self):
        self.assertEqual("a-1", profile_from_header(b";hydra_profile:a-1\r\nG28\n"))
        self.assertEqual("x", profile_from_header(b"; hydra_profile:   x  \n"))
        self.assertIsNone(profile_from_header(b"; other: x\nG28\n"))
        self.assertIsNone(profile_from_header(b"; hydra_profile: has space\n"))
        self.assertIsNone(profile_from_header(b"; hydra_profile:\n"))
        self.assertIsNone(profile_from_header(b""))

    def test_profile_beyond_the_header_window_is_ignored(self):
        self.assertIsNone(profile_from_header(b"; filler\n" * 2000 + b"; hydra_profile: late\n"))


class ConfigTests(unittest.TestCase):
    BASE = {"moonraker": {"url": "http://127.0.0.1:7125"}}

    def test_default_and_override(self):
        self.assertEqual(256 * 1024 * 1024, parse_config(self.BASE).file_facts_max_bytes)
        self.assertEqual(0, parse_config({**self.BASE, "file_facts": {"max_bytes": 0}}).file_facts_max_bytes)

    def test_bad_values_are_refused(self):
        for table in ({"max_bytes": -1}, {"max_bytes": "big"}, {"other": 1}):
            with self.assertRaises(ConfigError):
                parse_config({**self.BASE, "file_facts": table})

    def test_the_bridge_is_built_with_the_file_facts(self):
        bridge = build_bridge(parse_config(self.BASE))
        self.assertIsInstance(bridge._file_facts, MoonrakerFileFacts)


if __name__ == "__main__":
    unittest.main()
