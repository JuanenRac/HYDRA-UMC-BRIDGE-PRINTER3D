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

**HYDRA-UMC-BRIDGE-PRINTER3D** ist der High-Level-Koordinator für offene 3D-Drucksoftware (Moonraker/Klipper) und HYDRA-UMC-Roboterhilfsfunktionen. Sie erkennt außerdem lokale Slicer-Artefakte schreibgeschützt. Die native Drucker-Firmware bleibt jederzeit verantwortlich für Bewegung, Heizelemente, thermischen Schutz und Maschinenverriegelungen — diese Brücke liest nur die Bereitschaft, erfasst Artefakt-Evidenz und koordiniert Hilfsfunktionen rundherum.

Sie gehört zur Familie **External Automation Bridges**: einer Gruppe von Schwester-Repositories (CNC, LASER, OPENPNP, PRINTER3D, ROS2), die alle denselben gemeinsamen Sicherheitsvertrag von `HYDRA-UMC-SDK` sprechen, sodass keine Brücke ihre eigene Definition von "sicher zum Arbeiten" erfinden kann.

### Kernfunktionen:
* ✅ **Echte Moonraker-Bereitschaftssonde:** `moonraker.py`s `MoonrakerProbe` konsumiert den dokumentierten `/printer/info`-Endpunkt von Moonraker mit einem kleinen, ausschließlich auf der Standardbibliothek basierenden Client (`urlopen` + `json`) — keine zusätzliche Abhängigkeit über die Python-Standardbibliothek hinaus. *(implementiert, getestet in `tests/test_moonraker.py`)*
* ✅ **Echtes fail-closed Zustands-Parsing:** `parse_info()` bildet nur die wörtliche Zeichenkette `"ready"` auf `MachineState.IDLE` ab; `startup`/`shutdown`/`error` werden auf `FAULT` abgebildet, und alles andere (einschließlich einer fehlerhaften Antwort) auf `OFFLINE` — niemals auf einen Zustand, der es erlauben würde, einen Roboter rund um den Drucker zu planen. *(implementiert)*
* ✅ **Echtes gemeinsames Sicherheitsgatter:** jeder beobachtete Auftrag wird über `evaluate_job()` aus dem `bridge_contract` von `HYDRA-UMC-SDK` neu bewertet — demselben Gatter, das jede Schwesterbrücke und HYDRA-UMC-SERVER verwenden. *(implementiert)*
* ✅ **Slicer-unabhängige Artefaktprüfung:** `artifacts.py` identifiziert einfaches FDM-G-Code von OrcaSlicer, Ultimaker Cura, PrusaSlicer, Bambu Studio und weiteren Slicern ausschließlich über lokale Evidenz; außerdem erkennt es 3MF-Pakete und Lychee-kompatible Resin-Slices ohne Entpacken, Befehlsanalyse, Upload oder Druck. *(implementiert, getestet in `tests/test_artifacts.py`)*
* ✅ **Profil-Evidenz-Grenze:** `profiles.py` kann ein untersuchtes Artefakt mit einem deklarierten FDM- oder Harzprofil abgleichen, gibt aber selbst bei einer Übereinstimmung `execution_authorized=False` zurück. *(implementiert, getestet in `tests/test_profiles.py`)*
* ✅ **Echte, SDK-gegatterte Auftragsbefehle:** `MoonrakerJobControl` sendet echte `POST`-Anfragen an die dokumentierten `/printer/print/start|pause|resume|cancel`-Endpunkte von Moonraker — `start_job()` ist an dieselbe `evaluate_job()`-Entscheidung gebunden, die jeder produktive Dispatch in diesem Ökosystem verwendet; `pause_job()`/`cancel_job()` sind immer erlaubt (dieselbe Deeskalationslogik wie `ABORT`); `resume_job()` erfordert einen tatsächlich in `HOLDING` befindlichen Drucker. Es startet immer nur eine bereits hochgeladene, bereits geslicete Datei anhand ihres Namens — es streamt niemals rohen G-Code. *(implementiert, getestet in `tests/test_moonraker.py`)*
* ✅ **Nicht-mutierender Build/Test:** `build-test.bat`/`.sh` kompilieren den Antwort-Parser und das Sicherheitsgatter, ohne G-Code zu senden, Versionen zu ändern oder einen Drucker anzufassen. *(implementiert, siehe BUILD & AUSFÜHRUNG unten)*
* 🔜 **Rohes G-Code-Streaming** — bewusst weiterhin zurückgestellt: beliebige Low-Level-Befehle zu senden (kein benannter, bereits geslicter Auftrag) erfordert ein getestetes Profil, eine Authentifizierung und eine physische Sicherheitsprüfung, die diese Brücke noch nicht hat. *(geplant)*

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
* **Warum Auftragsbefehle (start/pause/resume/cancel) echt sind, rohes G-Code-Streaming aber noch nicht.** Moonrakers `/printer/print/*`-Endpunkte referenzieren immer nur eine bereits hochgeladene, bereits geslicete Datei anhand ihres Namens - dieselbe Sicherheitshülle, die Moonraker/Klipper selbst bereits für diese Datei durchsetzen. Beliebiger roher G-Code ist eine grundlegend andere, viel größere Vertrauensfläche (er kann alles enthalten) und erfordert weiterhin ein getestetes Profil, eine Authentifizierung und eine physische Sicherheitsprüfung, die diese Brücke noch nicht hat.
* **Warum `resume_job()` nicht das generische `evaluate_job()`-Gatter wiederverwendet.** Dieses Gatter ist um „produktive Arbeit braucht eine IDLE-Maschine" herum aufgebaut - das Gegenteil des Fortsetzens eines pausierten Auftrags, was nur von `HOLDING` aus Sinn ergibt. Dieselbe eigenständige Gatter-Logik, die bereits für `stand_request()`/`sit_request()` von DROIDS verwendet wird.
* **Wie das in den Rest des Ökosystems passt.** BRIDGE-PRINTER3D sitzt zwischen Moonraker/Klipper und `HYDRA-UMC-SDK` → `HYDRA-UMC-SERVER` → Zellsicherheit: es koordiniert Roboter-Hilfsarbeit rund um den Drucker, es ersetzt niemals native Firmware, Heizelemente oder thermischen Schutz.

