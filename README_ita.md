<!-- =============================================================================
HYDRA-UMC-BRIDGE-PRINTER3D - 3D printer coordination bridge
Copyright (C) JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
GPL-3.0-or-later - see LICENSE
============================================================================= -->

<p align="center">
  <img src="images/HYDRA_UMC_BANNER.svg" alt="HYDRA-UMC-BRIDGE-PRINTER3D banner" width="100%">
</p>

# 🖨️ HYDRA-UMC-BRIDGE-PRINTER3D

<p align="center"><a href="README.md">🇺🇸 English</a> | <a href="README_spa.md">🇪🇸 Español</a> | <a href="README_fra.md">🇫🇷 Français</a> | 🇮🇹 <b>Italiano</b> | <a href="README_deu.md">🇩🇪 Deutsch</a> | <a href="README_zho.md">🇨🇳 简体中文</a> | <a href="README_jpn.md">🇯🇵 日本語</a> | <a href="README_por.md">🇵🇹 Português</a></p>

### 🌡️ Ponte di coordinamento fail-safe per software di stampa 3D open

<p align="center">
  <img src="https://img.shields.io/badge/License-GPL%203.0--or--later-blue.svg" alt="GPL 3.0 or later">
  <img src="https://img.shields.io/badge/Python-3.11%2B-3776AB.svg" alt="Python">
  <img src="https://img.shields.io/badge/Safety-Fails%20Closed-red.svg" alt="Safety">
  <img src="https://img.shields.io/badge/Tests-125%20passing-2ea44f.svg" alt="Tests">
  <img src="https://img.shields.io/badge/Version-0.1.9-0f6cbd.svg" alt="Version">
  <img src="https://img.shields.io/badge/Maturity-functional-0F6CBD.svg" alt="Maturity">
</p>

---

> **Verifica di onestà - cosa funziona davvero oggi:** la sonda di disponibilità Moonraker e il gate di sicurezza (`moonraker.py` con `MoonrakerProbe`/`PrinterBridge`, che fa passare ogni lavoro attraverso il vero `evaluate_job()` di `HYDRA-UMC-SDK`), i veri comandi di lavoro gestiti dall'SDK (`MoonrakerJobControl` di avvio/pausa/ripresa/annullamento), l'evidenza di sola lettura di artefatti/profili (`artifacts.py`, `profiles.py`), e il ponte comandi/stato MQTT (`mqtt_transport.py`) sono reali e coperti da 125 casi `unittest` superati (`python tools/build_test.py`). I test orientati a Moonraker girano contro un vero `ThreadingHTTPServer` locale che sostituisce la vera API REST di Moonraker - non una vera stampante -, e la logica propria di `connect_with_retry()`/instradamento messaggi dello strato MQTT è testata senza mai aprire una vera connessione o un vero broker `paho-mqtt`. Come già indica il README più sotto, questo bridge non è ancora stato testato contro una vera stampante, un vero hotend o un vero robot. Lo streaming di G-code grezzo non è deliberatamente implementato - può essere avviato/messo in pausa/ripreso/annullato per nome solo un file già caricato e già affettato. Vedi "Roadmap e limiti noti" qui sotto, che lo dice già chiaramente, e `CHANGELOG.md` per cosa è stato esattamente consegnato finora.

