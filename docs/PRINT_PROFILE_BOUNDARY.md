<!-- =============================================================================
HYDRA-UMC-BRIDGE-PRINTER3D - Print profile admission boundary
Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
GPL-3.0-or-later - see LICENSE
============================================================================= -->

# Print Profile Admission Boundary

`PrintProfile` matches read-only artifact evidence to a declared printer profile. It checks only three facts: a non-empty profile identifier, the declared print technology, and an explicit set of accepted artifact kinds.

`assess_artifact_profile()` can report `profile_compatible: true`, but **always** returns `execution_authorized: false`. Matching a G-code, 3MF or resin-slice filename and hash proves neither that the profile is physically correct nor that it is safe to print.

Before a future implementation can upload or start any print, it must separately establish: authenticated native controller identity, model/firmware compatibility, nozzle/material/volume limits, an approved command policy, independent safety state and a physical validation procedure. This module opens no network connection and holds no printer credential or command path.

For an offline review, run `py tools/assess_print_profile.py profile.json job.gcode`. The profile JSON contains only `profile_id`, `technology` (`fdm` or `resin`) and `accepted_kinds`; the resulting JSON still reports `execution_authorized: false` for every input.
