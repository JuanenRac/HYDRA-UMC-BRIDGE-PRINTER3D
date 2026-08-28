<!-- =============================================================================
HYDRA-UMC-BRIDGE-PRINTER3D - 3D プリンターソフトウェアブリッジ
Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
GPL-3.0-or-later - see LICENSE
============================================================================= -->

# HYDRA-UMC-BRIDGE-PRINTER3D

🇺🇸 [English](README.md) | 🇪🇸 [Español](README_spa.md) | 🇫🇷 [Français](README_fra.md) | 🇮🇹 [Italiano](README_ita.md) | 🇩🇪 [Deutsch](README_deu.md) | 🇨🇳 [简体中文](README_zho.md) | 🇯🇵 **日本語**

オープンな 3D プリンターソフトウェアと HYDRA-UMC のロボット補助機構を
結ぶ上位コーディネーターです。ネイティブのプリンターファームウェアは、
動作、ヒーター、熱保護、機械インターロックを引き続き担当します。

## アーキテクチャ

```text
Moonraker/Klipper <-> BRIDGE-PRINTER3D <-> SDK <-> SERVER <-> セル安全
```

最初のアダプターは Moonraker の `/printer/info` 準備応答を使用します。
`ready` だけがアイドル状態のプリンターに対応します。起動、停止、エラー
状態はフェイルクローズです。準備できていないプリンターに対してロボット
作業を計画することはできません。

## ビルドとテスト

Windows では `build-test.bat`、Linux では `bash build-test.sh` を実行します。
プリンターに G-code を送信せず、バージョンを変更せず、プリンターに接触せず
に、応答パーサーと安全ゲートをコンパイルしてテストします。実機コマンドには、
検証済みプロファイル、認証、物理安全レビューが必要です。

## 関連プロジェクト

| プロジェクト | 役割 |
| --- | --- |
| [HYDRA-UMC-SDK](https://github.com/JuanenRac/HYDRA-UMC-SDK) | 共有コントラクト。 |
| [HYDRA-UMC-SERVER](https://github.com/JuanenRac/HYDRA-UMC-SERVER) | 認可済み協調エンドポイント。 |
| [HYDRA-UMC-SAFETY-ZONES](https://github.com/JuanenRac/HYDRA-UMC-SAFETY-ZONES) | 将来のワークスペース証跡。 |

## 状態

バージョン `0.0.1` には、ローカルでテスト済みの Moonraker 準備状態アダプター
が含まれます。実際のプリンター、ホットエンド、ロボットはまだ制御していません。
