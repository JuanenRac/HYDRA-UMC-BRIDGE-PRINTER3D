<!-- =============================================================================
HYDRA-UMC-BRIDGE-PRINTER3D - 3D 打印软件桥接
Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
GPL-3.0-or-later - see LICENSE
============================================================================= -->

<p align="center">
  <img src="images/HYDRA_UMC_BANNER.svg" alt="HYDRA-UMC-BRIDGE-PRINTER3D 横幅" width="100%">
</p>

# 🖨️ HYDRA-UMC-BRIDGE-PRINTER3D

<p align="center"><a href="README.md">🇺🇸 English</a> | <a href="README_spa.md">🇪🇸 Español</a> | <a href="README_fra.md">🇫🇷 Français</a> | <a href="README_ita.md">🇮🇹 Italiano</a> | <a href="README_deu.md">🇩🇪 Deutsch</a> | 🇨🇳 <b>简体中文</b> | <a href="README_jpn.md">🇯🇵 日本語</a></p>

### 🌡️ 面向开源 3D 打印软件的故障安全协调桥接

<p align="left">
  <img src="https://img.shields.io/badge/许可证-GPL%203.0-blue.svg" alt="GPL 3.0">
  <img src="https://img.shields.io/badge/Python-3.11%2B-3776AB.svg" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/Safety-Fails%20Closed-red.svg" alt="故障安全">
</p>

---

## 1. 🛠️ 技术概览

**HYDRA-UMC-BRIDGE-PRINTER3D** 是开源 3D 打印软件(Moonraker/Klipper)与 HYDRA-UMC 机器人辅助设备之间的高层协调器。打印机的原生固件始终负责运动、加热器、热保护和机器联锁——本桥接只读取就绪状态并围绕它协调辅助设备。

它属于 **External Automation Bridges** 家族:一组共享 `HYDRA-UMC-SDK` 相同安全契约的兄弟仓库(CNC、LASER、OPENPNP、PRINTER3D、ROS2),因此任何一个桥接都不能自行发明"可以安全工作"的定义。

### 核心特性:
* ✅ **真实的 Moonraker 就绪探测:** `moonraker.py` 中的 `MoonrakerProbe` 使用一个仅依赖标准库的小型客户端(`urlopen` + `json`)读取 Moonraker 文档化的 `/printer/info` 接口——除 Python 标准库外没有任何额外依赖。*(已实现,并在 `tests/test_moonraker.py` 中测试)*
* ✅ **真实的故障安全状态解析:** `parse_info()` 只把字面字符串 `"ready"` 映射为 `MachineState.IDLE`;`startup`/`shutdown`/`error` 映射为 `FAULT`,其余情况(包括格式错误的响应)一律映射为 `OFFLINE`——绝不会映射到允许围绕打印机规划机器人动作的状态。*(已实现)*
* ✅ **真实的共享安全门控:** 每个被观察到的任务都会通过 `HYDRA-UMC-SDK` 的 `bridge_contract` 中的 `evaluate_job()` 重新评估,这与所有兄弟桥接以及 HYDRA-UMC-SERVER 使用的是同一个门控。*(已实现)*
* ✅ **非变更式构建/测试:** `build-test.bat`/`.sh` 编译响应解析器和安全门控,不发送 G-code、不改变版本、不触碰打印机。*(已实现,见下方"构建与运行")*
* 🔜 **真正的打印机控制(G-code 命令)** —— 推迟到已有经过测试的配置文件、身份验证和物理安全评审之后。*(计划中)*

---

## 2. 🔄 打印机协调流程

```mermaid
flowchart LR
    PRINTER["Moonraker / Klipper<br/>(/printer/info)"] --> BRIDGE["BRIDGE-PRINTER3D<br/>MoonrakerProbe.parse_info()"]
    BRIDGE -- "BridgeJob + 观测到的 MachineState" --> SDK["HYDRA-UMC-SDK<br/>evaluate_job()"]
    SDK -- GateDecision --> SERVER["HYDRA-UMC-SERVER"]
    SERVER -- "任务 / 中止" --> CELL["单元安全"]
```

---

## 3. 🧱 架构与设计决策

