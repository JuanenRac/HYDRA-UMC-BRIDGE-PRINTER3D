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
* ✅ **Build/test non mutante:** `build-test.bat`/`.sh` compilano il parser delle risposte e la porta di sicurezza senza inviare G-code, cambiare versioni o toccare una stampante. *(implementato, vedi COMPILAZIONE ED ESECUZIONE più sotto)*
* 🔜 **Controllo reale della stampante (comandi G-code)** — rimandato fino a disporre di un profilo testato, autenticazione e revisione di sicurezza fisica. *(pianificato)*

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
* **Perché i comandi reali (G-code) richiedono prima un profilo testato, autenticazione e revisione di sicurezza fisica.** L'API di Moonraker può accettare G-code arbitrario; inviarlo senza un profilo validato e autenticazione aggirerebbe proprio il controllo di prontezza che questo ponte esiste per far rispettare.
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
│       └── moonraker.py         # Porta di sicurezza MoonrakerProbe + PrinterBridge
├── tests/
│   ├── test_artifacts.py         # Test di evidenza slicer (senza I/O stampante)
│   └── test_moonraker.py        # Test di analisi della prontezza e porta fail-safe
├── tools/
│   ├── build_test.py            # Compilatore + esecutore di test non mutante (build-test.bat/.sh)
│   ├── inspect_print_artifact.py # CLI JSON dell'evidenza locale dell'artefatto
│   └── bump_version.py          # Sincronizza pyproject.toml, manifesto e CHANGELOG.md
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

**Reale oggi:** versione `0.0.7`, un adattatore di prontezza Moonraker testato in locale (`MoonrakerProbe` + `PrinterBridge`) appoggiato sulla porta di lavoro condivisa di `HYDRA-UMC-SDK`, evidenza in sola lettura di artefatti G-code/3MF/slice di resina e compatibilità del profilo, una suite `unittest` deterministica di diciassette test che include la verifica del contratto HTTP locale `/printer/info`, e script build-test non mutanti collegati alla CI con checkout dell'SDK.

**Confine di integrazione:** il firmware nativo della stampante (Klipper via Moonraker) mantiene sempre il movimento, i riscaldatori, la protezione termica e gli interblocchi macchina; questo ponte si limita a leggere la prontezza e a regolare il lavoro robotico *ausiliario* attorno ad essa.

**Ancora da fare:** il ponte non ha mai controllato una stampante, un hotend o un robot reali — inviare comandi reali richiede prima un profilo di stampante testato, autenticazione e una revisione di sicurezza fisica.

---

## 🔗 PROGETTI CORRELATI

Questo progetto fa parte di un ecosistema robotico più ampio dello stesso autore (JuanenRac / Electro Hobby 3D), che copre firmware, software di controllo, nodi IA e strumenti di flotta. Vale la pena saperlo, perché una richiesta potrebbe in realtà riguardare uno di questi progetti anziché questo repository.

### Direttamente correlati

- **[HYDRA-UMC-SDK](https://github.com/JuanenRac/HYDRA-UMC-SDK)** — la porta di lavoro condivisa `bridge_contract` attraverso cui questo ponte (e tutti gli altri) valuta i propri lavori.
- **[HYDRA-UMC-SERVER](https://github.com/JuanenRac/HYDRA-UMC-SERVER)** — l'endpoint di coordinamento autorizzato a cui questo ponte riporta.
- **[HYDRA-UMC-SAFETY-ZONES](https://github.com/JuanenRac/HYDRA-UMC-SAFETY-ZONES)** — futura evidenza di sicurezza dell'area di lavoro.

### Resto dell'ecosistema

**Piattaforma HYDRA-UMC** — la micro-fabbrica multi-robot per cui questo ponte coordina gli ausiliari
- **[HYDRA-UMC](https://github.com/JuanenRac/HYDRA-UMC)** — la scheda madre CM5 + STM32H745 che orchestra fino a 8 bracci robotici.
- **[HYDRA-UMC-SERVER](https://github.com/JuanenRac/HYDRA-UMC-SERVER)** — il backend Express/WebSocket con cui parlano tutti i client di controllo e i ponti.
- **[HYDRA-UMC-STUDIO](https://github.com/JuanenRac/HYDRA-UMC-STUDIO)** — dashboard di controllo web, visualizzazione 3D multi-robot.

**External Automation Bridges** — repository fratelli che condividono questa stessa porta di lavoro `HYDRA-UMC-SDK`
- **[HYDRA-UMC-BRIDGE-CNC](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-CNC)** — ponte di coordinamento cella CNC.
- **[HYDRA-UMC-BRIDGE-LASER](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-LASER)** — ponte di coordinamento celle laser.
- **[HYDRA-UMC-BRIDGE-OPENPNP](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-OPENPNP)** — ponte di flusso schede per OpenPnP.
- **[HYDRA-UMC-BRIDGE-ROS2](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-ROS2)** — confine di coordinamento bidirezionale con ROS 2.

**Evidenze di sicurezza e integrazione**
- **[HYDRA-UMC-SAFETY-ZONES](https://github.com/JuanenRac/HYDRA-UMC-SAFETY-ZONES)** — evidenze di sicurezza delle zone di cella usate in tutta la famiglia di ponti.
- **[HYDRA-UMC-HIL-BRIDGE](https://github.com/JuanenRac/HYDRA-UMC-HIL-BRIDGE)** — evidenze di test hardware-in-the-loop.

## 👤 AUTORE
**JuanenRac** (Electro Hobby 3D)
📧 electrohobby3d@gmail.com

## 📜 LICENZA
GPL-3.0 - Vedi LICENSE per i dettagli.
