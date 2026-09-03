<!-- =============================================================================
HYDRA-UMC-BRIDGE-PRINTER3D - 3Dプリンターソフトウェアブリッジ
Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
GPL-3.0-or-later - see LICENSE
============================================================================= -->

<p align="center">
  <img src="images/HYDRA_UMC_BANNER.svg" alt="HYDRA-UMC-BRIDGE-PRINTER3D バナー" width="100%">
</p>

# 🖨️ HYDRA-UMC-BRIDGE-PRINTER3D

<p align="center"><a href="README.md">🇺🇸 English</a> | <a href="README_spa.md">🇪🇸 Español</a> | <a href="README_fra.md">🇫🇷 Français</a> | <a href="README_ita.md">🇮🇹 Italiano</a> | <a href="README_deu.md">🇩🇪 Deutsch</a> | <a href="README_zho.md">🇨🇳 简体中文</a> | 🇯🇵 <b>日本語</b></p>

### 🌡️ オープンな3Dプリントソフトウェア向けフェイルセーフ連携ブリッジ

<p align="left">
  <img src="https://img.shields.io/badge/ライセンス-GPL%203.0-blue.svg" alt="GPL 3.0">
  <img src="https://img.shields.io/badge/Python-3.11%2B-3776AB.svg" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/Safety-Fails%20Closed-red.svg" alt="フェイルセーフ">
</p>

---

## 1. 🛠️ 技術概要

**HYDRA-UMC-BRIDGE-PRINTER3D** は、オープンな3Dプリントソフトウェア(Moonraker/Klipper)とHYDRA-UMCロボット補助装置とを結ぶ高レベルコーディネーターである。ローカルのスライサー成果物も読み取り専用で認識する。プリンターのネイティブファームウェアは常に動作、ヒーター、熱保護、機械インターロックに責任を持つ —— このブリッジはレディネスを読み取り、成果物の証拠を記録し、その周辺で補助装置を連携させるだけである。

本リポジトリは **External Automation Bridges** ファミリーに属する。CNC・LASER・OPENPNP・PRINTER3D・ROS2という兄弟リポジトリ群が、すべて `HYDRA-UMC-SDK` の同じ安全契約を共有しており、いずれのブリッジも独自の「作業に安全」という定義を勝手に作ることはできない。

### 主な機能:
* ✅ **実在するMoonrakerレディネスプローブ:** `moonraker.py` の `MoonrakerProbe` は、標準ライブラリのみに基づく小さなクライアント(`urlopen` + `json`)でMoonraker公式ドキュメントの `/printer/info` エンドポイントを利用する —— Python標準ライブラリ以外に追加の依存はない。*(実装済み、`tests/test_moonraker.py` でテスト済み)*
* ✅ **実在するフェイルクローズドな状態解析:** `parse_info()` は文字列 `"ready"` のみを `MachineState.IDLE` にマッピングする。`startup`/`shutdown`/`error` は `FAULT` に、それ以外(不正な形式のレスポンスを含む)はすべて `OFFLINE` にマッピングされる —— プリンター周辺でロボットの計画を許可してしまうような状態には決してマッピングされない。*(実装済み)*
* ✅ **実在する共有安全ゲート:** 観測されたすべてのジョブは `HYDRA-UMC-SDK` の `bridge_contract` にある `evaluate_job()` を通じて再評価される。これは他のすべての兄弟ブリッジとHYDRA-UMC-SERVERが使うのと同じゲートである。*(実装済み)*
* ✅ **スライサー非依存の成果物検査:** `artifacts.py` はOrcaSlicer、Ultimaker Cura、PrusaSlicer、Bambu Studioなどが生成する通常のFDM G-codeをローカル証拠だけで識別する。また、3MFパッケージとLychee互換のレジンスライスも、展開、コマンド解析、アップロード、印刷をせずに認識する。*(実装済み、`tests/test_artifacts.py` でテスト済み)*
* ✅ **プロファイル証跡の境界:** `profiles.py` は検査済みのアーティファクトを宣言済みの FDM または樹脂プロファイルと照合できるが、一致した場合でも `execution_authorized=False` を返す。*(実装済み、`tests/test_profiles.py` でテスト済み)*
* ✅ **実際の、SDK によってゲートされたジョブコマンド:** `MoonrakerJobControl` は Moonraker の文書化された `/printer/print/start|pause|resume|cancel` エンドポイントに実際の `POST` リクエストを送信する —— `start_job()` は、このエコシステムのすべての生産的ディスパッチが使う同じ `evaluate_job()` の判定によってゲートされる。`pause_job()`/`cancel_job()` は常に許可される（`ABORT` と同じデエスカレーションの理由による）。`resume_job()` はプリンターが本当に `HOLDING` 状態であることを要求する。すでにアップロード済み・スライス済みのファイルを名前で開始するだけであり、生の G-code をストリーミングすることは決してない。*(実装済み、`tests/test_moonraker.py` でテスト済み)*
* ✅ **非破壊的なビルド/テスト:** `build-test.bat`/`.sh` は、G-codeを送信せず、バージョンを変更せず、プリンターに一切触れずに、レスポンスパーサーと安全ゲートをコンパイルする。*(実装済み、下記「ビルドと実行」を参照)*
* 🔜 **生の G-code ストリーミング:** 意図的に依然として保留されている——任意の低レベルコマンド（名前付きの、すでにスライス済みのジョブではない）を送信するには、テスト済みのプロファイル、認証、そしてこのブリッジがまだ持っていない物理的安全レビューが必要である。*(計画中)*

