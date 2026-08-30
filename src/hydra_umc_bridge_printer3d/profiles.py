# =============================================================================
# HYDRA-UMC-BRIDGE-PRINTER3D - Print artifact profile boundary
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""Match read-only artifact evidence to a declared profile without authorizing a print."""

from __future__ import annotations

from dataclasses import dataclass

from .artifacts import PrintArtifact, PrintArtifactKind, PrintTechnology


@dataclass(frozen=True)
class PrintProfile:
    """A local declaration of compatible artifact kinds for one printer profile."""

    profile_id: str
    technology: PrintTechnology
    accepted_kinds: frozenset[PrintArtifactKind]


@dataclass(frozen=True)
class ArtifactProfileAssessment:
    """Compatibility evidence only; it can never grant execution authority."""

    profile_compatible: bool
    execution_authorized: bool
    reason: str


def assess_artifact_profile(profile: PrintProfile, artifact: PrintArtifact) -> ArtifactProfileAssessment:
    """Compare declared metadata conservatively, retaining native-controller authority."""

    if not isinstance(profile.profile_id, str) or not profile.profile_id.strip():
        return ArtifactProfileAssessment(False, False, "profile identifier is missing")
    if not artifact.available or artifact.kind is PrintArtifactKind.UNKNOWN:
        return ArtifactProfileAssessment(False, False, "artifact is unavailable or unknown")
    if artifact.technology is not profile.technology:
        return ArtifactProfileAssessment(False, False, "artifact technology does not match the declared profile")
    if artifact.kind not in profile.accepted_kinds:
        return ArtifactProfileAssessment(False, False, "artifact kind is not declared for this profile")
    return ArtifactProfileAssessment(True, False, "metadata is compatible; native controller validation and physical review remain required")
