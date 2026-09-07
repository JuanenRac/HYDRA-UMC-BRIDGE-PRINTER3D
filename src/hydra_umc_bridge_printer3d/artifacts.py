# =============================================================================
# HYDRA-UMC-BRIDGE-PRINTER3D - Read-only slicer artifact inspection
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Identify print artifacts without unpacking, executing or sending them."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path


class PrintTechnology(StrEnum):
    """Technology indicated by an artifact's filename, never by trust alone."""

    FDM = "fdm"
    RESIN = "resin"
    UNKNOWN = "unknown"


class PrintArtifactKind(StrEnum):
    """Conservative artifact categories understood by the bridge."""

    FDM_GCODE = "fdm-gcode"
    FDM_GCODE_3MF = "fdm-gcode-3mf"
    PROJECT_3MF = "project-3mf"
    RESIN_SLICE = "resin-slice"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class PrintArtifact:
    """Read-only evidence about a candidate job; it is never an admission."""

    available: bool
    kind: PrintArtifactKind
    technology: PrintTechnology
    source_hint: str
    message: str
    size_bytes: int = 0
    sha256: str = ""

    def as_json(self) -> dict[str, object]:
        """Return JSON-safe evidence without disclosing the artifact contents."""

        values = asdict(self)
        values["kind"] = self.kind.value
        values["technology"] = self.technology.value
        return values


_FDM_GCODE_SUFFIXES = {".gcode", ".gco", ".gc"}
_RESIN_SLICE_SUFFIXES = {".ctb", ".goo", ".photon", ".pwmo", ".pws", ".sl1"}


def _classify_name(path: Path) -> tuple[PrintArtifactKind, PrintTechnology]:
    name = path.name.lower()
    if name.endswith(".gcode.3mf"):
        return PrintArtifactKind.FDM_GCODE_3MF, PrintTechnology.FDM
    if path.suffix.lower() in _FDM_GCODE_SUFFIXES:
        return PrintArtifactKind.FDM_GCODE, PrintTechnology.FDM
    if path.suffix.lower() == ".3mf":
        return PrintArtifactKind.PROJECT_3MF, PrintTechnology.UNKNOWN
    if path.suffix.lower() in _RESIN_SLICE_SUFFIXES:
        return PrintArtifactKind.RESIN_SLICE, PrintTechnology.RESIN
    return PrintArtifactKind.UNKNOWN, PrintTechnology.UNKNOWN


def _sha256_and_preview(path: Path, preview_bytes: int = 65536) -> tuple[str, bytes]:
    """Hash a local file while retaining only a bounded textual preview."""

    digest = hashlib.sha256()
    preview = bytearray()
    with path.open("rb") as artifact:
        while block := artifact.read(1024 * 1024):
            digest.update(block)
            if len(preview) < preview_bytes:
                preview.extend(block[: preview_bytes - len(preview)])
    return digest.hexdigest(), bytes(preview)


def _slicer_hint(kind: PrintArtifactKind, preview: bytes) -> str:
    """Recognize familiar G-code comments; a missing marker remains unknown."""

    if kind is not PrintArtifactKind.FDM_GCODE:
        return "unknown-slicer"
    text = preview.decode("utf-8", errors="replace").lower()
    if "orcaslicer" in text or "orca slicer" in text:
        return "OrcaSlicer"
    if "cura_" in text or "ultimaker cura" in text:
        return "Ultimaker Cura"
    if "prusaslicer" in text or "slic3r" in text:
        return "PrusaSlicer"
    if "bambustudio" in text or "bambu studio" in text:
        return "Bambu Studio"
    return "unknown-slicer"


def inspect_artifact(candidate: str | Path) -> PrintArtifact:
    """Inspect a local print artifact without unpacking, parsing commands or I/O to a printer."""

    try:
        path = Path(candidate)
        if not path.is_file():
            return PrintArtifact(False, PrintArtifactKind.UNKNOWN, PrintTechnology.UNKNOWN, "unknown-slicer", "artifact is not a regular file")
        kind, technology = _classify_name(path)
        digest, preview = _sha256_and_preview(path)
        if kind is PrintArtifactKind.UNKNOWN:
            return PrintArtifact(True, kind, technology, "unknown-slicer", "artifact type is not admitted for inspection", path.stat().st_size, digest)
        message = "identified read-only; no command was parsed, unpacked or sent to a printer"
        return PrintArtifact(True, kind, technology, _slicer_hint(kind, preview), message, path.stat().st_size, digest)
    except (OSError, TypeError, ValueError) as error:
        return PrintArtifact(False, PrintArtifactKind.UNKNOWN, PrintTechnology.UNKNOWN, "unknown-slicer", f"artifact inspection failed safely: {error}")