---

## 2. 🔄 プリンター連携フロー

```mermaid
flowchart LR
    PRINTER["Moonraker / Klipper<br/>(/printer/info)"] --> BRIDGE["BRIDGE-PRINTER3D<br/>MoonrakerProbe.parse_info()"]
    BRIDGE -- "BridgeJob + 観測された MachineState" --> SDK["HYDRA-UMC-SDK<br/>evaluate_job()"]
    SDK -- GateDecision --> SERVER["HYDRA-UMC-SERVER"]
    SERVER -- "ジョブ / 中止" --> CELL["セル安全"]
```

---

## 3. 🧱 アーキテクチャと設計判断

* **なぜMoonrakerの文字列 `"ready"` のみがアイドルにマッピングされるのか。** `parse_info()` の状態マッピングは意図的に狭く設計されている。`ready` → `IDLE`、`startup`/`shutdown`/`error` → `FAULT`(フェイルクローズド)、それ以外または欠落した値 → `OFFLINE`。認識されないプリンター状態に対して「デフォルトで安全」という前提は一切存在しない。
* **なぜパース処理はネットワーク取得とは別の `@staticmethod` になっているのか。** `MoonrakerProbe.parse_info()` は単純な `dict` を受け取り、ネットワーク呼び出しや稼働中のプリンターなしに完全にユニットテスト可能である。`fetch()` はそれを呼び出す薄い、必然的にネットワークを伴う部分である。安全に関わるロジックは、テストに実物のプリンターを一切必要としない部分に存在する。
* **なぜプローブはMoonrakerクライアントライブラリではなく標準ライブラリの `urlopen`/`json` を使うのか。** 依存範囲をPython標準ライブラリに限定することで、安全に関わる解析処理を最小限かつ監査可能に保ち、リトライやタイムアウト、エラー処理に関するサードパーティクライアント独自の前提を排除できる。
* **なぜブリッジは新しい `BridgeJob` を組み立て、独自の受理/拒否ロジックを書く代わりに共有の `evaluate_job()` に委譲するのか。** 5つのExternal Automation Bridges(CNC、LASER、OPENPNP、PRINTER3D、ROS2)はすべて `HYDRA-UMC-SDK` の全く同じ `bridge_contract` を再利用しており、「何をもってジョブ開始が安全とみなすか」がそれぞれの間で静かに食い違うことがない。
* **なぜジョブコマンド(start/pause/resume/cancel)は実物であり、生のG-codeストリーミングはまだそうではないのか。** Moonrakerの `/printer/print/*` エンドポイントは、すでにアップロード済みでスライス済みのファイルを名前で参照するだけである - Moonraker/Klipper自身がそのファイルに対してすでに適用している同じ安全の枠組みである。任意の生のG-codeは根本的に異なる、はるかに大きな信頼サーフェスであり(何でも含みうる)、テスト済みプロファイル、認証、物理的安全レビューがまだ必要であり、このブリッジにはまだそれがない。
* **なぜ `resume_job()` は汎用の `evaluate_job()` ゲートを再利用しないのか。** そのゲートは「生産的な作業にはIDLE状態のマシンが必要」という考え方で構築されている - これは一時停止したジョブの再開とは逆であり、`HOLDING` からのみ意味をなす。DROIDSの `stand_request()`/`sit_request()` ですでに使われているのと同じ、独立したゲートの理屈である。
* **エコシステムの他部分とどう関係するか。** BRIDGE-PRINTER3DはMoonraker/Klipperと `HYDRA-UMC-SDK` → `HYDRA-UMC-SERVER` → セル安全との間に位置する。プリンターの周辺で補助ロボット作業を連携させるものであり、ネイティブファームウェア、ヒーター、熱保護を置き換えることは決してない。

