<!-- =============================================================================
HYDRA-UMC-BRIDGE-PRINTER3D - Softwarebrücke für 3D-Drucker
Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
GPL-3.0-or-later - see LICENSE
============================================================================= -->

<p align="center">
  <img src="images/HYDRA_UMC_BANNER.svg" alt="HYDRA-UMC-BRIDGE-PRINTER3D Banner" width="100%">
</p>

# 🖨️ HYDRA-UMC-BRIDGE-PRINTER3D

<p align="center"><a href="README.md">🇺🇸 English</a> | <a href="README_spa.md">🇪🇸 Español</a> | <a href="README_fra.md">🇫🇷 Français</a> | <a href="README_ita.md">🇮🇹 Italiano</a> | 🇩🇪 <b>Deutsch</b> | <a href="README_zho.md">🇨🇳 简体中文</a> | <a href="README_jpn.md">🇯🇵 日本語</a></p>

### 🌡️ Ausfallsichere Koordinationsbrücke für offene 3D-Drucksoftware

<p align="left">
  <img src="https://img.shields.io/badge/Lizenz-GPL%203.0-blue.svg" alt="GPL 3.0">
  <img src="https://img.shields.io/badge/Python-3.11%2B-3776AB.svg" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/Safety-Fails%20Closed-red.svg" alt="Fail-Closed">
</p>

---

## 1. 🛠️ TECHNISCHER ÜBERBLICK

**HYDRA-UMC-BRIDGE-PRINTER3D** ist der High-Level-Koordinator für offene 3D-Drucksoftware (Moonraker/Klipper) und HYDRA-UMC-Roboterhilfsfunktionen. Die native Drucker-Firmware bleibt jederzeit verantwortlich für Bewegung, Heizelemente, thermischen Schutz und Maschinenverriegelungen — diese Brücke liest nur die Bereitschaft und koordiniert Hilfsfunktionen rundherum.

Sie gehört zur Familie **External Automation Bridges**: einer Gruppe von Schwester-Repositories (CNC, LASER, OPENPNP, PRINTER3D, ROS2), die alle denselben gemeinsamen Sicherheitsvertrag von `HYDRA-UMC-SDK` sprechen, sodass keine Brücke ihre eigene Definition von "sicher zum Arbeiten" erfinden kann.

### Kernfunktionen:
* ✅ **Echte Moonraker-Bereitschaftssonde:** `moonraker.py`s `MoonrakerProbe` konsumiert den dokumentierten `/printer/info`-Endpunkt von Moonraker mit einem kleinen, ausschließlich auf der Standardbibliothek basierenden Client (`urlopen` + `json`) — keine zusätzliche Abhängigkeit über die Python-Standardbibliothek hinaus. *(implementiert, getestet in `tests/test_moonraker.py`)*
* ✅ **Echtes fail-closed Zustands-Parsing:** `parse_info()` bildet nur die wörtliche Zeichenkette `"ready"` auf `MachineState.IDLE` ab; `startup`/`shutdown`/`error` werden auf `FAULT` abgebildet, und alles andere (einschließlich einer fehlerhaften Antwort) auf `OFFLINE` — niemals auf einen Zustand, der es erlauben würde, einen Roboter rund um den Drucker zu planen. *(implementiert)*
* ✅ **Echtes gemeinsames Sicherheitsgatter:** jeder beobachtete Auftrag wird über `evaluate_job()` aus dem `bridge_contract` von `HYDRA-UMC-SDK` neu bewertet — demselben Gatter, das jede Schwesterbrücke und HYDRA-UMC-SERVER verwenden. *(implementiert)*
* ✅ **Nicht-mutierender Build/Test:** `build-test.bat`/`.sh` kompilieren den Antwort-Parser und das Sicherheitsgatter, ohne G-Code zu senden, Versionen zu ändern oder einen Drucker anzufassen. *(implementiert, siehe BUILD & AUSFÜHRUNG unten)*
* 🔜 **Echte Druckersteuerung (G-Code-Befehle)** — zurückgestellt, bis ein getestetes Profil, Authentifizierung und eine physische Sicherheitsprüfung vorliegen. *(geplant)*

