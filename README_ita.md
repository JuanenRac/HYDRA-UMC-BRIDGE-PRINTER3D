<!-- =============================================================================
HYDRA-UMC-BRIDGE-PRINTER3D - Ponte software per stampa 3D
Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
GPL-3.0-or-later - see LICENSE
============================================================================= -->

<p align="center">
  <img src="images/HYDRA_UMC_BANNER.svg" alt="Banner HYDRA-UMC-BRIDGE-PRINTER3D" width="100%">
</p>

# 🖨️ HYDRA-UMC-BRIDGE-PRINTER3D

<p align="center"><a href="README.md">🇺🇸 English</a> | <a href="README_spa.md">🇪🇸 Español</a> | <a href="README_fra.md">🇫🇷 Français</a> | 🇮🇹 <b>Italiano</b> | <a href="README_deu.md">🇩🇪 Deutsch</a> | <a href="README_zho.md">🇨🇳 简体中文</a> | <a href="README_jpn.md">🇯🇵 日本語</a></p>

### 🌡️ Ponte di coordinamento fail-safe per software di stampa 3D open

<p align="left">
  <img src="https://img.shields.io/badge/Licenza-GPL%203.0-blue.svg" alt="GPL 3.0">
  <img src="https://img.shields.io/badge/Python-3.11%2B-3776AB.svg" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/Safety-Fails%20Closed-red.svg" alt="Fail-safe">
</p>

---

## 1. 🛠️ PANORAMICA TECNICA

**HYDRA-UMC-BRIDGE-PRINTER3D** è il coordinatore di alto livello per software di stampa 3D open (Moonraker/Klipper) e ausiliari robotici HYDRA-UMC. Riconosce inoltre gli artefatti locali dello slicer in sola lettura. Il firmware nativo della stampante rimane sempre responsabile del movimento, dei riscaldatori, della protezione termica e degli interblocchi macchina — questo ponte legge soltanto la prontezza, registra l'evidenza dell'artefatto e coordina gli ausiliari attorno ad esso.

Appartiene alla famiglia **External Automation Bridges**: un insieme di repository fratelli (CNC, LASER, OPENPNP, PRINTER3D, ROS2) che condividono lo stesso contratto di sicurezza di `HYDRA-UMC-SDK`, così nessun ponte può inventare una propria definizione di "sicuro per lavorare".

### Caratteristiche principali:
* ✅ **Sonda di prontezza Moonraker, reale:** `moonraker.py` — `MoonrakerProbe` consuma l'endpoint documentato `/printer/info` di Moonraker con un piccolo client basato esclusivamente sulla libreria standard (`urlopen` + `json`) — nessuna dipendenza aggiuntiva oltre alla libreria standard di Python. *(implementato, testato in `tests/test_moonraker.py`)*
* ✅ **Analisi dello stato fail-safe, reale:** `parse_info()` mappa solo la stringa letterale `"ready"` su `MachineState.IDLE`; `startup`/`shutdown`/`error` vengono mappati su `FAULT`, e qualsiasi altra cosa (inclusa una risposta malformata) su `OFFLINE` — mai su uno stato che permetterebbe di pianificare un robot attorno alla stampante. *(implementato)*
* ✅ **Porta di sicurezza condivisa, reale:** ogni lavoro osservato viene rivalutato tramite `evaluate_job()` del `bridge_contract` di `HYDRA-UMC-SDK`, la stessa porta usata da tutti i ponti fratelli e da HYDRA-UMC-SERVER. *(implementato)*
* ✅ **Ispezione di artefatti indipendente dallo slicer:** `artifacts.py` identifica G-code FDM semplice di OrcaSlicer, Ultimaker Cura, PrusaSlicer, Bambu Studio e altri slicer soltanto da evidenza locale; riconosce anche pacchetti 3MF e slice di resina compatibili Lychee senza estrarre, analizzare comandi, caricare o stampare. *(implementato, testato in `tests/test_artifacts.py`)*
* ✅ **Confine di evidenza del profilo:** `profiles.py` può abbinare un artefatto ispezionato a un profilo FDM o resina dichiarato, ma restituisce `execution_authorized=False` anche in caso di corrispondenza. *(implementato, testato in `tests/test_profiles.py`)*
* ✅ **Comandi di lavoro reali, controllati dall'SDK:** `MoonrakerJobControl` invia vere richieste `POST` agli endpoint documentati `/printer/print/start|pause|resume|cancel` di Moonraker — `start_job()` è subordinato alla stessa decisione di `evaluate_job()` usata da ogni dispatch produttivo di questo ecosistema; `pause_job()`/`cancel_job()` sono sempre consentiti (stesso ragionamento di de-escalation di `ABORT`); `resume_job()` richiede una stampante realmente in `HOLDING`. Avvia solo per nome un file già caricato e già affettato — non trasmette mai G-code grezzo. *(implementato, testato in `tests/test_moonraker.py`)*
* ✅ **Build/test non mutante:** `build-test.bat`/`.sh` compilano il parser delle risposte e la porta di sicurezza senza inviare G-code, cambiare versioni o toccare una stampante. *(implementato, vedi COMPILAZIONE ED ESECUZIONE più sotto)*
* 🔜 **Streaming di G-code grezzo** — deliberatamente ancora rimandato: inviare comandi arbitrari di basso livello (non un lavoro nominato già affettato) richiede un profilo testato, un'autenticazione e una revisione della sicurezza fisica che questo ponte non ha ancora. *(pianificato)*