## 🧾 SLICER-ARTEFAKT-KOMPATIBILITÄT

Der schreibgeschützte Artefaktpfad unterstützt normales FDM-G-Code (`.gcode`, `.gco`, `.gc`) aus OrcaSlicer, Ultimaker Cura, PrusaSlicer, Bambu Studio und weiteren Slicern. Bekannte Kommentare liefern einen Herkunftshinweis; ohne Marker bleibt er `unknown-slicer`. `.gcode.3mf` und generische `.3mf` werden erkannt, aber niemals entpackt. Resin-Slices (`.ctb`, `.goo`, `.photon`, `.pwmo`, `.pws`, `.sl1`) aus Lychee-kompatiblen Workflows bleiben absichtlich undurchsichtig und werden nie einem bestimmten Drucker oder Slicer zugeschrieben.

Dies ist Kompatibilität mit **Ausgabe-Artefakten**, keine Fernsteuerung dieser Anwendungen. Die Brücke startet keine Slicer, ändert keine Profile, analysiert/führt keinen G-Code aus, lädt keine Dateien hoch, kontaktiert keine Cloud-Dienste und startet keine Drucke. Die genaue Matrix und Voraussetzungen für spätere Steuerung stehen unter [Slicer-Artefakt-Kompatibilität](docs/SLICER_ARTIFACT_COMPATIBILITY.md).

---

## 📂 VERZEICHNISSTRUKTUR