* **为什么只有 Moonraker 字面上的 `"ready"` 状态会被映射为空闲。** `parse_info()` 的状态映射被刻意设计得很窄:`ready` → `IDLE`,`startup`/`shutdown`/`error` → `FAULT`(故障安全),其他任何值或缺失值 → `OFFLINE`。对于无法识别的打印机状态,不存在"默认安全"的假设。
* **为什么解析逻辑是一个独立于网络获取的 `@staticmethod`。** `MoonrakerProbe.parse_info()` 接收一个普通的 `dict`,完全可以在不进行网络调用、不需要运行中的打印机的情况下做单元测试;`fetch()` 是调用它的、必然涉及网络的薄层部分。与安全相关的逻辑正好位于那个永远不需要真实打印机就能测试的部分。
* **为什么探测器使用标准库的 `urlopen`/`json`,而不是某个 Moonraker 客户端库。** 把依赖面限制在 Python 标准库内,能让与安全相关的解析逻辑保持最小化、可审计,并且不受第三方客户端自身在重试、超时或错误处理上的假设所影响。
* **为什么桥接会构造一个新的 `BridgeJob` 并委托给共享的 `evaluate_job()`,而不是自己编写接受/拒绝逻辑。** 全部五个 External Automation Bridges(CNC、LASER、OPENPNP、PRINTER3D、ROS2)都复用 `HYDRA-UMC-SDK` 中完全相同的 `bridge_contract`,因此"什么才算安全到可以启动任务"不会在它们之间悄悄产生分歧。
* **为什么真正的命令(G-code)需要先有经过测试的配置文件、身份验证和物理安全评审。** Moonraker 的 API 可以接受任意 G-code;在没有经过验证的配置文件和身份验证的情况下发送它,恰恰会绕过本桥接存在的意义——执行就绪检查。
* **它如何融入整个生态系统。** BRIDGE-PRINTER3D 位于 Moonraker/Klipper 与 `HYDRA-UMC-SDK` → `HYDRA-UMC-SERVER` → 单元安全之间:它协调围绕打印机的辅助机器人工作,绝不会取代原生固件、加热器或热保护。

---

## 📂 目录结构

```text
HYDRA-UMC-BRIDGE-PRINTER3D/
├── src/
│   └── hydra_umc_bridge_printer3d/
│       ├── __init__.py
│       └── moonraker.py         # MoonrakerProbe + PrinterBridge 安全门控
├── tests/
│   └── test_moonraker.py        # 就绪状态解析与故障安全门控测试
├── tools/
│   ├── build_test.py            # 非变更式编译 + 测试运行器 (build-test.bat/.sh)
│   └── bump_version.py          # 同步 pyproject.toml、清单和 CHANGELOG.md
├── build-test.bat / build-test.sh  # 仅验证,绝不修改仓库
├── build.bat / build.sh            # 先验证,成功后才更新版本 + CHANGELOG
├── pyproject.toml               # 包元数据;依赖 HYDRA-UMC-SDK (git)
├── hydra-umc.project.json       # 生态系统清单(版本、成熟度、家族)
├── CHANGELOG.md
├── CODE_OF_CONDUCT.md / CONTRIBUTING.md / SECURITY.md / SUPPORT.md
├── LICENSE / LICENSE.md
└── README.md / README_*.md      # 本文件及其 6 种译文
```

---

## 4. ⚙️ 构建与运行

需要 Python 3.11+。`tools/build_test.py` 期望 `HYDRA-UMC-SDK` 作为兄弟目录被检出(`../HYDRA-UMC-SDK`),或通过环境变量 `HYDRA_UMC_SDK_ROOT` 指定。

```bash
# Windows
build-test.bat      # 仅验证 —— 不改变版本/CHANGELOG
build.bat            # 先验证,成功后更新版本 + CHANGELOG

# Linux/macOS
bash build-test.sh
bash build.sh
```

`build-test` 使用 `py_compile` 编译 `src/` 下的每个模块,并运行完整的 `unittest` 套件(`tests/test_moonraker.py`),证明就绪响应解析和故障安全门控均按预期工作 —— 它不发送任何 G-code、不触碰打印机,也绝不会修改仓库。`build` 会先运行同样的验证,只有成功后才调用 `tools/bump_version.py`,在 `pyproject.toml`、`hydra-umc.project.json` 和 `CHANGELOG.md` 之间同步版本号。目前尚无真正的打印机 `run` 命令 —— 这需要先有经过测试的配置文件、身份验证和物理安全评审。

---

## ✅ 当前状态与后续步骤

