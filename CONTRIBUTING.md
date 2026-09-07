<!-- =============================================================================
HYDRA-UMC-BRIDGE-PRINTER3D - Contribution guide
Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
GPL-3.0-or-later - see LICENSE
============================================================================= -->

# Contributing

Keep this bridge a coordinator: printer firmware and its controller retain
motion, heater, thermal-protection and machine-interlock authority. New
adapters must pass the shared SDK job gate and fail closed on unknown state.

Before opening a change, run `build-test.bat` on Windows or `bash build-test.sh`
on Linux. Add a focused test for every readiness mapping or admission rule
changed. Hardware behavior must identify its tested interface and safe failure
mode; unverified printer support is not ready support.
