<!-- =============================================================================
HYDRA-UMC-BRIDGE-PRINTER3D - Pont logiciel d'impression 3D
Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
GPL-3.0-or-later - see LICENSE
============================================================================= -->

# HYDRA-UMC-BRIDGE-PRINTER3D

🇺🇸 [English](README.md) | 🇪🇸 [Español](README_spa.md) | 🇫🇷 **Français** | 🇮🇹 [Italiano](README_ita.md) | 🇩🇪 [Deutsch](README_deu.md) | 🇨🇳 [简体中文](README_zho.md) | 🇯🇵 [日本語](README_jpn.md)

Coordinateur de haut niveau pour logiciel d'impression 3D libre et auxiliaires
robotiques HYDRA-UMC. Le firmware natif conserve mouvement, chauffages, protection
thermique et interlocks de machine.

## Architecture

```text
Moonraker/Klipper <-> BRIDGE-PRINTER3D <-> SDK <-> SERVER <-> sécurité cellule
```

Le premier adaptateur traite la réponse Moonraker `/printer/info`. Seul `ready`
signifie imprimante inactive; démarrage, arrêt ou erreur ferment la porte afin
qu'aucun robot ne soit planifié près d'une imprimante indisponible.

## Compiler et tester

Exécutez `build-test.bat` sous Windows ou `bash build-test.sh` sous Linux. Il
teste parser et porte sans envoyer G-code, modifier imprimante ou version. Les
commandes réelles exigent profil testé, authentification et revue de sécurité.

## Projets liés

| Projet | Rôle |
| --- | --- |
| [HYDRA-UMC-SDK](https://github.com/JuanenRac/HYDRA-UMC-SDK) | Contrat partagé. |
| [HYDRA-UMC-SERVER](https://github.com/JuanenRac/HYDRA-UMC-SERVER) | Point de coordination autorisé. |
| [HYDRA-UMC-SAFETY-ZONES](https://github.com/JuanenRac/HYDRA-UMC-SAFETY-ZONES) | Future preuve de l'espace de travail. |

## État

La version `0.0.1` contient un adaptateur Moonraker local testé. Elle n'a contrôlé
ni imprimante réelle, ni hotend, ni robot.

## ⚙️ Compilation versionnée

`build-test.bat` / `build-test.sh` valident sans modifier le dépôt.
`build.bat` / `build.sh` exécutent d'abord cette validation puis, uniquement
en cas de succès, synchronisent version native, manifeste et `CHANGELOG.md`.
Il n'existe pas de commande `run` imprimante avant une intégration réelle.