**目前真实的部分:** 版本 `0.0.1`,一个已在本地测试过的 Moonraker 就绪适配器(`MoonrakerProbe` + `PrinterBridge`),依托 `HYDRA-UMC-SDK` 的共享任务门控,配有确定性的 `unittest` 套件,以及已接入 CI 并带 SDK 检出的非变更式 build-test 脚本。

**集成边界:** 打印机的原生固件(通过 Moonraker 的 Klipper)始终保留运动、加热器、热保护和机器联锁;本桥接只负责读取就绪状态,并门控围绕它的*辅助*机器人工作。

**仍待完成:** 本桥接尚未控制过真实的打印机、热端或机器人 —— 发送真正的命令需要先有经过测试的打印机配置文件、身份验证和物理安全评审。

---

## 🔗 相关项目

本项目是同一作者(JuanenRac / Electro Hobby 3D)更大的机器人生态系统的一部分,涵盖固件、控制软件、AI 节点和车队工具。了解这一点很有必要,因为某个请求实际上可能与这些项目之一有关,而不是与本仓库有关。

### 直接相关

- **[HYDRA-UMC-SDK](https://github.com/JuanenRac/HYDRA-UMC-SDK)** —— 共享的 `bridge_contract` 任务门控,本桥接(以及所有其他桥接)都通过它评估任务。
- **[HYDRA-UMC-SERVER](https://github.com/JuanenRac/HYDRA-UMC-SERVER)** —— 本桥接汇报的经过授权的协调端点。
- **[HYDRA-UMC-SAFETY-ZONES](https://github.com/JuanenRac/HYDRA-UMC-SAFETY-ZONES)** —— 未来的工作空间安全证据。

### 生态系统的其余部分

**HYDRA-UMC 平台** —— 本桥接为其协调辅助功能的多机器人微工厂
- **[HYDRA-UMC](https://github.com/JuanenRac/HYDRA-UMC)** —— 协调多达 8 条机械臂的 CM5 + STM32H745 主板。
- **[HYDRA-UMC-SERVER](https://github.com/JuanenRac/HYDRA-UMC-SERVER)** —— 每个控制客户端和桥接都会对接的 Express/WebSocket 后端。
- **[HYDRA-UMC-STUDIO](https://github.com/JuanenRac/HYDRA-UMC-STUDIO)** —— 基于网页的控制仪表盘,多机器人 3D 可视化。

**External Automation Bridges** —— 共享同一个 `HYDRA-UMC-SDK` 任务门控的兄弟仓库
- **[HYDRA-UMC-BRIDGE-CNC](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-CNC)** —— CNC 单元协调桥接。
- **[HYDRA-UMC-BRIDGE-LASER](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-LASER)** —— 激光单元协调桥接。
- **[HYDRA-UMC-BRIDGE-OPENPNP](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-OPENPNP)** —— 面向 OpenPnP 的板级流程桥接。
- **[HYDRA-UMC-BRIDGE-ROS2](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-ROS2)** —— 与 ROS 2 之间的双向协调边界。

**安全与集成证据**
- **[HYDRA-UMC-SAFETY-ZONES](https://github.com/JuanenRac/HYDRA-UMC-SAFETY-ZONES)** —— 整个桥接家族共用的单元区域安全证据。
- **[HYDRA-UMC-HIL-BRIDGE](https://github.com/JuanenRac/HYDRA-UMC-HIL-BRIDGE)** —— 硬件在环测试证据。

## 👤 作者
**JuanenRac** (Electro Hobby 3D)
📧 electrohobby3d@gmail.com

## 📜 许可证
GPL-3.0 - 详见 LICENSE。

## 🛠️ 构建与运行

在发布构建之前,使用不带版本递增的构建检查:

| 操作 | Windows | Linux / macOS |
|---|---|---|
| 构建检查(不改变版本或 CHANGELOG) | `build-test.bat` | `./build-test.sh` |
| 运行 / 开发(如提供) | `run*.bat` 或 `dev*.bat` | `./run*.sh` 或 `./dev*.sh` |

`build-test.bat` 和 `build-test.sh` 会编译或验证项目技术栈,但不会递增 `hydra-umc.project.json` 或修改 `CHANGELOG.md`。它们只能产生正常的编译器输出。现有的 `build*.bat`、`build*.sh`、`run*` 和 `dev*` 脚本保留各自项目特定的、带版本管理或运行时行为;在需要这些行为时使用它们。