---

## 2. 🔄 FLUSSO DI COORDINAMENTO DELLA STAMPANTE

```mermaid
flowchart LR
    PRINTER["Moonraker / Klipper<br/>(/printer/info)"] --> BRIDGE["BRIDGE-PRINTER3D<br/>MoonrakerProbe.parse_info()"]
    BRIDGE -- "BridgeJob + MachineState osservato" --> SDK["HYDRA-UMC-SDK<br/>evaluate_job()"]
    SDK -- GateDecision --> SERVER["HYDRA-UMC-SERVER"]
    SERVER -- "lavoro / abort" --> CELL["Sicurezza di cella"]
```

---

## 3. 🧱 ARCHITETTURA E DECISIONI DI PROGETTAZIONE

* **Perché solo lo stato letterale `"ready"` di Moonraker viene mappato su riposo.** La mappatura di stato di `parse_info()` è deliberatamente ristretta: `ready` → `IDLE`, `startup`/`shutdown`/`error` → `FAULT` (fail-safe), e qualsiasi altro valore o valore assente → `OFFLINE`. Non esiste alcuna assunzione di "sicuro per default" per uno stato della stampante non riconosciuto.
* **Perché il parsing è un `@staticmethod` separato dal recupero di rete.** `MoonrakerProbe.parse_info()` accetta un semplice `dict` ed è interamente testabile con unit test senza una chiamata di rete o una stampante in funzione; `fetch()` è la parte sottile e necessariamente di rete che lo richiama. La logica rilevante per la sicurezza risiede nella parte che non richiede mai una stampante reale per essere testata.
* **Perché la sonda usa `urlopen`/`json` della libreria standard invece di una libreria client Moonraker.** Mantenere la superficie di dipendenza limitata alla libreria standard di Python mantiene il parsing rilevante per la sicurezza minimo, verificabile e privo delle assunzioni proprie di un client di terze parti su tentativi, timeout o gestione degli errori.
* **Perché il ponte costruisce un nuovo `BridgeJob` e delega al `evaluate_job()` condiviso invece di scrivere una propria logica di accettazione/rifiuto.** Tutti e cinque gli External Automation Bridges (CNC, LASER, OPENPNP, PRINTER3D, ROS2) riutilizzano esattamente lo stesso `bridge_contract` di `HYDRA-UMC-SDK`, così "cosa conta come sicuro per avviare un lavoro" non può divergere silenziosamente tra loro.
* **Perché i comandi di lavoro (start/pause/resume/cancel) sono reali ma lo streaming di G-code grezzo non lo è ancora.** Gli endpoint `/printer/print/*` di Moonraker fanno sempre riferimento solo a un file già caricato e già affettato, per nome - lo stesso involucro di sicurezza che Moonraker/Klipper già applicano a quel file. Il G-code grezzo arbitrario è una superficie di fiducia fondamentalmente diversa e molto più ampia (può contenere qualsiasi cosa) e richiede ancora un profilo testato, un'autenticazione e una revisione della sicurezza fisica che questo ponte non ha ancora.
* **Perché `resume_job()` non riutilizza la porta generica `evaluate_job()`.** Quella porta è costruita attorno a "il lavoro produttivo richiede una macchina IDLE" - l'opposto della ripresa di un lavoro in pausa, che ha senso solo da `HOLDING`. Stesso ragionamento di porta autonoma già usato per `stand_request()`/`sit_request()` di DROIDS.
* **Come si inserisce nel resto dell'ecosistema.** BRIDGE-PRINTER3D si trova tra Moonraker/Klipper e `HYDRA-UMC-SDK` → `HYDRA-UMC-SERVER` → sicurezza di cella: coordina il lavoro robotico ausiliario attorno alla stampante, non sostituisce mai il firmware nativo, i riscaldatori o la protezione termica.

