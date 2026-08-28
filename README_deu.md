<!-- =============================================================================
HYDRA-UMC-BRIDGE-PRINTER3D - Bruecke fuer 3D-Drucker-Software
Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
GPL-3.0-or-later - see LICENSE
============================================================================= -->

# HYDRA-UMC-BRIDGE-PRINTER3D

🇺🇸 [English](README.md) | 🇪🇸 [Español](README_spa.md) | 🇫🇷 [Français](README_fra.md) | 🇮🇹 [Italiano](README_ita.md) | 🇩🇪 **Deutsch** | 🇨🇳 [简体中文](README_zho.md) | 🇯🇵 [日本語](README_jpn.md)

Koordinator auf hoher Ebene für offene 3D-Druck-Software und robotische
HYDRA-UMC-Hilfseinrichtungen. Die native Drucker-Firmware bleibt für Bewegung,
Heizungen, Wärmeschutz und Maschinenverriegelungen verantwortlich.

## Architektur

```text
Moonraker/Klipper <-> BRIDGE-PRINTER3D <-> SDK <-> SERVER <-> Zellsicherheit
```

Der erste Adapter verarbeitet die Moonraker-Bereitschaftsantwort
`/printer/info`. Nur `ready` wird einem inaktiven Drucker zugeordnet. Start-,
Abschalt- und Fehlerzustände sperren sicher; ein Roboter kann nicht für einen
nicht bereiten Drucker geplant werden.

## Build & Test

Unter Windows `build-test.bat` oder unter Linux `bash build-test.sh` ausführen.
Dabei werden Response-Parser und Sicherheitsgatter kompiliert und getestet,
ohne G-Code zu senden, Versionen zu ändern oder einen Drucker anzufassen.
Reale Befehle benötigen ein erprobtes Profil, Authentifizierung und eine
physische Sicherheitsprüfung.

## Verwandte Projekte

| Projekt | Rolle |
| --- | --- |
| [HYDRA-UMC-SDK](https://github.com/JuanenRac/HYDRA-UMC-SDK) | Gemeinsamer Vertrag. |
| [HYDRA-UMC-SERVER](https://github.com/JuanenRac/HYDRA-UMC-SERVER) | Autorisierter Koordinierungsendpunkt. |
| [HYDRA-UMC-SAFETY-ZONES](https://github.com/JuanenRac/HYDRA-UMC-SAFETY-ZONES) | Zukünftige Nachweise für den Arbeitsbereich. |

## Status

Version `0.0.1` enthält einen lokalen, getesteten Moonraker-
Bereitschaftsadapter. Sie hat keinen realen Drucker, kein Hotend und keinen
Roboter gesteuert.