## 🧾 スライサー成果物の互換性

読み取り専用の成果物レーンは、OrcaSlicer、Ultimaker Cura、PrusaSlicer、Bambu Studioなどが生成する通常のFDM G-code(`.gcode`、`.gco`、`.gc`)をサポートする。既知のコメントは出所のヒントとなり、マーカーがない場合は `unknown-slicer` のままとなる。`.gcode.3mf` と汎用 `.3mf` は識別するが、展開は一切しない。Lychee互換ワークフローのレジンスライス(`.ctb`、`.goo`、`.photon`、`.pwmo`、`.pws`、`.sl1`)は意図的に不透明として扱い、特定のプリンターやスライサーに帰属させない。

これは**出力成果物**との互換性であり、これらのアプリケーションのリモート制御ではない。ブリッジはスライサーを起動せず、プロファイルを変更せず、G-codeを解析/実行せず、ファイルをアップロードせず、クラウドサービスに接続せず、印刷を開始しない。正確なマトリックスと将来の制御要件は[スライサー成果物の互換性](docs/SLICER_ARTIFACT_COMPATIBILITY.md)を参照。

---

## 📂 ディレクトリ構成

```text
HYDRA-UMC-BRIDGE-PRINTER3D/
├── src/
│   └── hydra_umc_bridge_printer3d/
│       ├── __init__.py
│       ├── artifacts.py         # 読み取り専用G-code・3MF・レジンスライス証拠
│       ├── profiles.py          # プロファイル互換性の証拠。印刷許可では決してない
│       ├── moonraker.py         # MoonrakerProbe + PrinterBridge 安全ゲート
│       └── mqtt_transport.py    # このbridgeの既存の実Moonrakerロジック向けの実MQTTブローカー転送
├── tests/
│   ├── test_artifacts.py         # スライサー証拠テスト(プリンターI/Oなし)
│   ├── test_profiles.py         # プロファイル照合は常に実行を拒否する
│   ├── test_moonraker.py        # レディネス解析とフェイルセーフゲートのテスト
│   └── test_mqtt_transport.py   # 疑似ブローカークライアントに対するMQTTコマンド/ステータス形状テスト
├── tools/
│   ├── build_test.py            # 非破壊的なコンパイル+テストランナー (build-test.bat/.sh)
│   ├── inspect_print_artifact.py # ローカル成果物証拠JSON CLI
│   ├── assess_print_profile.py  # オフラインのプロファイル・成果物照合CLI。実行を許可することはない
│   ├── ci_validate.py           # 依存関係なし・非破壊のCIベースライン (.github/workflows/ci.yml が使用)
│   └── bump_version.py          # pyproject.toml、マニフェスト、CHANGELOG.md を同期
├── docs/
│   ├── BRIDGE_GUIDE.md                        # 適用範囲、対応プラットフォーム、スクリプト、ハードウェア受け入れゲート
│   ├── PRINT_PROFILE_BOUNDARY.md              # プロファイル互換性の証拠が印刷許可に対して意味すること
│   └── SLICER_ARTIFACT_COMPATIBILITY.md       # このbridgeが証拠として読み取れるスライサー成果物形式
├── images/
│   └── HYDRA_UMC_BANNER.svg     # README バナー
├── build-test.bat / build-test.sh  # 検証のみ、リポジトリを一切変更しない
├── build.bat / build.sh            # 検証後、成功時のみバージョン + CHANGELOG を更新
├── pyproject.toml               # パッケージメタデータ。HYDRA-UMC-SDK に依存 (git)
├── hydra-umc.project.json       # エコシステムマニフェスト(バージョン、成熟度、ファミリー)
├── CHANGELOG.md
├── CODE_OF_CONDUCT.md / CONTRIBUTING.md / SECURITY.md / SUPPORT.md
├── LICENSE / LICENSE.md
└── README.md / README_*.md      # 本ファイルおよびその6言語訳
```