## 🧾 COMPATIBILITÀ DEGLI ARTEFATTI DELLO SLICER

Il canale di artefatti in sola lettura supporta il normale G-code FDM (`.gcode`, `.gco`, `.gc`) prodotto da OrcaSlicer, Ultimaker Cura, PrusaSlicer, Bambu Studio e altri slicer. I commenti noti forniscono un indizio di origine; senza marcatore resta `unknown-slicer`. I file `.gcode.3mf` e `.3mf` generici vengono identificati ma mai estratti. Le slice di resina (`.ctb`, `.goo`, `.photon`, `.pwmo`, `.pws`, `.sl1`) da flussi compatibili Lychee sono deliberatamente opache e non vengono mai attribuite a una stampante o a uno slicer specifico.

Questa è compatibilità con gli **artefatti di output**, non controllo remoto delle applicazioni. Il ponte non avvia slicer, non modifica profili, non analizza/esegue G-code, non carica file, non contatta servizi cloud e non avvia stampe. Vedere [Compatibilità degli artefatti dello slicer](docs/SLICER_ARTIFACT_COMPATIBILITY.md) per la matrice precisa e i prerequisiti di controllo futuro.

---

## 📂 STRUTTURA DELLE DIRECTORY

```text
HYDRA-UMC-BRIDGE-PRINTER3D/
├── src/
│   └── hydra_umc_bridge_printer3d/
│       ├── __init__.py
│       ├── artifacts.py         # Evidenza in sola lettura G-code, 3MF e slice di resina
│       ├── profiles.py          # Evidenza di compatibilità del profilo; mai autorizzazione di stampa
│       ├── moonraker.py         # Porta di sicurezza MoonrakerProbe + PrinterBridge
│       └── mqtt_transport.py    # Trasporto MQTT reale per la logica Moonraker già reale di questo bridge
├── tests/
│   ├── test_artifacts.py         # Test di evidenza slicer (senza I/O stampante)
│   ├── test_profiles.py         # La corrispondenza dei profili nega sempre l'esecuzione
│   ├── test_moonraker.py        # Test di analisi della prontezza e porta fail-safe
│   └── test_mqtt_transport.py   # Test di forma comando/stato MQTT contro un client broker fittizio
├── tools/
│   ├── build_test.py            # Compilatore + esecutore di test non mutante (build-test.bat/.sh)
│   ├── inspect_print_artifact.py # CLI JSON dell'evidenza locale dell'artefatto
│   ├── assess_print_profile.py  # CLI di confronto profilo/artefatto offline; non autorizza mai l'esecuzione
│   ├── ci_validate.py           # Base CI priva di dipendenze e non distruttiva (usata da .github/workflows/ci.yml)
│   └── bump_version.py          # Sincronizza pyproject.toml, manifesto e CHANGELOG.md
├── docs/
│   ├── BRIDGE_GUIDE.md                        # Ambito, piattaforme compatibili, script, porta di accettazione hardware
│   ├── PRINT_PROFILE_BOUNDARY.md              # Cosa significa l'evidenza di compatibilità del profilo rispetto all'autorizzazione di stampa
│   └── SLICER_ARTIFACT_COMPATIBILITY.md       # Quali formati di artefatto slicer questo bridge può leggere come evidenza
├── images/
│   └── HYDRA_UMC_BANNER.svg     # Banner del README
├── build-test.bat / build-test.sh  # Solo valida, non modifica mai il repository
├── build.bat / build.sh            # Valida e, solo in caso di successo, aggiorna versione + CHANGELOG
├── pyproject.toml               # Metadati del pacchetto; dipende da HYDRA-UMC-SDK (git)
├── hydra-umc.project.json       # Manifesto dell'ecosistema (versione, maturità, famiglia)
├── CHANGELOG.md
├── CODE_OF_CONDUCT.md / CONTRIBUTING.md / SECURITY.md / SUPPORT.md
├── LICENSE / LICENSE.md
└── README.md / README_*.md      # Questo file e le sue 6 traduzioni
```