```text
HYDRA-UMC-BRIDGE-PRINTER3D/
├── src/
│   └── hydra_umc_bridge_printer3d/
│       ├── __init__.py
│       ├── artifacts.py         # Schreibgeschützte G-Code-, 3MF- und Resin-Slice-Evidenz
│       ├── profiles.py          # Profilkompatibilitäts-Evidenz; niemals Druckautorisierung
│       ├── moonraker.py         # Sicherheitsgatter MoonrakerProbe + PrinterBridge
│       └── mqtt_transport.py    # Echter MQTT-Broker-Transport für die bereits reale Moonraker-Logik dieser Bridge
├── tests/
│   ├── test_artifacts.py         # Slicer-Evidenztests (ohne Drucker-E/A)
│   ├── test_profiles.py         # Profilabgleich verweigert die Ausführung immer
│   ├── test_moonraker.py        # Bereitschafts-Parsing- und Ausfallsicherheitsgatter-Tests
│   └── test_mqtt_transport.py   # MQTT-Befehls-/Statusform-Tests gegen einen simulierten Broker-Client
├── tools/
│   ├── build_test.py            # Nicht-mutierender Compiler + Testläufer (build-test.bat/.sh)
│   ├── inspect_print_artifact.py # Lokale Artefakt-Evidenz als JSON-CLI
│   ├── assess_print_profile.py  # Offline-CLI für Profil-/Artefaktabgleich; autorisiert nie eine Ausführung
│   ├── ci_validate.py           # Abhängigkeitsfreie, nicht-destruktive CI-Basislinie (verwendet von .github/workflows/ci.yml)
│   └── bump_version.py          # Synchronisiert pyproject.toml, Manifest und CHANGELOG.md
├── docs/
│   ├── BRIDGE_GUIDE.md                        # Umfang, kompatible Plattformen, Skripte, Hardware-Abnahmegatter
│   ├── PRINT_PROFILE_BOUNDARY.md              # Was Profilkompatibilitäts-Evidenz bedeutet vs. Druckautorisierung
│   └── SLICER_ARTIFACT_COMPATIBILITY.md       # Welche Slicer-Artefaktformate diese Bridge als Evidenz lesen kann
├── images/
│   └── HYDRA_UMC_BANNER.svg     # README-Banner
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

`build-test` kompiliert jedes Modul unter `src/` und `tools/` mit `py_compile` und führt die vollständige `unittest`-Suite aus (`tests/test_moonraker.py` und `tests/test_artifacts.py`), was das Bereitschafts-Parsing, die Artefaktprüfung und das Ausfallsicherheitsgatter belegt — es sendet keinen G-Code, fasst keinen Drucker an und ändert das Repository nie. `build` führt zuerst dieselbe Validierung aus und ruft nur bei Erfolg `tools/bump_version.py` auf, um die Version in `pyproject.toml`, `hydra-umc.project.json` und `CHANGELOG.md` zu synchronisieren. Es gibt noch keinen echten Drucker-`run`-Befehl — dafür sind zuerst ein getestetes Profil, Authentifizierung und eine physische Sicherheitsprüfung erforderlich.

Um eine lokale Slicer-Ausgabe ohne Druckerkontakt zu prüfen:

```bash
py tools/inspect_print_artifact.py pfad/zum/auftrag.gcode
```

---

## ✅ AKTUELLER STATUS UND NÄCHSTE SCHRITTE

**Heute real:** Version `0.1.0`, ein lokal getesteter Moonraker-Bereitschaftsadapter (`MoonrakerProbe` + `PrinterBridge`), gestützt auf das gemeinsame Auftragsgatter von `HYDRA-UMC-SDK`, echte, SDK-gegatterte Auftragsbefehle (`MoonrakerJobControl`: eine bereits hochgeladene Datei über Moonrakers eigene REST-API starten/pausieren/fortsetzen/abbrechen), schreibgeschützte Evidenz für G-Code/3MF/Resin-Slice-Artefakte und Profilkompatibilität für die wichtigsten Slicer-Familien, eine deterministische `unittest`-Suite mit neunundvierzig Tests einschließlich der lokalen HTTP-Vertragsprüfung `/printer/info`, dem echten, separaten Vertrag `/printer/objects/query?print_stats=state` und echter `POST`-Auftragsbefehl-Verifikation, sowie nicht-mutierende Build-Test-Skripte, die in CI mit SDK-Checkout eingebunden sind.

**Integrationsgrenze:** die native Drucker-Firmware (Klipper über Moonraker) behält jederzeit Bewegung, Heizelemente, thermischen Schutz und Maschinenverriegelungen; diese Brücke liest ausschließlich die Bereitschaft und steuert *Hilfs*-Roboterarbeit rund darum.

**Noch offen:** die Brücke hat noch keinen echten Drucker, kein Hotend und keinen Roboter gesteuert — das Senden echter Befehle erfordert zuerst ein getestetes Druckerprofil, Authentifizierung und eine physische Sicherheitsprüfung.

---

## 🔗 Verwandte Projekte

Dieses Projekt ist Teil des HYDRA-UMC-Robotik-Ökosystems desselben Autors (JuanenRac / Electro Hobby 3D). Gut zu wissen, da eine Anfrage eigentlich eines dieser Projekte betreffen könnte statt dieses Repositorys.

**Übergeordnetes Projekt**
- **[HYDRA-UMC-SERVER](https://github.com/JuanenRac/HYDRA-UMC-SERVER)** — das reale Headless-Backend (REST/WebSocket), mit dem jeder Steuerungsclient tatsächlich spricht; die authentifizierte Ökosystemgrenze, an die diese Bridge berichtet, sobald jeder Befehl die eigene lokale Sicherheitsschranke dieser Bridge durchlaufen hat.

**Geschwisterprojekte** — sprechen ebenfalls mit der eigenen API von HYDRA-UMC-SERVER, jeweils als eigener Client
- **[HYDRA-UMC-STUDIO](https://github.com/JuanenRac/HYDRA-UMC-STUDIO)** — Web-Steuerungs-Dashboard mit Echtzeit-3D-Visualisierung mehrerer Roboter.
- **[HYDRA-UMC-SUITE](https://github.com/JuanenRac/HYDRA-UMC-SUITE)** — Desktop-Schwarmleitstand (PySide6) für mehrere Server gleichzeitig, verpackt als eigenständige ausführbare Datei.
- **[HYDRA-UMC-ANDROID-CONTROL](https://github.com/JuanenRac/HYDRA-UMC-ANDROID-CONTROL)** — native Android-Steuerungs-App mit biometrischem Login und einer gekoppelten Wear-OS-Begleit-App.
- **[HYDRA-UMC-IOS-CONTROL](https://github.com/JuanenRac/HYDRA-UMC-IOS-CONTROL)** — iOS/iPadOS-Steuerungs-App (Flutter) mit Echtzeit-WebSocket-Synchronisierung.
- **[HYDRA-UMC-DSI](https://github.com/JuanenRac/HYDRA-UMC-DSI)** — native Touch-UI für das eingebaute 7"-DSI-Touchscreen, direkt auf dem CM5 eingebettet.
- **[HYDRA-UMC-BRIDGE-AMR](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-AMR)** — Koordinationsschranke für AGV-/AMR-Flotten über einen echten VDA-5050-MQTT-Publisher.
- **[HYDRA-UMC-BRIDGE-CNC](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-CNC)** — High-Level-Koordinator für CNC-Zellen mit echtem GRBL-Status-/Steuerbyte-Zugriff.
- **[HYDRA-UMC-BRIDGE-DROIDS](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-DROIDS)** — Koordinationsschranke für laufende/humanoide Droiden, mit einem echten Boston-Dynamics-Spot-Befehlssender.
- **[HYDRA-UMC-BRIDGE-LASER](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-LASER)** — Sicherheitskoordinator für Laserzellen, liest 3 echte Schlüssel-/Gehäuse-/Verriegelungs-GPIO-Sicherungen.
- **[HYDRA-UMC-BRIDGE-OPENPNP](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-OPENPNP)** — sicherer High-Level-Koordinator für den Leiterplattenfluss von OpenPnP Pick-and-Place.
- **[HYDRA-UMC-BRIDGE-ROS2](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-ROS2)** — Sicherheitskoordinator mit einem echten, träge importierten rclpy-ROS-2-Transport.
- **[HYDRA-UMC-BRIDGE-UAV](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-UAV)** — Koordinationsschranke für kameraausgestattete UAVs, mit einem echten MAVLink-Befehlssender.

**Direkt verwandt**
- **[HYDRA-UMC-SDK](https://github.com/JuanenRac/HYDRA-UMC-SDK)** — der gemeinsame JSON-Schema-Vertrag und die Sicherheitsschranke, gegen die jede Bridge ihre Befehle validiert.
- **[HYDRA-UMC-MQTT-BROKER](https://github.com/JuanenRac/HYDRA-UMC-MQTT-BROKER)** — der echte Transport von `mqtt_transport.py` für die eigenen `hydra/bridges/printer3d/...`-Topics dieser Bridge — Status plus echte Moonraker-Befehle start/pause/resume/cancel, neben der gemeinsamen Job-Schranke; siehe die eigene `docs/BRIDGE_TOPICS.md` dieses Repositorys.
- **[HYDRA-UMC-SAFETY-ZONES](https://github.com/JuanenRac/HYDRA-UMC-SAFETY-ZONES)** — zukünftiger Arbeitsraum-Sicherheitsnachweis für diese Bridge.

**Ebenfalls Teil des Ökosystems**

*Kern-Hardware & Plattform*
- **[HYDRA-UMC](https://github.com/JuanenRac/HYDRA-UMC)** — das physische Motherboard des Roboterarms: CM5-Host + Dual-Core-STM32H745, koordiniert bis zu 8 Werkzeugarme über CAN-OTA/SPI-OTA.
- **[HYDRA-UMC-OS](https://github.com/JuanenRac/HYDRA-UMC-OS)** — reproduzierbare Raspberry-Pi-OS-Produktschicht für den CM5: schreibgeschützter Agent, validierte Konfiguration/Profile, WiFi-Ersteinrichtung.

*Kern-Backend & Clients*
- **[HYDRA-UMC-EDITOR-URDF](https://github.com/JuanenRac/HYDRA-UMC-EDITOR-URDF)** — grafischer Desktop-URDF-Ersteller/-Editor, der fertige Modelle in STUDIOs eigenen Katalog überträgt.

*URTC-Werkzeugplattform*
- **[URTC](https://github.com/JuanenRac/URTC)** — Firmware für die physische Universal-Robot-Tool-Controller-Platine, 25+ Werkzeugprofile über CAN-Bus.
- **[URTC-FLASHER](https://github.com/JuanenRac/URTC-FLASHER)** — Desktop-GUI-Flash-Tool für URTC-Platinen, CAN-OTA plus Full-Chip-SWD/JTAG.
- **[URTC-TESTER](https://github.com/JuanenRac/URTC-TESTER)** — Desktop-Live-CAN-Bus-Diagnosetool für URTC-Platinen, ein Panel pro Werkzeugprofil.
- **[URTC-WEB-STUDIO](https://github.com/JuanenRac/URTC-WEB-STUDIO)** — browserbasierte Alternative zu URTC-TESTER über die Web-Serial-API, ohne lokale Installation.

*Vision-KI-Knoten (Hailo-8)*
- **[HYDRA-UMC-VISION-NODE](https://github.com/JuanenRac/HYDRA-UMC-VISION-NODE)** — Integrationsknoten für die Hailo-8-Vision-Pipeline, mit einer echten stufenweisen Hardware-Bereitschaftsprüfung.
- **[HYDRA-UMC-DETECTION-HEF](https://github.com/JuanenRac/HYDRA-UMC-DETECTION-HEF)** — echte Registry für kompilierte Modelle mit Hailo-Architektur-/Prüfsummen-Safe-Load-Verifizierung.
- **[HYDRA-UMC-VISION-STREAMER](https://github.com/JuanenRac/HYDRA-UMC-VISION-STREAMER)** — echter GStreamer-Pipeline- + MediaMTX-Konfigurationsgenerator mit einer echten HailoRT-Integrationsschranke.
- **[HYDRA-UMC-VISUAL-SERVOING-API](https://github.com/JuanenRac/HYDRA-UMC-VISUAL-SERVOING-API)** — echtes Position-Based-Visual-Servoing-Korrekturgesetz, sicherheitsgesteuert nach vorgelagertem Zonenstatus.

*Kognitiver KI-Knoten (Hailo-10)*
- **[HYDRA-UMC-COGNITIVE-NODE](https://github.com/JuanenRac/HYDRA-UMC-COGNITIVE-NODE)** — Integrationsknoten für die Hailo-10-Cognitive-Pipeline (LLM-/VLA-/Sprach-Orchestrierung).
- **[HYDRA-UMC-VLA-ENGINE](https://github.com/JuanenRac/HYDRA-UMC-VLA-ENGINE)** — echte Aktions-Token-Kodierung/-Dekodierung und Trajektoriengenerierung für ein Vision-Language-Action-Modell.
- **[HYDRA-UMC-VOICE-UI](https://github.com/JuanenRac/HYDRA-UMC-VOICE-UI)** — echtes Sprach-Frontend (VAD + Intent-Parser) mit einem begrenzten, bestätigungsgesicherten Watch-Relay.
- **[HYDRA-UMC-SEMANTIC-PLANNER](https://github.com/JuanenRac/HYDRA-UMC-SEMANTIC-PLANNER)** — echte regelbasierte Aufgabenzerlegung und semantische Fehlerbehebung über MCU-Fehlercodes.
- **[HYDRA-UMC-DOCS-QA](https://github.com/JuanenRac/HYDRA-UMC-DOCS-QA)** — echte, nur auf der Standardbibliothek basierende TF-IDF-Dokumentensuche über die eigenen Markdown-Dokumente dieses Ökosystems.

*Orchestrierung & Schwarm*
- **[HYDRA-UMC-ORCHESTRATOR](https://github.com/JuanenRac/HYDRA-UMC-ORCHESTRATOR)** — Integrationsknoten mit einem echten gRPC/Protobuf-Health-Report-Vertrag und einer Missions-Zustandsmaschine.
- **[HYDRA-UMC-JOB-DISPATCHER](https://github.com/JuanenRac/HYDRA-UMC-JOB-DISPATCHER)** — echte prioritätsbasierte Job-Queue mit Deduplizierung, über eine echte HTTP-API.
- **[HYDRA-UMC-NODE-HEALING](https://github.com/JuanenRac/HYDRA-UMC-NODE-HEALING)** — echter gRPC-basierter Flotten-Health-Watchdog mit Retry/Backoff und Identitäts-Mismatch-Erkennung.
- **[HYDRA-UMC-PATH-PLANNER-3D](https://github.com/JuanenRac/HYDRA-UMC-PATH-PLANNER-3D)** — echter RRT-basierter 3D-Pfadplaner mit echter Hindernis-/Arbeitsraum-Kollisionsvalidierung.
- **[HYDRA-UMC-SWARM-SYNC](https://github.com/JuanenRac/HYDRA-UMC-SWARM-SYNC)** — echte CRDT-LWW-Element-Map-Zustandssynchronisation, eigenschaftsgetestet auf Multi-Zellen-Konvergenz.

*Digitaler Zwilling & Simulation*
- **[HYDRA-UMC-TWIN](https://github.com/JuanenRac/HYDRA-UMC-TWIN)** — Integrationsknoten für die Digital-Twin-Engine, mit einem echten Versionskompatibilitäts-Sync-Vertrag.
- **[HYDRA-UMC-HIL-BRIDGE](https://github.com/JuanenRac/HYDRA-UMC-HIL-BRIDGE)** — echte Hardware-in-the-Loop-Sicherheitsverriegelung, die Befehle zwischen Simulation und echter Hardware routet.
- **[HYDRA-UMC-PHYSICS-REPLICA](https://github.com/JuanenRac/HYDRA-UMC-PHYSICS-REPLICA)** — echte Vorwärtskinematik und Gelenkgrenzenvalidierung über eine echte URDF-Teilmenge.
- **[HYDRA-UMC-SYNTHETIC-DATA-GEN](https://github.com/JuanenRac/HYDRA-UMC-SYNTHETIC-DATA-GEN)** — echter prozeduraler 2D-Szenengenerator mit YOLO/COCO-Annotationsexport.

*Daten & Analytik*
- **[HYDRA-UMC-DATALAKE](https://github.com/JuanenRac/HYDRA-UMC-DATALAKE)** — echter sqlite3-gestützter Zeitreihenspeicher mit einer echten Ingest-/Abfrage-HTTP-API.
- **[HYDRA-UMC-ANOMALY-DETECTOR](https://github.com/JuanenRac/HYDRA-UMC-ANOMALY-DETECTOR)** — echter FFT- + statistischer Basislinien-Anomaliedetektor mit Drift-Überwachung.
- **[HYDRA-UMC-PRODUCTION-REPORTS](https://github.com/JuanenRac/HYDRA-UMC-PRODUCTION-REPORTS)** — echte OEE-/Verfügbarkeitsberechnung über den DATALAKE-Verlauf, mit reproduzierbarem CSV-Export.
- **[HYDRA-UMC-TELEMETRY-COLLECTOR](https://github.com/JuanenRac/HYDRA-UMC-TELEMETRY-COLLECTOR)** — echte CAN/WebSocket-Ingestion-Pipeline in DATALAKE, mit Sequenz-Deduplizierung.

*Industrie-Gateway*
- **[HYDRA-UMC-GATEWAY-INDUSTRIAL](https://github.com/JuanenRac/HYDRA-UMC-GATEWAY-INDUSTRIAL)** — Integrationsknoten, der zu Industrieprotokollen weiterleitet, mit einer echten Befehls-Allowlist-/Backpressure-Schicht.
- **[HYDRA-UMC-OPCUA-SERVER](https://github.com/JuanenRac/HYDRA-UMC-OPCUA-SERVER)** — echter OPC-UA-Adressraum, verifiziert mit einer echten Binärprotokoll-Client-Session.
- **[HYDRA-UMC-MTCONNECT-ADAPTER](https://github.com/JuanenRac/HYDRA-UMC-MTCONNECT-ADAPTER)** — echte MTConnect-`/probe`- und `/current`-XML-Endpunkte mit Degraded-Mode-Ausgabe.

*Ergänzende Tools & Ökosystembetrieb*
- **[HYDRA-UMC-DASHBOARD-AI](https://github.com/JuanenRac/HYDRA-UMC-DASHBOARD-AI)** — Smart-Summaries- und Anomaly-Highlighting-Panels über DATALAKE/ANOMALY-DETECTOR, mit einem ehrlichen statistischen Fallback.
- **[HYDRA-UMC-TOOL-CLI](https://github.com/JuanenRac/HYDRA-UMC-TOOL-CLI)** — Flotten-CLI mit einem echten, stabilen Exit-Code-Vertrag, ein echter Live-Client der eigenen API von HYDRA-UMC-SERVER.
- **[HYDRA-UMC-WATCH](https://github.com/JuanenRac/HYDRA-UMC-WATCH)** — WearOS-Begleit-App mit echten haptischen Alarmen und einem Sprach-Relay zum gekoppelten Telefon.
- **[URTC-SMART-RACK](https://github.com/JuanenRac/URTC-SMART-RACK)** — Firmware für ein Platinenmontagegestell mit echter Werkzeug-ID-Dekodierung und Smart-Idle-Vorheizlogik.
- **[URTC-VISION-TOOL](https://github.com/JuanenRac/URTC-VISION-TOOL)** — Firmware plus ein echter Python-Vision-Begleiter für einen Thermal-/RGB-Inspektionswerkzeugkopf.
- **[HYDRA-UMC-UPDATER](https://github.com/JuanenRac/HYDRA-UMC-UPDATER)** — administratives Desktop-Tool, das jedes Repository in diesem Ökosystem entdeckt, klont und aktualisiert.

---

## 📚 Dokumentation & Community

- **[CONTRIBUTING.md](CONTRIBUTING.md)** — Technologie-Stack und Coding-Richtlinien für einen Pull Request.
- **[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)** — die in dieser Community erwarteten Verhaltensstandards.
- **[SECURITY.md](SECURITY.md)** — wie man eine Schwachstelle meldet, und die echten Sicherheitsschwerpunkte dieses Projekts.
- **[SUPPORT.md](SUPPORT.md)** — wo man Fragen stellt und Fehler meldet.
- **[LICENSE.md](LICENSE.md)** — die eigene Lizenz dieses Projekts.

## 👤 AUTOR
**JuanenRac** (Electro Hobby 3D)
📧 electrohobby3d@gmail.com
📺 [youtube.com/@electrohobby3d](https://youtube.com/@electrohobby3d)

## 📜 LIZENZ
GPL-3.0 - Siehe LICENSE für Details.