---

## 4. ⚙️ ビルドと実行

Python 3.11以上が必要。`tools/build_test.py` は `HYDRA-UMC-SDK` が兄弟ディレクトリ(`../HYDRA-UMC-SDK`)としてチェックアウトされているか、環境変数 `HYDRA_UMC_SDK_ROOT` で指定されていることを期待する。

```bash
# Windows
build-test.bat      # 検証のみ —— バージョン/CHANGELOGの変更なし
build.bat            # 検証後、成功時にバージョン + CHANGELOG を更新

# Linux/macOS
bash build-test.sh
bash build.sh
```

`build-test` は `src/` と `tools/` 配下の各モジュールを `py_compile` でコンパイルし、`unittest` の全スイート(`tests/test_moonraker.py` と `tests/test_artifacts.py`)を実行して、レディネスレスポンスの解析、成果物検査、フェイルセーフゲートを実証する —— G-codeを一切送信せず、プリンターに触れず、リポジトリを一切変更しない。`build` はまず同じ検証を実行し、成功した場合のみ `tools/bump_version.py` を呼び出して `pyproject.toml`、`hydra-umc.project.json`、`CHANGELOG.md` の間でバージョンを同期する。実際のプリンター向け `run` コマンドはまだ存在しない —— それには事前にテスト済みプロファイル、認証、物理的安全レビューが必要である。

プリンターに接続せずローカルのスライサー出力を検査するには:

```bash
py tools/inspect_print_artifact.py パス/ジョブ.gcode
```

---

## ✅ 現状と次のステップ

**現時点で実在するもの:** バージョン `0.1.0`。ローカルでテスト済みのMoonrakerレディネスアダプター(`MoonrakerProbe` + `PrinterBridge`)が `HYDRA-UMC-SDK` の共有ジョブゲートの上に構築されており、実際の、SDK によってゲートされたジョブコマンド(`MoonrakerJobControl`:Moonraker 自身の REST API を通じて既にアップロード済みのファイルを開始/一時停止/再開/キャンセル)、主要スライサー系の読み取り専用G-code/3MF/レジンスライス成果物証拠とプロファイル互換性、ローカルHTTP `/printer/info` 契約検証、実際の別個の `/printer/objects/query?print_stats=state` 契約、実際の `POST` ジョブコマンド検証を含む決定論的な49件の `unittest` スイートと、SDKチェックアウトを伴いCIに組み込まれた非破壊的なbuild-testスクリプトを備える。

**統合境界:** プリンターのネイティブファームウェア(Moonrakerを介したKlipper)は常に動作、ヒーター、熱保護、機械インターロックを保持する。このブリッジはレディネスを読み取るだけであり、その周辺の*補助的な*ロボット作業をゲート制御するのみである。