---

## 4. ⚙️ COMPILAZIONE ED ESECUZIONE

Richiede Python 3.11+. `tools/build_test.py` si aspetta che `HYDRA-UMC-SDK` sia clonato come directory fratella (`../HYDRA-UMC-SDK`) o indicato tramite la variabile d'ambiente `HYDRA_UMC_SDK_ROOT`.

```bash
# Windows
build-test.bat      # solo validazione — nessun cambio di versione/CHANGELOG
build.bat            # valida e, se ha successo, aggiorna versione + CHANGELOG

# Linux/macOS
bash build-test.sh
bash build.sh
```

`build-test` compila ogni modulo in `src/` e `tools/` con `py_compile` ed esegue l'intera suite `unittest` (`tests/test_moonraker.py` e `tests/test_artifacts.py`), dimostrando l'analisi della prontezza, l'ispezione degli artefatti e la porta fail-safe — non invia G-code, non tocca alcuna stampante e non modifica mai il repository. `build` esegue prima quella stessa validazione e, solo in caso di successo, chiama `tools/bump_version.py` per sincronizzare la versione in `pyproject.toml`, `hydra-umc.project.json` e `CHANGELOG.md`. Non esiste ancora un comando `run` stampante reale — serve prima un profilo testato, autenticazione e revisione di sicurezza fisica.

Per ispezionare un output locale dello slicer senza contattare una stampante:

```bash
py tools/inspect_print_artifact.py percorso/del/lavoro.gcode
```

---

## ✅ STATO ATTUALE E PROSSIMI PASSI

**Reale oggi:** versione `0.1.0`, un adattatore di prontezza Moonraker testato in locale (`MoonrakerProbe` + `PrinterBridge`) appoggiato sulla porta di lavoro condivisa di `HYDRA-UMC-SDK`, veri comandi di lavoro controllati dall'SDK (`MoonrakerJobControl`: avviare/mettere in pausa/riprendere/annullare un file già caricato tramite la vera API REST di Moonraker), evidenza in sola lettura di artefatti G-code/3MF/slice di resina e compatibilità del profilo per le principali famiglie di slicer, una suite `unittest` deterministica di quarantanove test che include la verifica del contratto HTTP locale `/printer/info`, il vero e separato contratto `/printer/objects/query?print_stats=state`, e la vera verifica dei comandi di lavoro `POST`, e script build-test non mutanti collegati alla CI con checkout dell'SDK.

**Confine di integrazione:** il firmware nativo della stampante (Klipper via Moonraker) mantiene sempre il movimento, i riscaldatori, la protezione termica e gli interblocchi macchina; questo ponte si limita a leggere la prontezza e a regolare il lavoro robotico *ausiliario* attorno ad essa.

**Ancora da fare:** il ponte non ha mai controllato una stampante, un hotend o un robot reali — inviare comandi reali richiede prima un profilo di stampante testato, autenticazione e una revisione di sicurezza fisica.

---

## 🔗 Progetti Correlati

Questo progetto fa parte dell'ecosistema robotico HYDRA-UMC dello stesso autore (JuanenRac / Electro Hobby 3D). Vale la pena conoscerlo, poiché una richiesta potrebbe in realtà riguardare uno di questi invece di questo repository.

