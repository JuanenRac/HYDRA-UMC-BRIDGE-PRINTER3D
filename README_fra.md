<!-- =============================================================================
HYDRA-UMC-BRIDGE-PRINTER3D - Pont logiciel pour impression 3D
Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
GPL-3.0-or-later - see LICENSE
============================================================================= -->

<p align="center">
  <img src="images/HYDRA_UMC_BANNER.svg" alt="Bannière HYDRA-UMC-BRIDGE-PRINTER3D" width="100%">
</p>

# 🖨️ HYDRA-UMC-BRIDGE-PRINTER3D

<p align="center"><a href="README.md">🇺🇸 English</a> | <a href="README_spa.md">🇪🇸 Español</a> | 🇫🇷 <b>Français</b> | <a href="README_ita.md">🇮🇹 Italiano</a> | <a href="README_deu.md">🇩🇪 Deutsch</a> | <a href="README_zho.md">🇨🇳 简体中文</a> | <a href="README_jpn.md">🇯🇵 日本語</a></p>

### 🌡️ Pont de coordination à sécurité intrinsèque pour logiciels d'impression 3D ouverts

<p align="left">
  <img src="https://img.shields.io/badge/Licence-GPL%203.0-blue.svg" alt="GPL 3.0">
  <img src="https://img.shields.io/badge/Python-3.11%2B-3776AB.svg" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/Safety-Fails%20Closed-red.svg" alt="Sécurité intrinsèque">
</p>

---

## 1. 🛠️ APERÇU TECHNIQUE

**HYDRA-UMC-BRIDGE-PRINTER3D** est le coordinateur haut niveau pour les logiciels d'impression 3D ouverts (Moonraker/Klipper) et les auxiliaires robotiques HYDRA-UMC. Le firmware natif de l'imprimante reste responsable en permanence du mouvement, des chauffages, de la protection thermique et des interverrouillages machine — ce pont ne fait que lire la disponibilité et coordonner des auxiliaires autour de cela.

Il appartient à la famille **External Automation Bridges** : un ensemble de dépôts frères (CNC, LASER, OPENPNP, PRINTER3D, ROS2) qui partagent le même contrat de sécurité de `HYDRA-UMC-SDK`, afin qu'aucun pont ne puisse inventer sa propre définition du « sûr pour travailler ».

### Fonctionnalités clés :
* ✅ **Sonde de disponibilité Moonraker, réelle :** `moonraker.py` — `MoonrakerProbe` consomme le point de terminaison documenté `/printer/info` de Moonraker avec un petit client basé uniquement sur la bibliothèque standard (`urlopen` + `json`) — aucune dépendance supplémentaire au-delà de la bibliothèque standard Python. *(implémenté, testé dans `tests/test_moonraker.py`)*
* ✅ **Analyse d'état à sécurité intrinsèque, réelle :** `parse_info()` ne mappe que la chaîne littérale `"ready"` vers `MachineState.IDLE` ; `startup`/`shutdown`/`error` sont mappés vers `FAULT`, et tout le reste (y compris une réponse malformée) vers `OFFLINE` — jamais vers un état qui permettrait de planifier un robot autour de l'imprimante. *(implémenté)*
* ✅ **Portail de sécurité partagé, réel :** chaque tâche observée est réévaluée via `evaluate_job()` du `bridge_contract` de `HYDRA-UMC-SDK`, le même portail utilisé par tous les ponts frères et HYDRA-UMC-SERVER. *(implémenté)*
* ✅ **Build/test non mutant :** `build-test.bat`/`.sh` compilent l'analyseur de réponse et le portail de sécurité sans envoyer de G-code, changer de version ni toucher une imprimante. *(implémenté, voir COMPILATION & EXÉCUTION ci-dessous)*
* 🔜 **Contrôle réel de l'imprimante (commandes G-code)** — reporté jusqu'à disposer d'un profil testé, d'une authentification et d'une revue de sécurité physique. *(prévu)*

---

## 2. 🔄 FLUX DE COORDINATION DE L'IMPRIMANTE

```mermaid
flowchart LR
    PRINTER["Moonraker / Klipper<br/>(/printer/info)"] --> BRIDGE["BRIDGE-PRINTER3D<br/>MoonrakerProbe.parse_info()"]
    BRIDGE -- "BridgeJob + MachineState observé" --> SDK["HYDRA-UMC-SDK<br/>evaluate_job()"]
    SDK -- GateDecision --> SERVER["HYDRA-UMC-SERVER"]
    SERVER -- "tâche / abandon" --> CELL["Sécurité de cellule"]
```

---

## 3. 🧱 ARCHITECTURE ET CHOIX DE CONCEPTION

