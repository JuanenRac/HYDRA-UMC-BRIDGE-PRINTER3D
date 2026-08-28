<!-- =============================================================================
HYDRA-UMC-BRIDGE-PRINTER3D - Bridge software di stampa 3D
Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
GPL-3.0-or-later - see LICENSE
============================================================================= -->

# HYDRA-UMC-BRIDGE-PRINTER3D

🇺🇸 [English](README.md) | 🇪🇸 [Español](README_spa.md) | 🇫🇷 [Français](README_fra.md) | 🇮🇹 **Italiano** | 🇩🇪 [Deutsch](README_deu.md) | 🇨🇳 [简体中文](README_zho.md) | 🇯🇵 [日本語](README_jpn.md)

Coordinatore ad alto livello per software di stampa 3D aperto e ausiliari robotici
HYDRA-UMC. Il firmware nativo mantiene movimento, heater, protezione termica e interlock.

## Architettura

```text
Moonraker/Klipper <-> BRIDGE-PRINTER3D <-> SDK <-> SERVER <-> sicurezza cella
```

Il primo adattatore elabora `/printer/info` Moonraker. Solo `ready` significa
stampante inattiva; avvio, arresto o errore chiudono la porta di sicurezza.

## Compilare e testare

Eseguire `build-test.bat` su Windows o `bash build-test.sh` su Linux. Prova parser
e porta senza inviare G-code, toccare stampante o cambiare versione. I comandi reali
richiedono profilo testato, autenticazione e revisione di sicurezza.

## Progetti correlati

| Progetto | Ruolo |
| --- | --- |
| [HYDRA-UMC-SDK](https://github.com/JuanenRac/HYDRA-UMC-SDK) | Contratto condiviso. |
| [HYDRA-UMC-SERVER](https://github.com/JuanenRac/HYDRA-UMC-SERVER) | Punto di coordinamento autorizzato. |
| [HYDRA-UMC-SAFETY-ZONES](https://github.com/JuanenRac/HYDRA-UMC-SAFETY-ZONES) | Evidenza futura dello spazio di lavoro. |

## Stato

La versione `0.0.1` include adattatore Moonraker locale testato. Non ha controllato
stampante reale, hotend o robot.