**Progetto Padre**
- **[HYDRA-UMC-SERVER](https://github.com/JuanenRac/HYDRA-UMC-SERVER)** — il vero backend headless (REST/WebSocket) con cui parla davvero ogni client di controllo; il confine autenticato dell'ecosistema a cui questo bridge riporta una volta che ogni comando ha superato la barriera di sicurezza locale di questo stesso bridge.

**Progetti Fratelli** — parlano anch'essi con la stessa API di HYDRA-UMC-SERVER, ciascuno come proprio client
- **[HYDRA-UMC-STUDIO](https://github.com/JuanenRac/HYDRA-UMC-STUDIO)** — dashboard di controllo web con visualizzazione 3D multi-robot in tempo reale.
- **[HYDRA-UMC-SUITE](https://github.com/JuanenRac/HYDRA-UMC-SUITE)** — centro di comando sciame desktop (PySide6) per più server contemporaneamente, pacchettizzato come eseguibile standalone.
- **[HYDRA-UMC-ANDROID-CONTROL](https://github.com/JuanenRac/HYDRA-UMC-ANDROID-CONTROL)** — app di controllo nativa per Android con login biometrico e un companion Wear OS abbinato.
- **[HYDRA-UMC-IOS-CONTROL](https://github.com/JuanenRac/HYDRA-UMC-IOS-CONTROL)** — app di controllo per iOS/iPadOS (Flutter) con sincronizzazione WebSocket in tempo reale.
- **[HYDRA-UMC-DSI](https://github.com/JuanenRac/HYDRA-UMC-DSI)** — interfaccia touch nativa per il touchscreen DSI da 7" a bordo, incorporata direttamente nel CM5.
- **[HYDRA-UMC-BRIDGE-AMR](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-AMR)** — barriera di coordinamento per flotte AGV/AMR tramite un publisher MQTT VDA 5050 reale.
- **[HYDRA-UMC-BRIDGE-CNC](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-CNC)** — coordinatore ad alto livello per celle CNC con accesso reale a stato/byte di controllo GRBL.
- **[HYDRA-UMC-BRIDGE-DROIDS](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-DROIDS)** — barriera di coordinamento per droidi con zampe/umanoidi, con un vero mittente di comandi per Boston Dynamics Spot.
- **[HYDRA-UMC-BRIDGE-LASER](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-LASER)** — coordinatore di sicurezza per celle laser che legge 3 salvaguardie GPIO reali di chiave/involucro/interblocco.
- **[HYDRA-UMC-BRIDGE-OPENPNP](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-OPENPNP)** — coordinatore ad alto livello sicuro per il flusso schede del pick-and-place OpenPnP.
- **[HYDRA-UMC-BRIDGE-ROS2](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-ROS2)** — coordinatore di sicurezza con un vero trasporto ROS 2 rclpy, importato in modo lazy.
- **[HYDRA-UMC-BRIDGE-UAV](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-UAV)** — barriera di coordinamento per UAV dotati di fotocamera, con un vero mittente di comandi MAVLink.

**Direttamente Correlati**
- **[HYDRA-UMC-SDK](https://github.com/JuanenRac/HYDRA-UMC-SDK)** — il contratto JSON-Schema condiviso e la barriera di sicurezza contro cui ogni bridge valida i propri comandi.
- **[HYDRA-UMC-MQTT-BROKER](https://github.com/JuanenRac/HYDRA-UMC-MQTT-BROKER)** — il vero trasporto di `mqtt_transport.py` per i propri topic `hydra/bridges/printer3d/...` di questo bridge — stato più i comandi reali Moonraker start/pause/resume/cancel, insieme alla barriera di lavoro condivisa; vedi il proprio `docs/BRIDGE_TOPICS.md` di quel repository.
- **[HYDRA-UMC-SAFETY-ZONES](https://github.com/JuanenRac/HYDRA-UMC-SAFETY-ZONES)** — futura evidenza di sicurezza dello spazio di lavoro per questo bridge.

**Fa Anche Parte dell'Ecosistema**

*Hardware e Piattaforma di Base*
- **[HYDRA-UMC](https://github.com/JuanenRac/HYDRA-UMC)** — la scheda madre fisica del braccio robotico: host CM5 + coprocessore STM32H745 dual-core, che coordina fino a 8 bracci utensile via CAN-OTA/SPI-OTA.
- **[HYDRA-UMC-OS](https://github.com/JuanenRac/HYDRA-UMC-OS)** — livello prodotto riproducibile su Raspberry Pi OS per il CM5: agente in sola lettura, config/profili validati, provisioning WiFi al primo contatto.

*Backend Centrale e Client*
- **[HYDRA-UMC-EDITOR-URDF](https://github.com/JuanenRac/HYDRA-UMC-EDITOR-URDF)** — creatore/editor grafico desktop di URDF che invia i modelli finiti al catalogo di STUDIO.

*Piattaforma Strumenti URTC*
- **[URTC](https://github.com/JuanenRac/URTC)** — firmware per la scheda fisica dell'Universal Robot Tool Controller, oltre 25 profili utensile su bus CAN.
- **[URTC-FLASHER](https://github.com/JuanenRac/URTC-FLASHER)** — strumento desktop con GUI per il flashing delle schede URTC, CAN-OTA più SWD/JTAG a chip intero.
- **[URTC-TESTER](https://github.com/JuanenRac/URTC-TESTER)** — strumento desktop di diagnostica CAN-bus dal vivo per schede URTC, un pannello per profilo utensile.
- **[URTC-WEB-STUDIO](https://github.com/JuanenRac/URTC-WEB-STUDIO)** — alternativa basata su browser a URTC-TESTER tramite la Web Serial API, senza installazione locale.

*Nodo IA Visione (Hailo-8)*
- **[HYDRA-UMC-VISION-NODE](https://github.com/JuanenRac/HYDRA-UMC-VISION-NODE)** — hub di integrazione per la pipeline di visione Hailo-8, con un vero controllo di prontezza hardware per fase.
- **[HYDRA-UMC-DETECTION-HEF](https://github.com/JuanenRac/HYDRA-UMC-DETECTION-HEF)** — registro reale di modelli compilati con verifica di caricamento sicuro per architettura Hailo/checksum.
- **[HYDRA-UMC-VISION-STREAMER](https://github.com/JuanenRac/HYDRA-UMC-VISION-STREAMER)** — generatore reale di pipeline GStreamer + config MediaMTX, con una vera barriera di integrazione HailoRT.
- **[HYDRA-UMC-VISUAL-SERVOING-API](https://github.com/JuanenRac/HYDRA-UMC-VISUAL-SERVOING-API)** — vera legge di correzione Position-Based Visual Servoing, con cancello di sicurezza sullo stato di zona a monte.

*Nodo IA Cognitivo (Hailo-10)*
- **[HYDRA-UMC-COGNITIVE-NODE](https://github.com/JuanenRac/HYDRA-UMC-COGNITIVE-NODE)** — hub di integrazione per la pipeline cognitiva Hailo-10 (orchestrazione LLM/VLA/voce).
- **[HYDRA-UMC-VLA-ENGINE](https://github.com/JuanenRac/HYDRA-UMC-VLA-ENGINE)** — vera codifica/decodifica di token d'azione e generazione di traiettoria per un modello Vision-Language-Action.
- **[HYDRA-UMC-VOICE-UI](https://github.com/JuanenRac/HYDRA-UMC-VOICE-UI)** — vero front-end vocale (VAD + parser di intenti) con un relay verso Watch limitato e soggetto a conferma.
- **[HYDRA-UMC-SEMANTIC-PLANNER](https://github.com/JuanenRac/HYDRA-UMC-SEMANTIC-PLANNER)** — vera scomposizione dei task basata su regole e recupero semantico degli errori sui codici errore MCU.
- **[HYDRA-UMC-DOCS-QA](https://github.com/JuanenRac/HYDRA-UMC-DOCS-QA)** — vera ricerca documentale TF-IDF (solo libreria standard) sui documenti Markdown di questo ecosistema.

*Orchestrazione e Sciame*
- **[HYDRA-UMC-ORCHESTRATOR](https://github.com/JuanenRac/HYDRA-UMC-ORCHESTRATOR)** — hub di integrazione con un vero contratto di health-report gRPC/Protobuf e una macchina a stati di missione.
- **[HYDRA-UMC-JOB-DISPATCHER](https://github.com/JuanenRac/HYDRA-UMC-JOB-DISPATCHER)** — vera coda di lavori basata su priorità con deduplicazione, su una vera API HTTP.
- **[HYDRA-UMC-NODE-HEALING](https://github.com/JuanenRac/HYDRA-UMC-NODE-HEALING)** — vero watchdog di salute della flotta basato su gRPC, con retry/backoff e rilevamento di discrepanza d'identità.
- **[HYDRA-UMC-PATH-PLANNER-3D](https://github.com/JuanenRac/HYDRA-UMC-PATH-PLANNER-3D)** — vero pianificatore di percorsi 3D basato su RRT, con vera validazione delle collisioni ostacolo/spazio di lavoro.
- **[HYDRA-UMC-SWARM-SYNC](https://github.com/JuanenRac/HYDRA-UMC-SWARM-SYNC)** — vera sincronizzazione di stato CRDT LWW-Element-Map, con property test per la convergenza multi-cella.

*Gemello Digitale e Simulazione*
- **[HYDRA-UMC-TWIN](https://github.com/JuanenRac/HYDRA-UMC-TWIN)** — hub di integrazione per il motore di gemello digitale, con un vero contratto di sincronizzazione per compatibilità di versione.
- **[HYDRA-UMC-HIL-BRIDGE](https://github.com/JuanenRac/HYDRA-UMC-HIL-BRIDGE)** — vero interblocco di sicurezza hardware-in-the-loop che instrada i comandi tra simulazione e hardware reale.
- **[HYDRA-UMC-PHYSICS-REPLICA](https://github.com/JuanenRac/HYDRA-UMC-PHYSICS-REPLICA)** — vera cinematica diretta e validazione dei limiti articolari su un vero sottoinsieme URDF.
- **[HYDRA-UMC-SYNTHETIC-DATA-GEN](https://github.com/JuanenRac/HYDRA-UMC-SYNTHETIC-DATA-GEN)** — vero generatore procedurale di scene 2D con esportazione di annotazioni YOLO/COCO.

*Dati e Analisi*
- **[HYDRA-UMC-DATALAKE](https://github.com/JuanenRac/HYDRA-UMC-DATALAKE)** — vero archivio di serie temporali basato su sqlite3, con una vera API HTTP di ingestione/query.
- **[HYDRA-UMC-ANOMALY-DETECTOR](https://github.com/JuanenRac/HYDRA-UMC-ANOMALY-DETECTOR)** — vero rilevatore di anomalie FFT + baseline statistica, con monitoraggio della deriva.
- **[HYDRA-UMC-PRODUCTION-REPORTS](https://github.com/JuanenRac/HYDRA-UMC-PRODUCTION-REPORTS)** — vero calcolo OEE/disponibilità sullo storico di DATALAKE, con esportazione CSV riproducibile.
- **[HYDRA-UMC-TELEMETRY-COLLECTOR](https://github.com/JuanenRac/HYDRA-UMC-TELEMETRY-COLLECTOR)** — vera pipeline di ingestione CAN/WebSocket verso DATALAKE, con deduplicazione per sequenza.

*Gateway Industriale*
- **[HYDRA-UMC-GATEWAY-INDUSTRIAL](https://github.com/JuanenRac/HYDRA-UMC-GATEWAY-INDUSTRIAL)** — hub di integrazione che inoltra ai protocolli industriali, con un vero livello di allowlist dei comandi/backpressure.
- **[HYDRA-UMC-OPCUA-SERVER](https://github.com/JuanenRac/HYDRA-UMC-OPCUA-SERVER)** — vero spazio di indirizzi OPC-UA, verificato con una vera sessione client del protocollo binario.
- **[HYDRA-UMC-MTCONNECT-ADAPTER](https://github.com/JuanenRac/HYDRA-UMC-MTCONNECT-ADAPTER)** — veri endpoint XML `/probe` e `/current` di MTConnect, con output in modalità degradata.

*Strumenti Complementari e Operazioni dell'Ecosistema*
- **[HYDRA-UMC-DASHBOARD-AI](https://github.com/JuanenRac/HYDRA-UMC-DASHBOARD-AI)** — pannelli Smart Summaries e Anomaly Highlighting su DATALAKE/ANOMALY-DETECTOR, con un fallback statistico onesto.
- **[HYDRA-UMC-TOOL-CLI](https://github.com/JuanenRac/HYDRA-UMC-TOOL-CLI)** — CLI di flotta con un vero e stabile contratto di exit-code, un client live reale della stessa API di HYDRA-UMC-SERVER.
- **[HYDRA-UMC-WATCH](https://github.com/JuanenRac/HYDRA-UMC-WATCH)** — app companion WearOS con avvisi aptici reali e un relay vocale verso il telefono abbinato.
- **[URTC-SMART-RACK](https://github.com/JuanenRac/URTC-SMART-RACK)** — firmware per un rack di montaggio schede con decodifica reale dell'ID utensile e logica di preriscaldamento Smart Idle.
- **[URTC-VISION-TOOL](https://github.com/JuanenRac/URTC-VISION-TOOL)** — firmware più un vero companion di visione Python per una testa utensile di ispezione termica/RGB.
- **[HYDRA-UMC-UPDATER](https://github.com/JuanenRac/HYDRA-UMC-UPDATER)** — strumento amministrativo desktop che scopre, clona e aggiorna ogni repository di questo ecosistema.

## 👤 AUTORE
**JuanenRac** (Electro Hobby 3D)
📧 electrohobby3d@gmail.com
📺 [youtube.com/@electrohobby3d](https://youtube.com/@electrohobby3d)

## 📜 LICENZA
GPL-3.0 - Vedi LICENSE per i dettagli.