---

## 2. 🔄 DRUCKERKOORDINATIONSABLAUF

```mermaid
flowchart LR
    PRINTER["Moonraker / Klipper<br/>(/printer/info)"] --> BRIDGE["BRIDGE-PRINTER3D<br/>MoonrakerProbe.parse_info()"]
    BRIDGE -- "BridgeJob + beobachteter MachineState" --> SDK["HYDRA-UMC-SDK<br/>evaluate_job()"]
    SDK -- GateDecision --> SERVER["HYDRA-UMC-SERVER"]
    SERVER -- "Auftrag / Abbruch" --> CELL["Zellsicherheit"]
```

---

## 3. 🧱 ARCHITEKTUR UND DESIGN-ENTSCHEIDUNGEN

* **Warum nur Moonrakers wörtlicher `"ready"`-Zustand auf Leerlauf abgebildet wird.** Die Zustandsabbildung von `parse_info()` ist bewusst eng gefasst: `ready` → `IDLE`, `startup`/`shutdown`/`error` → `FAULT` (fail-closed), und jeder andere oder fehlende Wert → `OFFLINE`. Es gibt keine Standardannahme "sicher", wenn ein Druckerzustand nicht erkannt wird.
* **Warum das Parsing eine eigene `@staticmethod`, getrennt vom Netzwerkabruf, ist.** `MoonrakerProbe.parse_info()` nimmt ein einfaches `dict` entgegen und ist vollständig unit-testbar ohne Netzwerkaufruf oder laufenden Drucker; `fetch()` ist der schlanke, notwendigerweise netzwerkbasierte Teil, der es aufruft. Die sicherheitsrelevante Logik liegt in dem Teil, der nie einen echten Drucker zum Testen braucht.
* **Warum die Sonde stdlib-`urlopen`/`json` statt einer Moonraker-Client-Bibliothek verwendet.** Die Abhängigkeitsfläche auf die Python-Standardbibliothek zu beschränken, hält das sicherheitsrelevante Parsing minimal, auditierbar und frei von den eigenen Annahmen eines Drittanbieter-Clients über Wiederholungsversuche, Timeouts oder Fehlerbehandlung.
* **Warum die Brücke einen neuen `BridgeJob` erstellt und an das gemeinsame `evaluate_job()` delegiert, statt eigene Annahme-/Ablehnungslogik zu schreiben.** Alle fünf External Automation Bridges (CNC, LASER, OPENPNP, PRINTER3D, ROS2) verwenden exakt denselben `bridge_contract` von `HYDRA-UMC-SDK` wieder, sodass "was als sicher für den Start eines Auftrags zählt" zwischen ihnen nicht stillschweigend auseinanderdriften kann.
* **Warum echte Befehle (G-Code) zuerst ein getestetes Profil, eine Authentifizierung und eine physische Sicherheitsprüfung erfordern.** Moonrakers API kann beliebigen G-Code akzeptieren; ihn ohne validiertes Profil und Authentifizierung zu senden, würde genau die Bereitschaftsprüfung umgehen, für deren Durchsetzung diese Brücke existiert.
* **Wie das in den Rest des Ökosystems passt.** BRIDGE-PRINTER3D sitzt zwischen Moonraker/Klipper und `HYDRA-UMC-SDK` → `HYDRA-UMC-SERVER` → Zellsicherheit: es koordiniert Roboter-Hilfsarbeit rund um den Drucker, es ersetzt niemals native Firmware, Heizelemente oder thermischen Schutz.

---

## 📂 VERZEICHNISSTRUKTUR

