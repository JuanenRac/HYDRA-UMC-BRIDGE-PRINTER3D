#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-BRIDGE-PRINTER3D - Read-only slicer artifact inspection CLI
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Emit conservative JSON evidence for one local print artifact."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from hydra_umc_bridge_printer3d.artifacts import PrintArtifactKind, inspect_artifact  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect a print artifact without controlling a printer.")
    parser.add_argument("artifact", help="Local G-code, 3MF or resin-slice candidate")
    arguments = parser.parse_args()
    result = inspect_artifact(arguments.artifact)
    print(json.dumps(result.as_json(), indent=2, sort_keys=True))
    return 0 if result.available and result.kind is not PrintArtifactKind.UNKNOWN else 2


if __name__ == "__main__":
    raise SystemExit(main())