* **Pourquoi seul l'état littéral `"ready"` de Moonraker est mappé vers le repos.** Le mappage d'état de `parse_info()` est délibérément étroit : `ready` → `IDLE`, `startup`/`shutdown`/`error` → `FAULT` (sécurité intrinsèque), et toute autre valeur ou valeur absente → `OFFLINE`. Il n'y a aucune hypothèse « par défaut sûr » pour un état d'imprimante non reconnu.
* **Pourquoi l'analyse est une `@staticmethod` séparée de la récupération réseau.** `MoonrakerProbe.parse_info()` prend un simple `dict` et est entièrement testable unitairement sans appel réseau ni imprimante en fonctionnement ; `fetch()` est la pièce mince et nécessairement réseau qui l'appelle. La logique liée à la sécurité vit dans la partie qui n'a jamais besoin d'une imprimante réelle pour être testée.
* **Pourquoi la sonde utilise `urlopen`/`json` de la bibliothèque standard plutôt qu'une bibliothèque cliente Moonraker.** Limiter la surface de dépendance à la bibliothèque standard Python garde l'analyse liée à la sécurité minimale, auditable et exempte des propres hypothèses d'un client tiers sur les tentatives, délais ou gestion d'erreurs.
* **Pourquoi le pont construit un nouveau `BridgeJob` et délègue au `evaluate_job()` partagé plutôt que d'écrire sa propre logique d'acceptation/rejet.** Les cinq External Automation Bridges (CNC, LASER, OPENPNP, PRINTER3D, ROS2) réutilisent exactement le même `bridge_contract` de `HYDRA-UMC-SDK`, afin que « ce qui compte comme sûr pour démarrer une tâche » ne puisse pas diverger silencieusement entre eux.
* **Pourquoi les commandes réelles (G-code) nécessitent d'abord un profil testé, une authentification et une revue de sécurité physique.** L'API de Moonraker peut accepter du G-code arbitraire ; l'envoyer sans profil validé ni authentification contournerait précisément la vérification de disponibilité que ce pont existe pour faire respecter.
* **Comment cela s'intègre dans le reste de l'écosystème.** BRIDGE-PRINTER3D se situe entre Moonraker/Klipper et `HYDRA-UMC-SDK` → `HYDRA-UMC-SERVER` → sécurité de cellule : il coordonne le travail robotique auxiliaire autour de l'imprimante, il ne remplace jamais le firmware natif, les chauffages ni la protection thermique.

---

## 📂 STRUCTURE DES RÉPERTOIRES

```text
HYDRA-UMC-BRIDGE-PRINTER3D/
├── src/
│   └── hydra_umc_bridge_printer3d/
│       ├── __init__.py
│       └── moonraker.py         # Portail de sécurité MoonrakerProbe + PrinterBridge
├── tests/
│   └── test_moonraker.py        # Tests d'analyse de disponibilité et de portail de sécurité
├── tools/
│   ├── build_test.py            # Compilateur + lanceur de tests non mutant (build-test.bat/.sh)
│   └── bump_version.py          # Synchronise pyproject.toml, manifeste et CHANGELOG.md
├── build-test.bat / build-test.sh  # Valide uniquement, ne modifie jamais le dépôt
├── build.bat / build.sh            # Valide puis, si succès, incrémente version + CHANGELOG
├── pyproject.toml               # Métadonnées du paquet ; dépend de HYDRA-UMC-SDK (git)
├── hydra-umc.project.json       # Manifeste de l'écosystème (version, maturité, famille)
├── CHANGELOG.md
├── CODE_OF_CONDUCT.md / CONTRIBUTING.md / SECURITY.md / SUPPORT.md
├── LICENSE / LICENSE.md
└── README.md / README_*.md      # Ce fichier et ses 6 traductions
```

---

## 4. ⚙️ COMPILATION ET EXÉCUTION

Nécessite Python 3.11+. `tools/build_test.py` attend que `HYDRA-UMC-SDK` soit cloné en tant que répertoire frère (`../HYDRA-UMC-SDK`) ou indiqué via la variable d'environnement `HYDRA_UMC_SDK_ROOT`.

```bash
# Windows
build-test.bat      # validation uniquement — pas de changement de version/CHANGELOG
build.bat            # valide puis, si succès, incrémente version + CHANGELOG

# Linux/macOS
bash build-test.sh
bash build.sh
```

`build-test` compile chaque module sous `src/` avec `py_compile` et exécute la suite complète `unittest` (`tests/test_moonraker.py`), démontrant l'analyse de la réponse de disponibilité et le portail de sécurité — il n'envoie aucun G-code, ne touche aucune imprimante et ne modifie jamais le dépôt. `build` exécute d'abord cette même validation et, seulement en cas de succès, appelle `tools/bump_version.py` pour synchroniser la version dans `pyproject.toml`, `hydra-umc.project.json` et `CHANGELOG.md`. Il n'existe pas encore de commande `run` imprimante réelle — cela nécessite d'abord un profil testé, une authentification et une revue de sécurité physique.

---