**今後の課題:** 本ブリッジはまだ実際のプリンター、ホットエンド、ロボットを制御したことがない —— 実際のコマンドを送信するには、事前にテスト済みのプリンタープロファイル、認証、物理的安全レビューが必要である。

---

## 🔗 関連プロジェクト

本プロジェクトは、同じ作者(JuanenRac / Electro Hobby 3D)による HYDRA-UMC ロボティクスエコシステムの一部です。リクエストが実はこの中のどれかについてのものである可能性があるため、知っておく価値があります。

**親プロジェクト**
- **[HYDRA-UMC-SERVER](https://github.com/JuanenRac/HYDRA-UMC-SERVER)** — すべての制御クライアントが実際に通信する、本物のヘッドレスバックエンド(REST/WebSocket)。各コマンドがこのブリッジ自身のローカル安全ゲートを通過した後、本ブリッジが報告する認証済みエコシステム境界。

**兄弟プロジェクト** —— それぞれ独自のクライアントとして、同じく HYDRA-UMC-SERVER 自身の API と通信する
- **[HYDRA-UMC-STUDIO](https://github.com/JuanenRac/HYDRA-UMC-STUDIO)** — リアルタイムのマルチロボット 3D 可視化を備えたウェブ制御ダッシュボード。
- **[HYDRA-UMC-SUITE](https://github.com/JuanenRac/HYDRA-UMC-SUITE)** — 複数のサーバーを同時に扱えるデスクトップ(PySide6)スウォームコマンドセンター、スタンドアロン実行ファイルとしてパッケージ化。
- **[HYDRA-UMC-ANDROID-CONTROL](https://github.com/JuanenRac/HYDRA-UMC-ANDROID-CONTROL)** — 生体認証ログインとペアリングされた Wear OS コンパニオンを備えたネイティブ Android 制御アプリ。
- **[HYDRA-UMC-IOS-CONTROL](https://github.com/JuanenRac/HYDRA-UMC-IOS-CONTROL)** — リアルタイム WebSocket 同期を備えた iOS/iPadOS 制御アプリ(Flutter)。
- **[HYDRA-UMC-DSI](https://github.com/JuanenRac/HYDRA-UMC-DSI)** — 本体搭載の 7 インチ DSI タッチスクリーン向けネイティブタッチ UI、CM5 自体に組み込み。
- **[HYDRA-UMC-BRIDGE-AMR](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-AMR)** — 実際の VDA 5050 MQTT パブリッシャーによる AGV/AMR フリートの調整境界。
- **[HYDRA-UMC-BRIDGE-CNC](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-CNC)** — 実際の GRBL ステータス/制御バイトへのアクセスを持つ、CNC セルの高レベルコーディネーター。
- **[HYDRA-UMC-BRIDGE-DROIDS](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-DROIDS)** — 実際の Boston Dynamics Spot コマンド送信機能を持つ、脚型/ヒューマノイドドロイドの調整境界。
- **[HYDRA-UMC-BRIDGE-LASER](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-LASER)** — 実際のキー/筐体/インターロック GPIO セーフガード 3 系統を読み取る、レーザーセルの安全コーディネーター。
- **[HYDRA-UMC-BRIDGE-OPENPNP](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-OPENPNP)** — OpenPnP ピックアンドプレースの基板フローを安全に統括する高レベルコーディネーター。
- **[HYDRA-UMC-BRIDGE-ROS2](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-ROS2)** — 実際の遅延インポート rclpy ROS 2 トランスポートを持つ安全コーディネーター。
- **[HYDRA-UMC-BRIDGE-UAV](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-UAV)** — 実際の MAVLink コマンド送信機能を持つ、カメラ搭載 UAV の調整境界。

**直接関連**
- **[HYDRA-UMC-SDK](https://github.com/JuanenRac/HYDRA-UMC-SDK)** — すべてのブリッジが自身のコマンドを検証する共有 JSON-Schema 契約と安全ゲートの境界。
- **[HYDRA-UMC-MQTT-BROKER](https://github.com/JuanenRac/HYDRA-UMC-MQTT-BROKER)** — このブリッジ自身の `hydra/bridges/printer3d/...` トピック向けの `mqtt_transport.py` の実際のトランスポート——ステータスに加え実際の Moonraker start/pause/resume/cancel コマンド、および共有ジョブゲート。詳細はそのリポジトリ自身の `docs/BRIDGE_TOPICS.md` を参照。
- **[HYDRA-UMC-SAFETY-ZONES](https://github.com/JuanenRac/HYDRA-UMC-SAFETY-ZONES)** — 本ブリッジ向けの将来のワークスペース安全実証。

**エコシステムの他のプロジェクト**

*コアハードウェア&プラットフォーム*
- **[HYDRA-UMC](https://github.com/JuanenRac/HYDRA-UMC)** — 実際のロボットアームのマザーボード——CM5 ホスト + デュアルコア STM32H745、CAN-OTA/SPI-OTA 経由で最大 8 本のツールアームを統括。
- **[HYDRA-UMC-OS](https://github.com/JuanenRac/HYDRA-UMC-OS)** — CM5 向けの再現可能な Raspberry Pi OS プロダクト層——読み取り専用エージェント、検証済み設定/プロファイル、WiFi 初回接続プロビジョニング。

*コアバックエンド&クライアント*
- **[HYDRA-UMC-EDITOR-URDF](https://github.com/JuanenRac/HYDRA-UMC-EDITOR-URDF)** — 完成したモデルを STUDIO 自身のカタログへ送信するデスクトップ用グラフィカル URDF 作成/編集ツール。

*URTC ツールプラットフォーム*
- **[URTC](https://github.com/JuanenRac/URTC)** — 物理的な Universal Robot Tool Controller 基板向けファームウェア、CAN バス経由の 25 以上のツールプロファイル。
- **[URTC-FLASHER](https://github.com/JuanenRac/URTC-FLASHER)** — URTC 基板用のデスクトップ GUI 書き込みツール、CAN-OTA およびフルチップ SWD/JTAG。
- **[URTC-TESTER](https://github.com/JuanenRac/URTC-TESTER)** — URTC 基板向けのデスクトップ CAN バスライブ診断ツール、ツールプロファイルごとに 1 パネル。
- **[URTC-WEB-STUDIO](https://github.com/JuanenRac/URTC-WEB-STUDIO)** — Web Serial API を使ったブラウザベースの URTC-TESTER の代替、ローカルインストール不要。

*ビジョン AI ノード(Hailo-8)*
- **[HYDRA-UMC-VISION-NODE](https://github.com/JuanenRac/HYDRA-UMC-VISION-NODE)** — Hailo-8 ビジョンパイプラインの統合ハブ、段階ごとの実際のハードウェア準備状況チェック付き。
- **[HYDRA-UMC-DETECTION-HEF](https://github.com/JuanenRac/HYDRA-UMC-DETECTION-HEF)** — Hailo アーキテクチャ/チェックサムによる安全読み込み検証を備えた、実際のコンパイル済みモデルレジストリ。
- **[HYDRA-UMC-VISION-STREAMER](https://github.com/JuanenRac/HYDRA-UMC-VISION-STREAMER)** — 実際の HailoRT 統合境界を持つ、実際の GStreamer パイプライン + MediaMTX 設定生成器。
- **[HYDRA-UMC-VISUAL-SERVOING-API](https://github.com/JuanenRac/HYDRA-UMC-VISUAL-SERVOING-API)** — 上流のゾーン状態に応じて安全ゲート制御される、実際の Position-Based Visual Servoing 補正則。

*コグニティブ AI ノード(Hailo-10)*
- **[HYDRA-UMC-COGNITIVE-NODE](https://github.com/JuanenRac/HYDRA-UMC-COGNITIVE-NODE)** — Hailo-10 コグニティブパイプライン(LLM/VLA/音声オーケストレーション)の統合ハブ。
- **[HYDRA-UMC-VLA-ENGINE](https://github.com/JuanenRac/HYDRA-UMC-VLA-ENGINE)** — Vision-Language-Action モデル向けの、実際のアクショントークンのエンコード/デコードと軌道生成。
- **[HYDRA-UMC-VOICE-UI](https://github.com/JuanenRac/HYDRA-UMC-VOICE-UI)** — 確認ゲート付きの限定的な Watch リレーを備えた、実際の音声フロントエンド(VAD + 意図解析)。
- **[HYDRA-UMC-SEMANTIC-PLANNER](https://github.com/JuanenRac/HYDRA-UMC-SEMANTIC-PLANNER)** — MCU エラーコードに対する、実際のルールベースのタスク分解と意味的エラー復旧。
- **[HYDRA-UMC-DOCS-QA](https://github.com/JuanenRac/HYDRA-UMC-DOCS-QA)** — このエコシステム自身の Markdown ドキュメントに対する、標準ライブラリのみの実際の TF-IDF 文書検索。

*オーケストレーション&スウォーム*
- **[HYDRA-UMC-ORCHESTRATOR](https://github.com/JuanenRac/HYDRA-UMC-ORCHESTRATOR)** — 実際の gRPC/Protobuf ヘルスレポート契約とミッションステートマシンを持つ統合ハブ。
- **[HYDRA-UMC-JOB-DISPATCHER](https://github.com/JuanenRac/HYDRA-UMC-JOB-DISPATCHER)** — 実際の HTTP API 上に構築された、優先度ベースの実際のジョブキュー(重複排除付き)。
- **[HYDRA-UMC-NODE-HEALING](https://github.com/JuanenRac/HYDRA-UMC-NODE-HEALING)** — リトライ/バックオフとアイデンティティ不一致検出を備えた、実際の gRPC ベースのフリートヘルスウォッチドッグ。
- **[HYDRA-UMC-PATH-PLANNER-3D](https://github.com/JuanenRac/HYDRA-UMC-PATH-PLANNER-3D)** — 実際の障害物/ワークスペース衝突検証を備えた、実際の RRT ベースの 3D 経路プランナー。
- **[HYDRA-UMC-SWARM-SYNC](https://github.com/JuanenRac/HYDRA-UMC-SWARM-SYNC)** — 複数セルの収束についてプロパティテストされた、実際の CRDT LWW-Element-Map 状態同期。

*デジタルツイン&シミュレーション*
- **[HYDRA-UMC-TWIN](https://github.com/JuanenRac/HYDRA-UMC-TWIN)** — 実際のバージョン互換性同期契約を持つ、デジタルツインエンジンの統合ハブ。
- **[HYDRA-UMC-HIL-BRIDGE](https://github.com/JuanenRac/HYDRA-UMC-HIL-BRIDGE)** — シミュレーションと実際のハードウェアの間でコマンドをルーティングする、実際のハードウェア・イン・ザ・ループ安全インターロック。
- **[HYDRA-UMC-PHYSICS-REPLICA](https://github.com/JuanenRac/HYDRA-UMC-PHYSICS-REPLICA)** — 実際の URDF サブセットに対する、実際の順運動学と関節限界検証。
- **[HYDRA-UMC-SYNTHETIC-DATA-GEN](https://github.com/JuanenRac/HYDRA-UMC-SYNTHETIC-DATA-GEN)** — YOLO/COCO アノテーションのエクスポート機能を持つ、実際のプロシージャル 2D シーンジェネレーター。

*データ&分析*
- **[HYDRA-UMC-DATALAKE](https://github.com/JuanenRac/HYDRA-UMC-DATALAKE)** — 実際の取り込み/クエリ HTTP API を備えた、実際の sqlite3 ベースの時系列ストア。
- **[HYDRA-UMC-ANOMALY-DETECTOR](https://github.com/JuanenRac/HYDRA-UMC-ANOMALY-DETECTOR)** — ドリフト監視を備えた、実際の FFT + 統計ベースラインによる異常検知器。
- **[HYDRA-UMC-PRODUCTION-REPORTS](https://github.com/JuanenRac/HYDRA-UMC-PRODUCTION-REPORTS)** — DATALAKE の履歴に対する実際の OEE/稼働率計算、再現可能な CSV エクスポート付き。
- **[HYDRA-UMC-TELEMETRY-COLLECTOR](https://github.com/JuanenRac/HYDRA-UMC-TELEMETRY-COLLECTOR)** — シーケンス重複排除機能を備えた、DATALAKE への実際の CAN/WebSocket 取り込みパイプライン。

*産業用ゲートウェイ*
- **[HYDRA-UMC-GATEWAY-INDUSTRIAL](https://github.com/JuanenRac/HYDRA-UMC-GATEWAY-INDUSTRIAL)** — 実際のコマンド許可リスト/バックプレッシャー層を持つ、産業用プロトコルへ中継する統合ハブ。
- **[HYDRA-UMC-OPCUA-SERVER](https://github.com/JuanenRac/HYDRA-UMC-OPCUA-SERVER)** — 実際のバイナリプロトコルクライアントセッションで検証された、実際の OPC-UA アドレス空間。
- **[HYDRA-UMC-MTCONNECT-ADAPTER](https://github.com/JuanenRac/HYDRA-UMC-MTCONNECT-ADAPTER)** — 縮退モード出力を備えた、実際の MTConnect `/probe` および `/current` XML エンドポイント。

*補完ツール&エコシステム運用*
- **[HYDRA-UMC-DASHBOARD-AI](https://github.com/JuanenRac/HYDRA-UMC-DASHBOARD-AI)** — 誠実な統計フォールバックを備えた、DATALAKE/ANOMALY-DETECTOR 上のスマートサマリーと異常ハイライトパネル。
- **[HYDRA-UMC-TOOL-CLI](https://github.com/JuanenRac/HYDRA-UMC-TOOL-CLI)** — 実際の安定した終了コード契約を持つフリート CLI、HYDRA-UMC-SERVER 自身の API の本物のライブクライアント。
- **[HYDRA-UMC-WATCH](https://github.com/JuanenRac/HYDRA-UMC-WATCH)** — 実際の触覚アラートとペアリングされたスマートフォンへの音声リレーを備えた WearOS コンパニオンアプリ。
- **[URTC-SMART-RACK](https://github.com/JuanenRac/URTC-SMART-RACK)** — 実際の工具 ID デコードと Smart Idle 予熱ロジックを備えた、基板搭載ラック用ファームウェア。
- **[URTC-VISION-TOOL](https://github.com/JuanenRac/URTC-VISION-TOOL)** — サーマル/RGB 検査ツールヘッド向けの、ファームウェアと実際の Python ビジョンコンパニオン。
- **[HYDRA-UMC-UPDATER](https://github.com/JuanenRac/HYDRA-UMC-UPDATER)** — このエコシステム内のすべてのリポジトリを検出・クローン・更新する、管理用デスクトップツール。

---

## 📚 ドキュメント & コミュニティ

- **[CONTRIBUTING.md](CONTRIBUTING.md)** —— プルリクエストのための技術スタックとコーディング指針。
- **[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)** —— このコミュニティで期待される行動規範。
- **[SECURITY.md](SECURITY.md)** —— 脆弱性の報告方法と、このプロジェクトの実際のセキュリティ重点領域。
- **[SUPPORT.md](SUPPORT.md)** —— 質問の投稿先とバグの報告先。
- **[LICENSE.md](LICENSE.md)** —— このプロジェクト自身のライセンス。

## 👤 作者
**JuanenRac** (Electro Hobby 3D)
📧 electrohobby3d@gmail.com
📺 [youtube.com/@electrohobby3d](https://youtube.com/@electrohobby3d)

## 📜 ライセンス
GPL-3.0 - 詳細はLICENSEを参照。
