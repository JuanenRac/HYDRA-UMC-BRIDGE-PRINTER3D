<!-- =============================================================================
HYDRA-UMC-BRIDGE-PRINTER3D - 3D-printer software bridge
Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
GPL-3.0-or-later - see LICENSE
============================================================================= -->

# HYDRA-UMC-BRIDGE-PRINTER3D

🇺🇸 **English** | 🇪🇸 [Español](README_spa.md) | 🇫🇷 [Français](README_fra.md) | 🇮🇹 [Italiano](README_ita.md) | 🇩🇪 [Deutsch](README_deu.md) | 🇨🇳 [简体中文](README_zho.md) | 🇯🇵 [日本語](README_jpn.md)

High-level coordinator for open 3D-printing software and HYDRA-UMC robotic
auxiliaries. Native printer firmware remains responsible for motion, heaters,
thermal protection and machine interlocks.

## Architecture

```text
Moonraker/Klipper <-> BRIDGE-PRINTER3D <-> SDK <-> SERVER <-> cell safety
```

The first adapter consumes Moonraker's `/printer/info` readiness response.
Only `ready` maps to an idle printer. Startup, shutdown and error states fail
closed; a robot cannot be planned around a printer that is not ready.

## Build & Test

Run `build-test.bat` on Windows or `bash build-test.sh` on Linux. It compiles
and tests the response parser and safety gate without sending G-code, changing
versions or touching a printer. Real commands require a tested profile,
authentication and physical safety review.

## Related Projects

| Project | Role |
| --- | --- |
| [HYDRA-UMC-SDK](https://github.com/JuanenRac/HYDRA-UMC-SDK) | Shared contract. |
| [HYDRA-UMC-SERVER](https://github.com/JuanenRac/HYDRA-UMC-SERVER) | Authorised coordination endpoint. |
| [HYDRA-UMC-SAFETY-ZONES](https://github.com/JuanenRac/HYDRA-UMC-SAFETY-ZONES) | Future workspace evidence. |

## Status

Version `0.0.1` includes a local, tested Moonraker readiness adapter. It has
not controlled a real printer, hotend or robot.

## ⚙️ Versioned Build

`build-test.bat` / `build-test.sh` validate without modifying the repository.
`build.bat` / `build.sh` run that validation first and, only on success,
synchronize the native package version, manifest and `CHANGELOG.md`. There is
no live printer `run` command until a real integration is validated.
