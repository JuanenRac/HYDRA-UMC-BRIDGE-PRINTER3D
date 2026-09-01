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
* ✅ **非破壊的なビルド/テスト:** `build-test.bat`/`.sh` は、G-codeを送信せず、バージョンを変更せず、プリンターに一切触れずに、レスポンスパーサーと安全ゲートをコンパイルする。*(実装済み、下記「ビルドと実行」を参照)*
* 🔜 **実際のプリンター制御(G-codeコマンド)** —— テスト済みプロファイル、認証、物理的安全レビューが整うまで保留されている。*(計画中)*

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
* **なぜ実際のコマンド(G-code)には事前にテスト済みプロファイル、認証、物理的安全レビューが必要なのか。** MoonrakerのAPIは任意のG-codeを受け付けることができる。検証済みのプロファイルと認証なしにそれを送信することは、このブリッジが存在意義とするレディネスチェックそのものを回避することになってしまう。
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
│       └── moonraker.py         # MoonrakerProbe + PrinterBridge 安全ゲート
├── tests/
│   ├── test_artifacts.py         # スライサー証拠テスト(プリンターI/Oなし)
│   └── test_moonraker.py        # レディネス解析とフェイルセーフゲートのテスト
├── tools/
│   ├── build_test.py            # 非破壊的なコンパイル+テストランナー (build-test.bat/.sh)
│   ├── inspect_print_artifact.py # ローカル成果物証拠JSON CLI
│   └── bump_version.py          # pyproject.toml、マニフェスト、CHANGELOG.md を同期
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

**現時点で実在するもの:** バージョン `0.0.7`。ローカルでテスト済みのMoonrakerレディネスアダプター(`MoonrakerProbe` + `PrinterBridge`)が `HYDRA-UMC-SDK` の共有ジョブゲートの上に構築されており、主要スライサー系の読み取り専用G-code/3MF/レジンスライス成果物証拠とプロファイル互換性、ローカルHTTP `/printer/info` 契約検証を含む決定論的な17件の `unittest` スイートと、SDKチェックアウトを伴いCIに組み込まれた非破壊的なbuild-testスクリプトを備える。

**統合境界:** プリンターのネイティブファームウェア(Moonrakerを介したKlipper)は常に動作、ヒーター、熱保護、機械インターロックを保持する。このブリッジはレディネスを読み取るだけであり、その周辺の*補助的な*ロボット作業をゲート制御するのみである。

**今後の課題:** 本ブリッジはまだ実際のプリンター、ホットエンド、ロボットを制御したことがない —— 実際のコマンドを送信するには、事前にテスト済みのプリンタープロファイル、認証、物理的安全レビューが必要である。

---

## 🔗 関連プロジェクト

本プロジェクトは、同じ著者(JuanenRac / Electro Hobby 3D)によるより大きなロボティクス・エコシステムの一部であり、ファームウェア、制御ソフトウェア、AIノード、フリート管理ツールにまたがる。リクエストが実際には本リポジトリではなくこれらのいずれかに関するものである可能性があるため、知っておく価値がある。

### 直接関連

- **[HYDRA-UMC-SDK](https://github.com/JuanenRac/HYDRA-UMC-SDK)** —— このブリッジ(および他のすべてのブリッジ)がジョブを評価する共有の `bridge_contract` ジョブゲート。
- **[HYDRA-UMC-SERVER](https://github.com/JuanenRac/HYDRA-UMC-SERVER)** —— このブリッジが報告する認可済み連携エンドポイント。
- **[HYDRA-UMC-SAFETY-ZONES](https://github.com/JuanenRac/HYDRA-UMC-SAFETY-ZONES)** —— 将来の作業空間安全実証。

### エコシステムのその他

**HYDRA-UMCプラットフォーム** —— このブリッジが補助機能を調整するマルチロボット・マイクロファクトリー
- **[HYDRA-UMC](https://github.com/JuanenRac/HYDRA-UMC)** —— 最大8本のロボットアームを統括するCM5 + STM32H745マザーボード。
- **[HYDRA-UMC-SERVER](https://github.com/JuanenRac/HYDRA-UMC-SERVER)** —— すべての制御クライアントとブリッジが通信するExpress/WebSocketバックエンド。
- **[HYDRA-UMC-STUDIO](https://github.com/JuanenRac/HYDRA-UMC-STUDIO)** —— Webベースの制御ダッシュボード、マルチロボット3D可視化。

**External Automation Bridges** —— 同じ `HYDRA-UMC-SDK` ジョブゲートを共有する兄弟リポジトリ群
- **[HYDRA-UMC-BRIDGE-CNC](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-CNC)** —— CNCセル連携ブリッジ。
- **[HYDRA-UMC-BRIDGE-LASER](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-LASER)** —— レーザーセル連携ブリッジ。
- **[HYDRA-UMC-BRIDGE-OPENPNP](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-OPENPNP)** —— OpenPnP向けボードフローブリッジ。
- **[HYDRA-UMC-BRIDGE-ROS2](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-ROS2)** —— ROS 2との双方向連携境界。

**安全・統合の実証**
- **[HYDRA-UMC-SAFETY-ZONES](https://github.com/JuanenRac/HYDRA-UMC-SAFETY-ZONES)** —— ブリッジファミリー全体で使われるセルゾーンの安全実証。
- **[HYDRA-UMC-HIL-BRIDGE](https://github.com/JuanenRac/HYDRA-UMC-HIL-BRIDGE)** —— ハードウェア・イン・ザ・ループのテスト実証。

## 👤 作者
**JuanenRac** (Electro Hobby 3D)
📧 electrohobby3d@gmail.com
📺 [youtube.com/@electrohobby3d](https://youtube.com/@electrohobby3d)

## 📜 ライセンス
GPL-3.0 - 詳細はLICENSEを参照。
