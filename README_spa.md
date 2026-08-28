<!-- =============================================================================
HYDRA-UMC-BRIDGE-PRINTER3D - Puente de software de impresión 3D
Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
GPL-3.0-or-later - see LICENSE
============================================================================= -->

# HYDRA-UMC-BRIDGE-PRINTER3D

🇺🇸 [English](README.md) | 🇪🇸 **Español** | 🇫🇷 [Français](README_fra.md) | 🇮🇹 [Italiano](README_ita.md) | 🇩🇪 [Deutsch](README_deu.md) | 🇨🇳 [简体中文](README_zho.md) | 🇯🇵 [日本語](README_jpn.md)

Coordinador de alto nivel para software de impresión 3D abierto y auxiliares
robóticos HYDRA-UMC. El firmware nativo conserva movimiento, heaters, protección
térmica e interlocks de máquina.

## Arquitectura

```text
Moonraker/Klipper <-> BRIDGE-PRINTER3D <-> SDK <-> SERVER <-> seguridad de celda
```

El primer adaptador procesa la respuesta Moonraker `/printer/info`. Solo `ready`
equivale a impresora inactiva; estados de inicio, apagado o error cierran la puerta
para que ningún robot se planifique junto a una impresora no disponible.

## Compilar y probar

Ejecuta `build-test.bat` en Windows o `bash build-test.sh` en Linux. Compila y
prueba el parser y la puerta sin enviar G-code, tocar impresora ni cambiar versión.
Los comandos reales requieren perfil probado, autenticación y revisión de seguridad física.

## Proyectos relacionados

| Proyecto | Función |
| --- | --- |
| [HYDRA-UMC-SDK](https://github.com/JuanenRac/HYDRA-UMC-SDK) | Contrato compartido. |
| [HYDRA-UMC-SERVER](https://github.com/JuanenRac/HYDRA-UMC-SERVER) | Punto de coordinación autorizado. |
| [HYDRA-UMC-SAFETY-ZONES](https://github.com/JuanenRac/HYDRA-UMC-SAFETY-ZONES) | Evidencia futura del espacio de trabajo. |

## Estado

La versión `0.0.1` incluye adaptador Moonraker local y probado. No ha controlado
una impresora real, hotend ni robot.

## ⚙️ Compilación con versión

`build-test.bat` / `build-test.sh` validan sin modificar el repositorio.
`build.bat` / `build.sh` ejecutan primero esa validación y, solo si es
correcta, sincronizan la versión nativa, el manifiesto y `CHANGELOG.md`. No
existe un comando `run` de impresora hasta validar una integración real.