> **Stato di sicurezza (safety e security):** questo ecosistema non è un sistema di sicurezza certificato. Non esiste ancora un percorso E-STOP hardware, né limiti o interblocchi imposti dal firmware, né un comando di movimento verificato; le immagini firmware sono controllate con CRC-32 e una firma Ed25519, e una compilazione di rilascio rifiuta le chiavi di sviluppo pubblicate (le teste utensile e le schede di espansione dietro il relè usano ancora i bootloader di URTC, che accettano un HMAC-SHA256 a chiave condivisa invece di una firma); TLS e TLS reciproco sono opzionali e disattivati per impostazione predefinita; nessuna scheda propria è stata ancora assemblata o provata. Leggi la [base di sicurezza](https://github.com/JuanenRac/HYDRA-UMC-DOCS/blob/main/docs/SECURITY_BASELINE.md) e il [modello delle minacce](https://github.com/JuanenRac/HYDRA-UMC-DOCS/blob/main/docs/THREAT_MODEL.md) prima di fidarti di qualsiasi affermazione qui per la sicurezza di una persona.

---

## 📋 In breve

| | |
|---|---|
| Versione | `0.1.9` |
| Maturità | Funzionale |
| Test | 125 (`python tools/build_test.py`) |
| Tecnologia | Python / Moonraker / Klipper / G-code / 3MF |
| Destinazione | Il Raspberry Pi CM5 di una cella HYDRA-UMC |
| Su hardware reale | Solo simulato: provato con emulatori, test double o simulatori; per questa versione non risulta alcuna esecuzione su hardware reale |

**Vai a:** [Panoramica](#-panoramica) · [Architettura](#-architettura) · [Funzionalità](#-funzionalità) · [Sicurezza e protezione](#-sicurezza-e-protezione) · [Interfacce](#-interfacce) · [Configurazione](#-configurazione) · [Avvio rapido](#-avvio-rapido) · [Test](#-test) · [Risoluzione dei problemi](#-risoluzione-dei-problemi) · [Struttura del repository](#-struttura-del-repository) · [Progetti correlati](#-progetti-correlati)

## 🚦 Stato del progetto

Ogni riga è una parte di questo repository e il semaforo dice a che punto è oggi. È scritta in base a ciò che il repository può mostrare (test, compilazioni, esecuzioni), non a ciò che è previsto.

🟢 Fatto e verificato · 🟡 Funziona, con limiti noti · 🟠 Fatto a metà o non ancora verificato · 🔴 Non fatto o non funzionante

| Area | Stato | Cosa significa qui |
|---|---|---|
| Software | 🟡 | Funziona per il suo scopo principale; la verifica di onestà qui sopra elenca ciò che manca ancora |
| Test | 🟢 | 125 test automatici, eseguiti a ogni modifica |
| Hardware reale | 🟠 | Solo simulato: provato con emulatori, test double o simulatori; per questa versione non risulta alcuna esecuzione su hardware reale |
| Documentazione | 🟢 | README in otto lingue, verificato rispetto al manifesto a ogni modifica |

## 🎯 Panoramica

**HYDRA-UMC-BRIDGE-PRINTER3D** è il coordinatore di alto livello per software di stampa 3D open (Moonraker/Klipper) e ausiliari robotici HYDRA-UMC. Riconosce inoltre gli artefatti locali dello slicer in sola lettura e può inviare comandi di lavoro gestiti dall'SDK (avvio/pausa/ripresa/annullamento di un file già caricato e già processato, più un arresto di emergenza deciso) tramite la REST API propria di Moonraker; i test usano un server HTTP locale fittizio e nessuna stampante reale ne ha ricevuto uno. Il firmware nativo della stampante rimane sempre responsabile del movimento, dei riscaldatori, della protezione termica e degli interblocchi macchina — questo ponte non trasmette mai G-code grezzo e non sostituisce mai questa autorità; legge soltanto la prontezza, registra l'evidenza degli artefatti, invia comandi di livello lavoro già sicuri e coordina gli ausiliari attorno ad essa.

Appartiene alla famiglia **External Automation Bridges**: un insieme di repository fratelli (CNC, LASER, OPENPNP, PRINTER3D, ROS2) che condividono lo stesso contratto di sicurezza di `HYDRA-UMC-SDK`, così nessun ponte può inventare una propria definizione di "sicuro per lavorare".

## 🧩 Ruolo in HYDRA-UMC

**HYDRA-UMC-BRIDGE-PRINTER3D** sta tra una stampante 3D Moonraker/Klipper e la cella di robot. Riferisce ciò che dice quel lato, interroga la porta condivisa prima di qualsiasi lavoro ausiliario e non assume mai l'autorità della macchina con cui si coordina.

Ogni bridge parla il contratto di sicurezza condiviso di `HYDRA-UMC-SDK`: un lavoro viene accettato solo se la porta condivisa `evaluate_job()` lo permette, e quella porta fallisce chiusa. Il progetto padre è `HYDRA-UMC-SERVER`; questo bridge non lo chiama, risponde via MQTT, attraverso `HYDRA-UMC-MQTT-BROKER`, a chi comanda la cella.

## 🏛️ Architettura

<p align="center">
  <img src="images/architecture.svg" alt="HYDRA-UMC-BRIDGE-PRINTER3D architecture" width="100%">
</p>

<details>
<summary>Versione testuale del diagramma (Mermaid)</summary>

```mermaid
flowchart LR
    PRINTER["Moonraker / Klipper<br/>(/printer/info)"] --> BRIDGE["BRIDGE-PRINTER3D<br/>MoonrakerProbe.parse_info()"]
    BRIDGE -- "BridgeJob + MachineState osservato" --> SDK["HYDRA-UMC-SDK<br/>evaluate_job()"]
    SDK -- GateDecision --> RESULT["MQTT: cmd/job/result"]
```

</details>

**Perché è fatto così**

* **Perché solo lo stato letterale `"ready"` di Moonraker viene mappato su riposo.** La mappatura di stato di `parse_info()` è deliberatamente ristretta: `ready` → `IDLE`, `shutdown`/`error` → `FAULT`, `startup` → `OFFLINE` (fail-safe), e qualsiasi altro valore o valore assente → `OFFLINE`. Non esiste alcuna assunzione di "sicuro per default" per uno stato della stampante non riconosciuto.
* **Perché il parsing è un `@staticmethod` separato dal recupero di rete.** `MoonrakerProbe.parse_info()` accetta un semplice `dict` ed è interamente testabile con unit test senza una chiamata di rete o una stampante in funzione; `fetch()` è la parte sottile e necessariamente di rete che lo richiama. La logica rilevante per la sicurezza risiede nella parte che non richiede mai una stampante reale per essere testata.
* **Perché la sonda usa `urlopen`/`json` della libreria standard invece di una libreria client Moonraker.** Mantenere la superficie di dipendenza limitata alla libreria standard di Python mantiene il parsing rilevante per la sicurezza minimo, verificabile e privo delle assunzioni proprie di un client di terze parti su tentativi, timeout o gestione degli errori.
* **Perché il ponte costruisce un nuovo `BridgeJob` e delega al `evaluate_job()` condiviso invece di scrivere una propria logica di accettazione/rifiuto.** Tutti e cinque gli External Automation Bridges (CNC, LASER, OPENPNP, PRINTER3D, ROS2) riutilizzano esattamente lo stesso `bridge_contract` di `HYDRA-UMC-SDK`, così "cosa conta come sicuro per avviare un lavoro" non può divergere silenziosamente tra loro.
* **Perché i comandi di lavoro (start/pause/resume/cancel) sono reali ma lo streaming di G-code grezzo non lo è ancora.** Gli endpoint `/printer/print/*` di Moonraker fanno sempre riferimento solo a un file già caricato e già affettato, per nome - lo stesso involucro di sicurezza che Moonraker/Klipper già applicano a quel file. Il G-code grezzo arbitrario è una superficie di fiducia fondamentalmente diversa e molto più ampia (può contenere qualsiasi cosa) e richiede ancora un profilo testato, un'autenticazione e una revisione della sicurezza fisica che questo ponte non ha ancora.
* **Perché `resume_job()` non riutilizza la porta generica `evaluate_job()`.** Quella porta è costruita attorno a "il lavoro produttivo richiede una macchina IDLE" - l'opposto della ripresa di un lavoro in pausa, che ha senso solo da `HOLDING`. Stesso ragionamento di porta autonoma già usato per `stand_request()`/`sit_request()` di DROIDS.
* **Come si inserisce nel resto dell'ecosistema.** BRIDGE-PRINTER3D si trova tra Moonraker/Klipper e `HYDRA-UMC-SDK` → `HYDRA-UMC-MQTT-BROKER` → sicurezza di cella: coordina il lavoro robotico ausiliario attorno alla stampante, non sostituisce mai il firmware nativo, i riscaldatori o la protezione termica.

## ✨ Funzionalità

* ✅ **Sonda di prontezza Moonraker, reale:** `moonraker.py` — `MoonrakerProbe` consuma l'endpoint documentato `/printer/info` di Moonraker con un piccolo client basato esclusivamente sulla libreria standard (`urlopen` + `json`) — nessuna dipendenza aggiuntiva oltre alla libreria standard di Python. *(implementato, testato in `tests/test_moonraker.py`)*
* ✅ **Analisi dello stato fail-safe, reale:** `parse_info()` mappa solo la stringa letterale `"ready"` su `MachineState.IDLE`; `shutdown`/`error` vengono mappati su `FAULT`, e qualsiasi altra cosa (inclusa una risposta malformata) su `OFFLINE` — mai su uno stato che permetterebbe di pianificare un robot attorno alla stampante. *(implementato)*
* ✅ **Porta di sicurezza condivisa, reale:** ogni lavoro osservato viene rivalutato tramite `evaluate_job()` del `bridge_contract` di `HYDRA-UMC-SDK`, la stessa porta usata da tutti i ponti fratelli. *(implementato)*
* ✅ **Ispezione di artefatti indipendente dallo slicer:** `artifacts.py` identifica G-code FDM semplice di OrcaSlicer, Ultimaker Cura, PrusaSlicer, Bambu Studio e altri slicer soltanto da evidenza locale; riconosce anche pacchetti 3MF e slice di resina compatibili Lychee senza estrarre, analizzare comandi, caricare o stampare. *(implementato, testato in `tests/test_artifacts.py`)*
* ✅ **Confine di evidenza del profilo:** `profiles.py` può abbinare un artefatto ispezionato a un profilo FDM o resina dichiarato, ma restituisce `execution_authorized=False` anche in caso di corrispondenza. *(implementato, testato in `tests/test_profiles.py`)*
* ✅ **Comandi di lavoro reali, controllati dall'SDK:** `MoonrakerJobControl` invia vere richieste `POST` agli endpoint documentati `/printer/print/start|pause|resume|cancel` di Moonraker — `start_job()` è subordinato alla stessa decisione di `evaluate_job()` usata da ogni dispatch produttivo di questo ecosistema; `pause_job()`/`cancel_job()` sono sempre consentiti (stesso ragionamento di de-escalation di `ABORT`); `resume_job()` richiede una stampante realmente in `HOLDING`. Avvia solo per nome un file già caricato e già affettato — non trasmette mai G-code grezzo. *(implementato, testato in `tests/test_moonraker.py`)*
* ✅ **Build/test non mutante:** `build-test.bat`/`.sh` compilano il parser delle risposte e la porta di sicurezza senza inviare G-code, cambiare versioni o toccare una stampante. *(implementato, vedi Compilazione e rilascio più sotto)*
* 🔜 **Streaming di G-code grezzo** — deliberatamente ancora rimandato: inviare comandi arbitrari di basso livello (non un lavoro nominato già affettato) richiede un profilo testato, un'autenticazione e una revisione della sicurezza fisica che questo ponte non ha ancora. *(pianificato)*
* ✅ **Chiavi di idempotenza ripetute:** `PrinterMqttBridge` accetta un `IdempotencyStore`: una chiave di lavoro ripetuta riceve la risposta data la prima volta invece di essere valutata di nuovo, così che un `cmd/start` ripetuto non avvii mai una seconda stampa. *(implementato, testato in `tests/test_idempotency.py`)*
* ✅ **Ciclo MQTT blindato:** un payload troppo grande (oltre 16 KiB) o illeggibile, un JSON profondamente annidato e qualsiasi guasto inatteso ricevono un rifiuto sul topic di risultato e non terminano mai il ciclo; pausa, annullamento e il nuovo `cmd/emergency_stop` (M112 di Klipper) sono gestiti su una corsia propria, così un Moonraker lento non ritarda mai un arresto; le chiavi di idempotenza sono per verbo (`job:`/`start:`); le risposte di `cmd/job` riportano `"mode": "gate-only"` e un ABORT passato di lì dice che nulla è stato fermato; lo stato porta `observed_at` e il bridge si annuncia su un topic `availability` con Last Will; è supportata la chiave API di Moonraker (`MOONRAKER_API_KEY`, inviata come `X-Api-Key`) e un avvio viene inviato solo per un file che Moonraker conosce. *(implementato, testato in `tests/test_hardening.py`)*

### COMPATIBILITÀ DEGLI ARTEFATTI DELLO SLICER

Il canale di artefatti in sola lettura supporta il normale G-code FDM (`.gcode`, `.gco`, `.gc`) prodotto da OrcaSlicer, Ultimaker Cura, PrusaSlicer, Bambu Studio e altri slicer. I commenti noti forniscono un indizio di origine; senza marcatore resta `unknown-slicer`. I file `.gcode.3mf` e `.3mf` generici vengono identificati ma mai estratti. Le slice di resina (`.ctb`, `.goo`, `.photon`, `.pwmo`, `.pws`, `.sl1`) da flussi compatibili Lychee sono deliberatamente opache e non vengono mai attribuite a una stampante o a uno slicer specifico.

Questa è compatibilità con gli **artefatti di output**, non controllo remoto delle applicazioni. Il ponte non avvia slicer, non modifica profili, non analizza/esegue G-code, non carica file, non contatta servizi cloud e non avvia stampe. Vedere [Compatibilità degli artefatti dello slicer](docs/SLICER_ARTIFACT_COMPATIBILITY.md) per la matrice precisa e i prerequisiti di controllo futuro.

Una corrispondenza di artefatto/profilo resta solo un'evidenza, mai un permesso di stampa. [Print Profile Admission Boundary](docs/PRINT_PROFILE_BOUNDARY.md) documenta la validazione separata richiesta prima di qualsiasi futura operazione con un controllore nativo.

## 🔒 Sicurezza e protezione

| Minaccia | Difesa | Dove |
|---|---|---|
| Un lavoro per una cella o macchina che non è in stato sicuro | Ogni lavoro passa dalla porta condivisa `evaluate_job()` dell'SDK, che fallisce chiusa; il bridge non ha una logica propria di accettazione | SDK `bridge_contract` |
| Dati di lavoro smisurati | Al massimo 32 parametri, chiavi fino a 64 caratteri, valori fino a 1024, identificatori fino a 128 (`MAX_PARAMETERS`, `MAX_PARAMETER_KEY_CHARS`, `MAX_PARAMETER_VALUE_CHARS`, `MAX_IDENTIFIER_CHARS`) | SDK `bridge_contract` |
| Un ordine ripetuto o rinviato | Un `IdempotencyStore` ricorda ogni chiave per 24 ore e al massimo 10 000 voci; una ripetizione riceve la prima risposta invece di essere valutata di nuovo | SDK `job_intake` |
| Un payload MQTT enorme o ostile | Un payload oltre 16 KiB, un JSON illeggibile o molto annidato e qualsiasi errore imprevisto ricevono un rifiuto sul topic di risultato e non terminano mai il ciclo | `mqtt_transport.py` |
| Una stampante avviata da un ordine non sicuro | `MoonrakerJobControl` (avvio, pausa, ripresa, annullamento) agisce solo dietro la porta dell'SDK; il bridge legge lo stato e non controlla mai firmware né riscaldatori; i verbi di arresto `cmd/pause`, `cmd/cancel` e `cmd/emergency_stop` girano su una corsia propria | `moonraker.py`, `mqtt_transport.py` |
| Un file di stampa ostile | `artifacts.py` identifica un file senza decomprimerlo, eseguirlo né inviarlo (`.gcode.3mf` e `.3mf` hanno un'impronta, mai aperti); `profiles.py` associa solo la prova a un profilo dichiarato e non autorizza mai una stampa | `artifacts.py`, `profiles.py` |
| Una chiave API Moonraker esposta | La chiave viene inviata solo nell'intestazione `X-Api-Key` e letta da `MOONRAKER_API_KEY` | `moonraker.py` |

**Cosa non fa mai:** non controlla mai firmware né riscaldatori e non decomprime né esegue mai un file di stampa.

## 🔌 Interfacce

Topic sotto `hydra/bridges/printer3d/`; ogni comando riceve risposta su `<verbo>/result`.

| Topic o rotta | Cosa porta |
|---|---|
| `cmd/status`, `cmd/job` | lo stato della stampante; un `BridgeJob` con risposta `GateDecision` |
| `cmd/start`, `cmd/resume` | con porta: un vero `POST /printer/print/*` solo se la porta lo permette |
| `cmd/pause`, `cmd/cancel`, `cmd/emergency_stop` | i verbi di arresto, su una corsia propria |
| `state`, `availability` | lo stato trattenuto della stampante e `online`/`offline` |

## ⚙️ Configurazione

| Variabile | Predefinito | Cosa imposta |
|---|---|---|
| `MOONRAKER_API_KEY` | non impostata (nessuna chiave) | la chiave API di Moonraker, inviata come `X-Api-Key` |
| `HYDRA_MQTT_USERNAME` | nessuno | Il nome utente MQTT; il broker lo lega a un prefisso di ID client |
| `HYDRA_MQTT_PASSWORD` | nessuno | La password; valida solo insieme al nome utente |
| `HYDRA_MQTT_PASSWORD_FILE` | nessuno | La password letta da un file (segreto Docker o systemd); ignorata se `HYDRA_MQTT_PASSWORD` è impostata |
| `HYDRA_MQTT_TLS_CA` | nessuno | Il file della CA che ha firmato il certificato del broker: la connessione è TLS e il certificato viene verificato |
| `HYDRA_MQTT_TLS` | disattivato | `1` attiva TLS, verificato con le CA fidate del sistema |
| `HYDRA_MQTT_TLS_CERT` / `HYDRA_MQTT_TLS_KEY` | nessuno | Il certificato client e la sua chiave per un broker che richiede TLS reciproco; servono entrambi |

## 🚀 Avvio rapido

Richiede Python 3.11 o successivo. I test e gli script di build si aspettano `HYDRA-UMC-SDK` clonato accanto a questo repository (`../HYDRA-UMC-SDK`) o indicato con `HYDRA_UMC_SDK_ROOT`.

Provalo senza hardware (questo verifica tutto il bridge con i suoi emulatori e test double):

```bash
py -3 tools/build_test.py          # Windows
python3 tools/build_test.py         # Linux, macOS
```

Avviare il servizio (non c'è uno script da console: il servizio è il `run_forever()` del trasporto MQTT, che chiami dal tuo codice di avvio):

```python
from hydra_umc_bridge_printer3d.mqtt_transport import PrinterMqttBridge, run_forever
bridge = PrinterMqttBridge("http://192.168.0.50:7125", cell_state=lambda: cell_state)   # the Moonraker address; the key from MOONRAKER_API_KEY
run_forever(bridge, host="192.168.0.180")                                              # serves cmd/# forever
```

Nome utente, password e file TLS vengono dalle variabili `HYDRA_MQTT_*` (vedi Configurazione); il codice sopra non ha bisogno di credenziali proprie.

## 🧪 Test

125 casi `unittest` automatici si eseguono con `python tools/build_test.py` (che compila anche ogni modulo). I test non richiedono hardware, rete né pacchetti opzionali: quelli che richiederebbero `paho-mqtt`, `pyserial` o una libreria del produttore usano un sostituto o vengono saltati se il pacchetto manca.

| File di test | Test | Cosa copre |
|---|---|---|
| `test_moonraker.py` | - | lettura dello stato e comandi lavoro con porta contro un sostituto locale |
| `test_artifacts.py`, `test_profiles.py` | - | identificazione dei file e associazione ai profili |
| `test_mqtt_transport.py`, `test_mqtt_environment.py`, `test_hardening.py`, `test_edge_cases.py`, `test_idempotency.py` | - | smistamento dei topic, credenziali dell'ambiente, client ostili, casi limite, chiavi ripetute |

La CI esegue `HYDRA_UMC_CI=1 python tools/ci_validate.py`, che controlla il manifesto, i documenti, gli otto README e le immagini, ed esegue i test con una copia dell'SDK.

## 🏗️ Compilazione e rilascio

Richiede Python 3.11+. `tools/build_test.py` si aspetta che `HYDRA-UMC-SDK` sia clonato come directory fratella (`../HYDRA-UMC-SDK`) o indicato tramite la variabile d'ambiente `HYDRA_UMC_SDK_ROOT`.

```bash
# Windows
build-test.bat      # solo validazione — nessun cambio di versione/CHANGELOG
build.bat            # valida e, se ha successo, aggiorna versione + CHANGELOG

# Linux/macOS
bash build-test.sh
bash build.sh
```

`build-test` compila ogni modulo in `src/` e `tools/` con `py_compile` ed esegue l'intera suite `unittest` individuata sotto `tests/` (`test_moonraker.py`, `test_artifacts.py`, `test_profiles.py`, `test_mqtt_transport.py`, `test_hardening.py`, `test_idempotency.py`, `test_mqtt_environment.py` - 125 test), dimostrando l'analisi della prontezza, l'ispezione degli artefatti e la porta fail-safe tra tutto il resto coperto — non invia G-code, non tocca alcuna stampante e non modifica mai il repository. `build` esegue prima quella stessa validazione e, solo in caso di successo, chiama `tools/bump_version.py` per sincronizzare la versione in `pyproject.toml`, `hydra-umc.project.json` e `CHANGELOG.md`. Non esiste ancora un comando `run` stampante reale — serve prima un profilo testato, autenticazione e revisione di sicurezza fisica.

Per ispezionare un output locale dello slicer senza contattare una stampante:

```bash
py tools/inspect_print_artifact.py percorso/del/lavoro.gcode      # Windows
python3 tools/inspect_print_artifact.py percorso/del/lavoro.gcode  # Linux / macOS
```

## 🩺 Risoluzione dei problemi

| Vedi | Perché | Fai |
|---|---|---|
| `ModuleNotFoundError: hydra_umc_sdk` | L'SDK non è installato né accanto a questo repository | Clona `HYDRA-UMC-SDK` accanto a questo repository o imposta `HYDRA_UMC_SDK_ROOT` |
| `paho-mqtt is not installed` | Il client MQTT è un extra opzionale | `pip install ".[mqtt]"` (serve `paho-mqtt` 2.1 o successivo, inferiore a 3) |
| `password was given without a username` | Le credenziali MQTT richiedono entrambe le parti | Imposta anche `HYDRA_MQTT_USERNAME`, non solo la password |
| `could not reach the MQTT broker after N attempts` | Il broker è spento, l'indirizzo è sbagliato o la porta è chiusa | Avvia `HYDRA-UMC-MQTT-BROKER` e controlla host e porta dati al trasporto (5 tentativi a 2 secondi di distanza); un errore dell'handshake TLS non viene ritentato |
| `the MQTT broker refused the connection` | Il broker ha rifiutato la credenziale (o non ha risposto entro il tempo limite) | Controlla `HYDRA_MQTT_USERNAME` e la password; l'ID client deve iniziare con il prefisso che il broker ha legato alla credenziale |
| `"allowed": false` + `reason` | La porta condivisa o una guardia ha rifiutato l'ordine | Leggi `reason` e correggi la causa; non riprovare alla cieca |

## 📂 Struttura del repository

<p align="center">
  <img src="images/repository-structure.svg" alt="Repository structure of HYDRA-UMC-BRIDGE-PRINTER3D" width="100%">
</p>

<details>
<summary>Versione testuale dell'albero</summary>

```text
HYDRA-UMC-BRIDGE-PRINTER3D/
├── src/hydra_umc_bridge_printer3d/
│   ├── moonraker.py               stato della stampante e controllo lavori con porta
│   ├── artifacts.py               identifica i file di stampa, mai li decomprime
│   ├── profiles.py                associa la prova a un profilo dichiarato
│   └── mqtt_transport.py          trasporto MQTT di comandi e stato
├── tests/                         125 test, contro un sostituto locale di Moonraker
├── docs/                          guida del bridge, limite dei profili, file dello slicer
├── tools/                         esecutore di build e test, aumento di versione, validatore CI, generatori e controlli di README e immagini
├── images/                        banner e immagini del README
├── .github/                       workflow CI e modelli di segnalazione
├── pyproject.toml                 metadati del pacchetto e dipendenze
├── hydra-umc.project.json         manifesto: versione, maturità, famiglia
├── CHANGELOG.md                   cosa è cambiato in ogni versione
├── build.sh build.bat             script di build (non cambiano mai la versione)
├── build-test.sh build-test.bat   script di build (non cambiano mai la versione)
├── test.sh test.bat               eseguono i test
└── SECURITY.md SUPPORT.md CONTRIBUTING.md CODE_OF_CONDUCT.md LICENSE LICENSE.md
```

</details>

## 🗺️ Roadmap e limiti noti

**Limiti noti oggi**

**Reale oggi:** versione `0.1.9`, un adattatore di prontezza Moonraker testato in locale (`MoonrakerProbe` + `PrinterBridge`) appoggiato sulla porta di lavoro condivisa di `HYDRA-UMC-SDK`, veri comandi di lavoro controllati dall'SDK (`MoonrakerJobControl`: avviare/mettere in pausa/riprendere/annullare un file già caricato tramite la vera API REST di Moonraker), evidenza in sola lettura di artefatti G-code/3MF/slice di resina e compatibilità del profilo per le principali famiglie di slicer, una suite `unittest` deterministica di 125 test che include la verifica del contratto HTTP locale `/printer/info`, il vero e separato contratto `/printer/objects/query?print_stats=state`, e la vera verifica dei comandi di lavoro `POST`, e script build-test non mutanti collegati alla CI con checkout dell'SDK.

**Confine di integrazione:** il firmware nativo della stampante (Klipper via Moonraker) mantiene sempre il movimento, i riscaldatori, la protezione termica e gli interblocchi macchina; questo ponte legge la prontezza, invia solo comandi di livello lavoro già sicuri (mai G-code grezzo) e regola il lavoro robotico *ausiliario* attorno ad essa.

**Ancora da fare:** il ponte non è ancora stato provato con una stampante, un hotend o un robot reali (solo contro un server HTTP locale di prova) — una prima esecuzione su una stampante reale richiede prima un profilo di stampante testato e una revisione di sicurezza fisica; lo streaming di G-code grezzo non è volutamente implementato.

## 🌍 Lingue

Questo README e i documenti del repository esistono in otto lingue: inglese, spagnolo, tedesco, francese, italiano, giapponese, cinese e portoghese (Portogallo). Sono scritti insieme e la CI verifica che gli otto file abbiano le stesse sezioni e gli stessi link. Questo repository non ha uno schermo né un catalogo di messaggi propri, quindi non ci sono stringhe di interfaccia da tradurre.

## 🔗 Progetti correlati

Questo progetto fa parte dell'ecosistema robotico HYDRA-UMC dello stesso autore (JuanenRac / Electro Hobby 3D). Vale la pena conoscerlo, poiché una richiesta potrebbe in realtà riguardare uno di questi invece di questo repository.

**Progetto Padre**
- **[HYDRA-UMC-SERVER](https://github.com/JuanenRac/HYDRA-UMC-SERVER)** — il vero backend headless (REST/WebSocket) con cui parla davvero ogni client di controllo; questo bridge non lo chiama: risponde via MQTT, attraverso HYDRA-UMC-MQTT-BROKER, a chi comanda la cella.

**Progetti Fratelli** — parlano anch'essi con la stessa API di HYDRA-UMC-SERVER, ciascuno come proprio client
- **[HYDRA-UMC-STUDIO](https://github.com/JuanenRac/HYDRA-UMC-STUDIO)** — dashboard di controllo web con visualizzazione 3D multi-robot in tempo reale.
- **[HYDRA-UMC-SUITE](https://github.com/JuanenRac/HYDRA-UMC-SUITE)** — centro di comando sciame desktop (PySide6) per più server contemporaneamente, pacchettizzato come eseguibile standalone.
- **[HYDRA-UMC-ANDROID-CONTROL](https://github.com/JuanenRac/HYDRA-UMC-ANDROID-CONTROL)** — app di controllo nativa per Android con login biometrico e un companion Wear OS abbinato.
- **[HYDRA-UMC-IOS-CONTROL](https://github.com/JuanenRac/HYDRA-UMC-IOS-CONTROL)** — app di controllo per iOS/iPadOS (Flutter) con sincronizzazione WebSocket in tempo reale.
- **[HYDRA-UMC-DSI](https://github.com/JuanenRac/HYDRA-UMC-DSI)** — interfaccia touch nativa per il touchscreen DSI da 7" a bordo, incorporata direttamente nel CM5.
- **[HYDRA-UMC-BRIDGE-AMR](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-AMR)** — barriera di coordinamento per flotte AGV/AMR tramite un publisher MQTT VDA 5050 (testato solo contro una flotta emulata).
- **[HYDRA-UMC-BRIDGE-CNC](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-CNC)** — coordinatore ad alto livello per celle CNC con accesso a stato/byte di controllo GRBL (testato solo contro un emulatore).
- **[HYDRA-UMC-BRIDGE-DROIDS](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-DROIDS)** — barriera di coordinamento per droidi con zampe/umanoidi, con un mittente di comandi per Boston Dynamics Spot (testato solo contro un emulatore).
- **[HYDRA-UMC-BRIDGE-LASER](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-LASER)** — coordinatore per celle laser che legge 3 segnali GPIO di chiave/involucro/interblocco (testato solo contro un chip simulato; non può armare né far partire un laser).
- **[HYDRA-UMC-BRIDGE-OPENPNP](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-OPENPNP)** — coordinatore ad alto livello sicuro per il flusso schede del pick-and-place OpenPnP.
- **[HYDRA-UMC-BRIDGE-ROS2](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-ROS2)** — coordinatore con un trasporto ROS 2 rclpy importato in modo lazy (non ancora eseguito contro un'installazione ROS 2).
- **[HYDRA-UMC-BRIDGE-UAV](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-UAV)** — barriera di coordinamento per UAV dotati di fotocamera, con un mittente di comandi MAVLink (testato solo contro un emulatore).

**Direttamente Correlati**
- **[HYDRA-UMC-SDK](https://github.com/JuanenRac/HYDRA-UMC-SDK)** — il contratto JSON-Schema condiviso e la barriera software di controllo dei job contro cui ogni bridge valida i propri comandi (non è una funzione di sicurezza certificata).
- **[HYDRA-UMC-CONNECTOR-HUB](https://github.com/JuanenRac/HYDRA-UMC-CONNECTOR-HUB)** — registro dichiarativo e validatore di manifesti adattatore per connettori di macchine esterne; estende la propria idea di contratto dell'SDK alle macchine esterne senza sostituire i progetti di gateway industriale.
- **[HYDRA-UMC-MQTT-BROKER](https://github.com/JuanenRac/HYDRA-UMC-MQTT-BROKER)** — il vero trasporto di `mqtt_transport.py` per i propri topic `hydra/bridges/printer3d/...` di questo bridge — stato più i comandi reali Moonraker start/pause/resume/cancel, insieme alla barriera di lavoro condivisa; vedi il proprio `docs/BRIDGE_TOPICS.md` di quel repository.
- **[HYDRA-UMC-SAFETY-ZONES](https://github.com/JuanenRac/HYDRA-UMC-SAFETY-ZONES)** — futura evidenza di sicurezza dello spazio di lavoro per questo bridge.

**Fa Anche Parte dell'Ecosistema**

*Hardware e Piattaforma di Base*
- **[HYDRA-UMC](https://github.com/JuanenRac/HYDRA-UMC)** — il progetto della scheda madre del braccio robotico: host CM5 + coprocessore STM32H745 dual-core, pensato per coordinare fino a 8 bracci utensile via CAN-OTA/SPI-OTA (firmware in fase iniziale; nessuna scheda assemblata per ora).
- **[HYDRA-UMC-OS](https://github.com/JuanenRac/HYDRA-UMC-OS)** — livello prodotto riproducibile su Raspberry Pi OS per il CM5: agente in sola lettura, config/profili validati, provisioning WiFi al primo contatto.

*Backend Centrale e Client*
- **[HYDRA-UMC-EDITOR-URDF](https://github.com/JuanenRac/HYDRA-UMC-EDITOR-URDF)** — creatore/editor grafico desktop di URDF che invia i modelli finiti al catalogo di STUDIO.
- **[HYDRA-UMC-EDITOR-STL](https://github.com/JuanenRac/HYDRA-UMC-EDITOR-STL)** — editor desktop di modelli STL, che trasforma/sostituisce/rimuove/aggiunge veri pezzi nello stesso catalogo di modelli modificato anche da HYDRA-UMC-EDITOR-URDF.

*Piattaforma Strumenti URTC*
- **[URTC](https://github.com/JuanenRac/URTC)** — firmware per la scheda fisica dell'Universal Robot Tool Controller, oltre 25 profili utensile su bus CAN.
- **[URTC-FLASHER](https://github.com/JuanenRac/URTC-FLASHER)** — strumento desktop con GUI per il flashing delle schede URTC, CAN-OTA più SWD/JTAG a chip intero.
- **[URTC-TESTER](https://github.com/JuanenRac/URTC-TESTER)** — strumento desktop di diagnostica CAN-bus dal vivo per schede URTC, un pannello per profilo utensile.
- **[URTC-WEB-STUDIO](https://github.com/JuanenRac/URTC-WEB-STUDIO)** — alternativa basata su browser a URTC-TESTER tramite la Web Serial API, senza installazione locale.
- **[URTC-GATEWAY](https://github.com/JuanenRac/URTC-GATEWAY)** — gateway davanti al bus CAN di URTC: elenco di identificatori consentiti, limite di frequenza e chiave di sessione; software provato su computer, non ancora su un bus reale.

*Nodo IA Visione (Hailo-8)*
- **[HYDRA-UMC-VISION-NODE](https://github.com/JuanenRac/HYDRA-UMC-VISION-NODE)** — hub di integrazione per la pipeline di visione Hailo-8, con un vero controllo di prontezza hardware per fase.
- **[HYDRA-UMC-DETECTION-HEF](https://github.com/JuanenRac/HYDRA-UMC-DETECTION-HEF)** — registro reale di modelli compilati con verifica di caricamento sicuro per architettura Hailo/checksum.
- **[HYDRA-UMC-VISION-STREAMER](https://github.com/JuanenRac/HYDRA-UMC-VISION-STREAMER)** — generatore reale di pipeline GStreamer + config MediaMTX, con una vera barriera di integrazione HailoRT.
- **[HYDRA-UMC-VISUAL-SERVOING-API](https://github.com/JuanenRac/HYDRA-UMC-VISUAL-SERVOING-API)** — legge di correzione Position-Based Visual Servoing con autorizzazione condizionata allo stato di zona; ancora nessuna stima di posa da telecamera.

*Nodo IA Cognitivo (Hailo-10)*
- **[HYDRA-UMC-COGNITIVE-NODE](https://github.com/JuanenRac/HYDRA-UMC-COGNITIVE-NODE)** — hub di integrazione per la pipeline cognitiva Hailo-10 (orchestrazione LLM/VLA/voce).
- **[HYDRA-UMC-VLA-ENGINE](https://github.com/JuanenRac/HYDRA-UMC-VLA-ENGINE)** — vera codifica/decodifica di token d'azione e generazione di traiettoria per un modello Vision-Language-Action.
- **[HYDRA-UMC-VOICE-UI](https://github.com/JuanenRac/HYDRA-UMC-VOICE-UI)** — vero front-end vocale (VAD + parser di intenti) con un relay verso Watch limitato e soggetto a conferma.
- **[HYDRA-UMC-SEMANTIC-PLANNER](https://github.com/JuanenRac/HYDRA-UMC-SEMANTIC-PLANNER)** — vera scomposizione dei task basata su regole e recupero semantico degli errori sui codici errore MCU.
- **[HYDRA-UMC-DOCS-QA](https://github.com/JuanenRac/HYDRA-UMC-DOCS-QA)** — vera ricerca documentale TF-IDF (solo libreria standard) sui documenti Markdown di questo ecosistema.
- **[HYDRA-UMC-LOCAL-TECHNICIAN](https://github.com/JuanenRac/HYDRA-UMC-LOCAL-TECHNICIAN)** — tecnico di manutenzione IA locale e con cancelli di policy per l'ecosistema stesso - osserva, diagnostica e propone correzioni; i due livelli di rischio più alti non sono deliberatamente ancora implementati.

*Orchestrazione e Sciame*
- **[HYDRA-UMC-ORCHESTRATOR](https://github.com/JuanenRac/HYDRA-UMC-ORCHESTRATOR)** — hub di integrazione con un vero contratto di health-report gRPC/Protobuf e una macchina a stati di missione.
- **[HYDRA-UMC-JOB-DISPATCHER](https://github.com/JuanenRac/HYDRA-UMC-JOB-DISPATCHER)** — vera coda di lavori basata su priorità con deduplicazione, su una vera API HTTP.
- **[HYDRA-UMC-NODE-HEALING](https://github.com/JuanenRac/HYDRA-UMC-NODE-HEALING)** — vero watchdog di salute della flotta basato su gRPC, con retry/backoff e rilevamento di discrepanza d'identità.
- **[HYDRA-UMC-PATH-PLANNER-3D](https://github.com/JuanenRac/HYDRA-UMC-PATH-PLANNER-3D)** — vero pianificatore di percorsi 3D basato su RRT, con vera validazione delle collisioni ostacolo/spazio di lavoro.
- **[HYDRA-UMC-SWARM-SYNC](https://github.com/JuanenRac/HYDRA-UMC-SWARM-SYNC)** — vera sincronizzazione di stato CRDT LWW-Element-Map, con property test per la convergenza multi-cella.

*Gemello Digitale e Simulazione*
- **[HYDRA-UMC-TWIN](https://github.com/JuanenRac/HYDRA-UMC-TWIN)** — hub di integrazione per il motore di gemello digitale, con un vero contratto di sincronizzazione per compatibilità di versione.
- **[HYDRA-UMC-HIL-BRIDGE](https://github.com/JuanenRac/HYDRA-UMC-HIL-BRIDGE)** — router hardware-in-the-loop con un interblocco software di collisione tra simulazione e hardware reale (testato senza hardware reale).
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
- **[HYDRA-UMC-WATCH](https://github.com/JuanenRac/HYDRA-UMC-WATCH)** — app companion WearOS con schemi di avviso aptico e un relay vocale verso il telefono abbinato (non ancora eseguita su un orologio fisico).
- **[URTC-SMART-RACK](https://github.com/JuanenRac/URTC-SMART-RACK)** — firmware per un rack di montaggio schede con decodifica reale dell'ID utensile e logica di preriscaldamento Smart Idle.
- **[URTC-VISION-TOOL](https://github.com/JuanenRac/URTC-VISION-TOOL)** — firmware più un vero companion di visione Python per una testa utensile di ispezione termica/RGB.
- **[HYDRA-UMC-UPDATER](https://github.com/JuanenRac/HYDRA-UMC-UPDATER)** — strumento amministrativo desktop che scopre, clona e aggiorna ogni repository di questo ecosistema.
- **[HYDRA-UMC-OS-REBUILDER](https://github.com/JuanenRac/HYDRA-UMC-OS-REBUILDER)** — strumento desktop Windows/Linux che costruisce un'immagine della CM5 pronta da scrivere, precaricata con le versioni più aggiornate dell'ecosistema, con configurazione di primo avvio Wi-Fi/utente/SSH in stile Raspberry Pi Imager.
- **[HYDRA-UMC-OPS-AGENT](https://github.com/JuanenRac/HYDRA-UMC-OPS-AGENT)** — coordinatore di incidenti di manutenzione: un ruolo edge a basso privilegio raccoglie uno snapshot di inventario/salute sanificato, un ruolo control-plane lo rende in sola lettura e chiede a un provider di IA di suggerire una diagnosi - non applica mai una patch né distribuisce nulla.
- **[HYDRA-UMC-DEV-SERVER](https://github.com/JuanenRac/HYDRA-UMC-DEV-SERVER)** — host di sviluppo riproducibile (Raspberry Pi 5 / CM5) che conserva il codice sorgente dell'ecosistema ed esegue attività delimitate di build/test tramite una coda durevole; un ruolo di sviluppo dedicato, esplicitamente distinto da un CM5 operativo.

## 📚 Documentazione

Dove leggere di più:

* [docs/BRIDGE_GUIDE.md](docs/BRIDGE_GUIDE.md) - ambito, Moonraker, script, la porta di accettazione hardware
* [docs/SLICER_ARTIFACT_COMPATIBILITY.md](docs/SLICER_ARTIFACT_COMPATIBILITY.md) - quali file dello slicer sono riconosciuti e come
* [docs/PRINT_PROFILE_BOUNDARY.md](docs/PRINT_PROFILE_BOUNDARY.md) - la convalida necessaria prima di qualsiasi operazione con il controller nativo
* [Base di sicurezza dell'ecosistema](https://github.com/JuanenRac/HYDRA-UMC-DOCS/blob/main/docs/SECURITY_BASELINE.md)
* [Modello delle minacce dell'ecosistema](https://github.com/JuanenRac/HYDRA-UMC-DOCS/blob/main/docs/THREAT_MODEL.md)
* [Registro delle modifiche di questo repository](CHANGELOG.md)
* [Licenza di questo repository](LICENSE.md)

## 🤝 Contribuire e comunità

* Prima di una pull request esegui `HYDRA_UMC_CI=1 py -3 tools/ci_validate.py` (oppure `HYDRA_UMC_CI=1 python3 tools/ci_validate.py`): deve stampare `CI_VALIDATION=PASS`. Non eseguire `build.sh` né `build.bat` per questa verifica; compilare non è verificare.
* I otto README sono scritti da un'unica fonte in HYDRA-UMC-DOCS; non modificarli a mano. Cambia la fonte e riscrivili con `tools/make_readmes.py`.
* Non affermare in un README ciò che non è stato eseguito: scrivi «simulato» o «non provato su hardware» quando è la verità.
* Vedi [CONTRIBUTING.md](CONTRIBUTING.md), il [codice di condotta](CODE_OF_CONDUCT.md), [SECURITY.md](SECURITY.md) e [SUPPORT.md](SUPPORT.md).

## 👤 AUTORE

**JuanenRac (Electro Hobby 3D)** · electrohobby3d@gmail.com

## 📜 LICENZA

GPL-3.0-or-later - [LICENSE](LICENSE).