## ✅ ÉTAT ACTUEL ET PROCHAINES ÉTAPES

**Réel aujourd'hui :** version `0.0.1`, un adaptateur de disponibilité Moonraker testé localement (`MoonrakerProbe` + `PrinterBridge`) adossé au portail de tâches partagé de `HYDRA-UMC-SDK`, une suite `unittest` déterministe, et des scripts build-test non mutants intégrés en CI avec clonage du SDK.

**Frontière d'intégration :** le firmware natif de l'imprimante (Klipper via Moonraker) conserve à tout moment le mouvement, les chauffages, la protection thermique et les interverrouillages machine ; ce pont ne fait que lire la disponibilité et réguler le travail robotique *auxiliaire* autour de cela.

**Encore à venir :** le pont n'a piloté ni imprimante, ni hotend, ni robot réels — envoyer des commandes réelles nécessite d'abord un profil d'imprimante testé, une authentification et une revue de sécurité physique.

---

## 🔗 PROJETS LIÉS

Ce projet fait partie d'un écosystème robotique plus large du même auteur (JuanenRac / Electro Hobby 3D), couvrant firmware, logiciel de contrôle, nœuds d'IA et outillage de flotte. Cela vaut la peine de le savoir, car une demande pourrait en réalité concerner l'un de ces projets plutôt que ce dépôt.

### Directement liés

- **[HYDRA-UMC-SDK](https://github.com/JuanenRac/HYDRA-UMC-SDK)** — le portail de tâches partagé `bridge_contract` à travers lequel ce pont (et tous les autres) évalue ses tâches.
- **[HYDRA-UMC-SERVER](https://github.com/JuanenRac/HYDRA-UMC-SERVER)** — le point de coordination autorisé auquel ce pont rend compte.
- **[HYDRA-UMC-SAFETY-ZONES](https://github.com/JuanenRac/HYDRA-UMC-SAFETY-ZONES)** — future preuve de sécurité de l'espace de travail.

### Reste de l'écosystème

**Plateforme HYDRA-UMC** — la micro-usine multi-robot pour laquelle ce pont coordonne les auxiliaires
- **[HYDRA-UMC](https://github.com/JuanenRac/HYDRA-UMC)** — la carte mère CM5 + STM32H745 orchestrant jusqu'à 8 bras robotiques.
- **[HYDRA-UMC-SERVER](https://github.com/JuanenRac/HYDRA-UMC-SERVER)** — le backend Express/WebSocket auquel parlent tous les clients de contrôle et ponts.
- **[HYDRA-UMC-STUDIO](https://github.com/JuanenRac/HYDRA-UMC-STUDIO)** — tableau de bord web, visualisation 3D multi-robot.

**External Automation Bridges** — dépôts frères partageant ce même portail de tâches `HYDRA-UMC-SDK`
- **[HYDRA-UMC-BRIDGE-CNC](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-CNC)** — pont de coordination de cellule CNC.
- **[HYDRA-UMC-BRIDGE-LASER](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-LASER)** — pont de coordination de cellules laser.
- **[HYDRA-UMC-BRIDGE-OPENPNP](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-OPENPNP)** — pont de flux de cartes pour OpenPnP.
- **[HYDRA-UMC-BRIDGE-ROS2](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-ROS2)** — frontière de coordination bidirectionnelle avec ROS 2.

**Preuves de sécurité et d'intégration**
- **[HYDRA-UMC-SAFETY-ZONES](https://github.com/JuanenRac/HYDRA-UMC-SAFETY-ZONES)** — preuves de sécurité des zones de cellule utilisées dans toute la famille de ponts.
- **[HYDRA-UMC-HIL-BRIDGE](https://github.com/JuanenRac/HYDRA-UMC-HIL-BRIDGE)** — preuves de tests hardware-in-the-loop.

## 👤 AUTEUR
**JuanenRac** (Electro Hobby 3D)
📧 electrohobby3d@gmail.com

## 📜 LICENCE
GPL-3.0 - Voir LICENSE pour les détails.

## 🛠️ COMPILATION ET EXÉCUTION

Utilisez la vérification de compilation sans versionnage avant une compilation de publication :

| Action | Windows | Linux / macOS |
|---|---|---|
| Vérification de compilation (sans changement de version ni CHANGELOG) | `build-test.bat` | `./build-test.sh` |
| Exécution / développement (le cas échéant) | `run*.bat` ou `dev*.bat` | `./run*.sh` ou `./dev*.sh` |

`build-test.bat` et `build-test.sh` compilent ou valident la pile du projet sans incrémenter `hydra-umc.project.json` ni modifier `CHANGELOG.md`. Ils ne peuvent produire que la sortie normale du compilateur. Les scripts `build*.bat`, `build*.sh`, `run*` et `dev*` existants conservent leur comportement propre au projet, versionné ou d'exécution ; utilisez-les lorsque ce comportement est requis.
