#!/usr/bin/env python3
# =============================================================================
# HYDRA-UMC-BRIDGE-PRINTER3D - Offline print profile assessment CLI
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Compare one local artifact with one local profile without a printer connection."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from hydra_umc_bridge_printer3d.artifacts import PrintArtifactKind, PrintTechnology, inspect_artifact  # noqa: E402
from hydra_umc_bridge_printer3d.profiles import PrintProfile, assess_artifact_profile  # noqa: E402


def load_profile(path: Path) -> PrintProfile:
    """Load only the small local compatibility declaration used by this CLI."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("profile JSON must be an object")
    profile_id = payload.get("profile_id")
    technology = PrintTechnology(payload.get("technology"))
    kinds = payload.get("accepted_kinds")
    if not isinstance(profile_id, str) or not isinstance(kinds, list) or not all(isinstance(kind, str) for kind in kinds):
        raise ValueError("profile_id and accepted_kinds must be strings")
    return PrintProfile(profile_id, technology, frozenset(PrintArtifactKind(kind) for kind in kinds))


def main() -> int:
    parser = argparse.ArgumentParser(description="Assess local print-artifact metadata without contacting a printer.")
    parser.add_argument("profile", type=Path, help="Local JSON profile declaration")
    parser.add_argument("artifact", help="Local artifact to inspect")
    arguments = parser.parse_args()
    try:
        result = assess_artifact_profile(load_profile(arguments.profile), inspect_artifact(arguments.artifact))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"profile_compatible": False, "execution_authorized": False, "reason": f"profile assessment failed safely: {error}"}, indent=2))
        return 2
    print(json.dumps({"profile_compatible": result.profile_compatible, "execution_authorized": result.execution_authorized, "reason": result.reason}, indent=2))
    return 0 if result.profile_compatible else 2


if __name__ == "__main__":
    raise SystemExit(main())