```text
HYDRA-UMC-BRIDGE-PRINTER3D/
├── src/
│   └── hydra_umc_bridge_printer3d/
│       ├── __init__.py
│       └── moonraker.py         # Sicherheitsgatter MoonrakerProbe + PrinterBridge
├── tests/
│   └── test_moonraker.py        # Bereitschafts-Parsing- und Ausfallsicherheitsgatter-Tests
├── tools/
│   ├── build_test.py            # Nicht-mutierender Compiler + Testläufer (build-test.bat/.sh)
│   └── bump_version.py          # Synchronisiert pyproject.toml, Manifest und CHANGELOG.md
├── build-test.bat / build-test.sh  # Validiert nur, ändert das Repository nie
├── build.bat / build.sh            # Validiert und erhöht bei Erfolg Version + CHANGELOG
├── pyproject.toml               # Paket-Metadaten; hängt von HYDRA-UMC-SDK ab (git)
├── hydra-umc.project.json       # Ökosystem-Manifest (Version, Reifegrad, Familie)
├── CHANGELOG.md
├── CODE_OF_CONDUCT.md / CONTRIBUTING.md / SECURITY.md / SUPPORT.md
├── LICENSE / LICENSE.md
└── README.md / README_*.md      # Diese Datei und ihre 6 Übersetzungen
```

---

## 4. ⚙️ BUILD & AUSFÜHRUNG

Erfordert Python 3.11+. `tools/build_test.py` erwartet, dass `HYDRA-UMC-SDK` als Schwesterverzeichnis (`../HYDRA-UMC-SDK`) ausgecheckt oder über die Umgebungsvariable `HYDRA_UMC_SDK_ROOT` angegeben ist.

```bash
# Windows
build-test.bat      # nur Validierung — keine Versions-/CHANGELOG-Änderung
build.bat            # validiert und erhöht bei Erfolg Version + CHANGELOG

# Linux/macOS
bash build-test.sh
bash build.sh
```

`build-test` kompiliert jedes Modul unter `src/` mit `py_compile` und führt die vollständige `unittest`-Suite aus (`tests/test_moonraker.py`), was das Parsing der Bereitschaftsantwort und das Ausfallsicherheitsgatter belegt — es sendet keinen G-Code, fasst keinen Drucker an und ändert das Repository nie. `build` führt zuerst dieselbe Validierung aus und ruft nur bei Erfolg `tools/bump_version.py` auf, um die Version in `pyproject.toml`, `hydra-umc.project.json` und `CHANGELOG.md` zu synchronisieren. Es gibt noch keinen echten Drucker-`run`-Befehl — dafür sind zuerst ein getestetes Profil, Authentifizierung und eine physische Sicherheitsprüfung erforderlich.

---

## ✅ AKTUELLER STATUS UND NÄCHSTE SCHRITTE

**Heute real:** Version `0.0.1`, ein lokal getesteter Moonraker-Bereitschaftsadapter (`MoonrakerProbe` + `PrinterBridge`), gestützt auf das gemeinsame Auftragsgatter von `HYDRA-UMC-SDK`, eine deterministische `unittest`-Suite sowie nicht-mutierende Build-Test-Skripte, die in CI mit SDK-Checkout eingebunden sind.

**Integrationsgrenze:** die native Drucker-Firmware (Klipper über Moonraker) behält jederzeit Bewegung, Heizelemente, thermischen Schutz und Maschinenverriegelungen; diese Brücke liest ausschließlich die Bereitschaft und steuert *Hilfs*-Roboterarbeit rund darum.

**Noch offen:** die Brücke hat noch keinen echten Drucker, kein Hotend und keinen Roboter gesteuert — das Senden echter Befehle erfordert zuerst ein getestetes Druckerprofil, Authentifizierung und eine physische Sicherheitsprüfung.

---

## 🔗 VERWANDTE PROJEKTE

Dieses Projekt ist Teil eines größeren Robotik-Ökosystems desselben Autors (JuanenRac / Electro Hobby 3D), das Firmware, Steuerungssoftware, KI-Knoten und Flotten-Tooling umfasst. Es lohnt sich, das zu wissen, da eine Anfrage tatsächlich eines dieser Projekte betreffen könnte statt dieses Repositorys.

### Direkt verwandt

- **[HYDRA-UMC-SDK](https://github.com/JuanenRac/HYDRA-UMC-SDK)** — das gemeinsame `bridge_contract`-Auftragsgatter, über das diese Brücke (und alle anderen) ihre Aufträge bewertet.
- **[HYDRA-UMC-SERVER](https://github.com/JuanenRac/HYDRA-UMC-SERVER)** — der autorisierte Koordinationsendpunkt, an den diese Brücke berichtet.
- **[HYDRA-UMC-SAFETY-ZONES](https://github.com/JuanenRac/HYDRA-UMC-SAFETY-ZONES)** — künftiger Nachweis der Arbeitsbereichssicherheit.

### Rest des Ökosystems

**HYDRA-UMC-Plattform** — die Multi-Roboter-Mikrofabrik, für die diese Brücke Hilfsfunktionen koordiniert
- **[HYDRA-UMC](https://github.com/JuanenRac/HYDRA-UMC)** — die CM5- + STM32H745-Hauptplatine, die bis zu 8 Roboterarme orchestriert.
- **[HYDRA-UMC-SERVER](https://github.com/JuanenRac/HYDRA-UMC-SERVER)** — das Express/WebSocket-Backend, mit dem jeder Steuerungsclient und jede Brücke spricht.
- **[HYDRA-UMC-STUDIO](https://github.com/JuanenRac/HYDRA-UMC-STUDIO)** — webbasiertes Steuerungs-Dashboard, Multi-Roboter-3D-Visualisierung.

**External Automation Bridges** — Schwester-Repositories, die dasselbe `HYDRA-UMC-SDK`-Auftragsgatter teilen
- **[HYDRA-UMC-BRIDGE-CNC](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-CNC)** — CNC-Zellkoordinationsbrücke.
- **[HYDRA-UMC-BRIDGE-LASER](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-LASER)** — Koordinationsbrücke für Laserzellen.
- **[HYDRA-UMC-BRIDGE-OPENPNP](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-OPENPNP)** — Board-Flow-Brücke für OpenPnP.
- **[HYDRA-UMC-BRIDGE-ROS2](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-ROS2)** — bidirektionale Koordinationsgrenze zu ROS 2.

**Sicherheits- und Integrationsnachweise**
- **[HYDRA-UMC-SAFETY-ZONES](https://github.com/JuanenRac/HYDRA-UMC-SAFETY-ZONES)** — Sicherheitsnachweise für Zellzonen, die in der gesamten Brückenfamilie verwendet werden.
- **[HYDRA-UMC-HIL-BRIDGE](https://github.com/JuanenRac/HYDRA-UMC-HIL-BRIDGE)** — Hardware-in-the-Loop-Testnachweise.

## 👤 AUTOR
**JuanenRac** (Electro Hobby 3D)
📧 electrohobby3d@gmail.com

## 📜 LIZENZ
GPL-3.0 - Siehe LICENSE für Details.

## 🛠️ BUILD & AUSFÜHRUNG

Verwenden Sie die versionslose Build-Prüfung vor einem Release-Build:

| Aktion | Windows | Linux / macOS |
|---|---|---|
| Build-Prüfung (keine Versions- oder CHANGELOG-Änderung) | `build-test.bat` | `./build-test.sh` |
| Ausführung / Entwicklung (falls vorhanden) | `run*.bat` oder `dev*.bat` | `./run*.sh` oder `./dev*.sh` |

`build-test.bat` und `build-test.sh` kompilieren oder validieren den Projekt-Stack, ohne `hydra-umc.project.json` zu erhöhen oder `CHANGELOG.md` zu ändern. Sie dürfen nur normale Compiler-Ausgaben erzeugen. Bestehende `build*.bat`-, `build*.sh`-, `run*`- und `dev*`-Skripte behalten ihr projektspezifisches, versioniertes oder Laufzeitverhalten; verwenden Sie sie, wenn dieses Verhalten benötigt wird.
