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

**HYDRA-UMC-BRIDGE-PRINTER3D** 是开源 3D 打印软件(Moonraker/Klipper)与 HYDRA-UMC 机器人辅助设备之间的高层协调器。它还会以只读方式识别本地切片软件产物。打印机的原生固件始终负责运动、加热器、热保护和机器联锁——本桥接只读取就绪状态、记录产物证据并围绕它协调辅助设备。

它属于 **External Automation Bridges** 家族:一组共享 `HYDRA-UMC-SDK` 相同安全契约的兄弟仓库(CNC、LASER、OPENPNP、PRINTER3D、ROS2),因此任何一个桥接都不能自行发明"可以安全工作"的定义。

### 核心特性:
* ✅ **真实的 Moonraker 就绪探测:** `moonraker.py` 中的 `MoonrakerProbe` 使用一个仅依赖标准库的小型客户端(`urlopen` + `json`)读取 Moonraker 文档化的 `/printer/info` 接口——除 Python 标准库外没有任何额外依赖。*(已实现,并在 `tests/test_moonraker.py` 中测试)*
* ✅ **真实的故障安全状态解析:** `parse_info()` 只把字面字符串 `"ready"` 映射为 `MachineState.IDLE`;`startup`/`shutdown`/`error` 映射为 `FAULT`,其余情况(包括格式错误的响应)一律映射为 `OFFLINE`——绝不会映射到允许围绕打印机规划机器人动作的状态。*(已实现)*
* ✅ **真实的共享安全门控:** 每个被观察到的任务都会通过 `HYDRA-UMC-SDK` 的 `bridge_contract` 中的 `evaluate_job()` 重新评估,这与所有兄弟桥接以及 HYDRA-UMC-SERVER 使用的是同一个门控。*(已实现)*
* ✅ **独立于切片软件的产物检查:** `artifacts.py` 只通过本地证据识别 OrcaSlicer、Ultimaker Cura、PrusaSlicer、Bambu Studio 和其他切片软件生成的普通 FDM G-code；它也能识别 3MF 包和兼容 Lychee 的树脂切片，且不会解包、解析命令、上传或打印。*(已实现,并在 `tests/test_artifacts.py` 中测试)*
* ✅ **配置文件证据边界:** `profiles.py` 可以将检查过的产物与已声明的 FDM 或树脂配置文件进行匹配,但即使匹配成功也会返回 `execution_authorized=False`。*(已实现,在 `tests/test_profiles.py` 中测试)*
* ✅ **真实的、由 SDK 门控的作业命令:** `MoonrakerJobControl` 向 Moonraker 文档化的 `/printer/print/start|pause|resume|cancel` 端点发送真实的 `POST` 请求——`start_job()` 受与本生态系统中所有生产性调度相同的 `evaluate_job()` 决策门控;`pause_job()`/`cancel_job()` 始终被允许(与 `ABORT` 相同的降级逻辑);`resume_job()` 要求打印机真正处于 `HOLDING` 状态。它只按名称启动一个已上传、已切片的文件——从不流式传输原始 G-code。*(已实现,在 `tests/test_moonraker.py` 中测试)*
* ✅ **非变更式构建/测试:** `build-test.bat`/`.sh` 编译响应解析器和安全门控,不发送 G-code、不改变版本、不触碰打印机。*(已实现,见下方"构建与运行")*
* 🔜 **原始 G-code 流式传输:** 刻意仍然推迟——发送任意底层命令(而非一个已命名、已切片的作业)需要经过测试的配置文件、身份验证以及本桥目前还不具备的物理安全评审。*(计划中)*

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
* **为什么任务命令(start/pause/resume/cancel)是真实的,而原始 G-code 流式传输还不是。** Moonraker 的 `/printer/print/*` 端点始终只是按名称引用一个已经上传、已经切片好的文件——这与 Moonraker/Klipper 自身已经在该文件上强制执行的安全边界相同。任意的原始 G-code 是一个从根本上不同、大得多的信任面(它可以包含任何内容),仍然需要经过测试的配置文件、身份验证和物理安全评审,而本桥接目前还没有这些。
* **为什么 `resume_job()` 不复用通用的 `evaluate_job()` 关卡。** 那个关卡是围绕"生产性工作需要一台处于 IDLE 状态的机器"构建的——这与恢复一个已暂停的任务正好相反,后者只有从 `HOLDING` 状态出发才有意义。与 DROIDS 的 `stand_request()`/`sit_request()` 已经使用的独立关卡逻辑相同。
* **它如何融入整个生态系统。** BRIDGE-PRINTER3D 位于 Moonraker/Klipper 与 `HYDRA-UMC-SDK` → `HYDRA-UMC-SERVER` → 单元安全之间:它协调围绕打印机的辅助机器人工作,绝不会取代原生固件、加热器或热保护。

## 🧾 切片软件产物兼容性

只读产物通道支持 OrcaSlicer、Ultimaker Cura、PrusaSlicer、Bambu Studio 和其他切片软件生成的常规 FDM G-code(`.gcode`、`.gco`、`.gc`)。熟悉的注释会提供来源提示；没有标记时保持为 `unknown-slicer`。`.gcode.3mf` 和通用 `.3mf` 会被识别，但绝不会解包。来自兼容 Lychee 工作流的树脂切片(`.ctb`、`.goo`、`.photon`、`.pwmo`、`.pws`、`.sl1`)被有意作为不透明内容处理，绝不会归属到某台特定打印机或切片软件。

这是与**输出产物**的兼容，而不是对这些应用的远程控制。桥接不会启动切片软件、修改配置文件、解析/执行 G-code、上传文件、联系云服务或启动打印。准确矩阵和未来控制前置条件见[切片软件产物兼容性](docs/SLICER_ARTIFACT_COMPATIBILITY.md)。

---

## 📂 目录结构

```text
HYDRA-UMC-BRIDGE-PRINTER3D/
├── src/
│   └── hydra_umc_bridge_printer3d/
│       ├── __init__.py
│       ├── artifacts.py         # 只读 G-code、3MF 和树脂切片证据
│       ├── profiles.py          # 配置文件兼容性证据;绝非打印授权
│       ├── moonraker.py         # MoonrakerProbe + PrinterBridge 安全门控
│       └── mqtt_transport.py    # 面向此 bridge 已有真实 Moonraker 逻辑的真实 MQTT broker 传输
├── tests/
│   ├── test_artifacts.py         # 切片软件证据测试(无打印机 I/O)
│   ├── test_profiles.py         # 配置文件匹配始终拒绝执行
│   ├── test_moonraker.py        # 就绪状态解析与故障安全门控测试
│   └── test_mqtt_transport.py   # 针对模拟 broker 客户端的 MQTT 命令/状态格式测试
├── tools/
│   ├── build_test.py            # 非变更式编译 + 测试运行器 (build-test.bat/.sh)
│   ├── inspect_print_artifact.py # 本地产物证据 JSON CLI
│   ├── assess_print_profile.py  # 离线配置文件与产物比对 CLI;从不授权执行
│   ├── ci_validate.py           # 无依赖、非破坏性的CI基线检查 (由 .github/workflows/ci.yml 使用)
│   └── bump_version.py          # 同步 pyproject.toml、清单和 CHANGELOG.md
├── docs/
│   ├── BRIDGE_GUIDE.md                        # 范围、兼容平台、脚本、硬件验收门控
│   ├── PRINT_PROFILE_BOUNDARY.md              # 配置文件兼容性证据相对于打印授权意味着什么
│   └── SLICER_ARTIFACT_COMPATIBILITY.md       # 此 bridge 可作为证据读取的切片软件产物格式
├── images/
│   └── HYDRA_UMC_BANNER.svg     # README 横幅图
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

`build-test` 使用 `py_compile` 编译 `src/` 和 `tools/` 下的每个模块,并运行完整的 `unittest` 套件(`tests/test_moonraker.py` 和 `tests/test_artifacts.py`),证明就绪响应解析、产物检查和故障安全门控均按预期工作 —— 它不发送任何 G-code、不触碰打印机,也绝不会修改仓库。`build` 会先运行同样的验证,只有成功后才调用 `tools/bump_version.py`,在 `pyproject.toml`、`hydra-umc.project.json` 和 `CHANGELOG.md` 之间同步版本号。目前尚无真正的打印机 `run` 命令 —— 这需要先有经过测试的配置文件、身份验证和物理安全评审。

要在不连接打印机的情况下检查本地切片软件输出:

```bash
py tools/inspect_print_artifact.py 路径/任务.gcode
```

---

## ✅ 当前状态与后续步骤

**目前真实的部分:** 版本 `0.1.0`,一个已在本地测试过的 Moonraker 就绪适配器(`MoonrakerProbe` + `PrinterBridge`),依托 `HYDRA-UMC-SDK` 的共享任务门控,真实的、由 SDK 门控的作业命令(`MoonrakerJobControl`:通过 Moonraker 自身的 REST API 启动/暂停/恢复/取消一个已上传的文件),包含主要切片软件系列的只读 G-code/3MF/树脂切片产物与配置文件兼容性证据,配有确定性的四十九项 `unittest` 测试套件(包括本地 HTTP `/printer/info` 合同验证、真实的、独立的 `/printer/objects/query?print_stats=state` 合同,以及真实的 `POST` 作业命令验证),以及已接入 CI 并带 SDK 检出的非变更式 build-test 脚本。

**集成边界:** 打印机的原生固件(通过 Moonraker 的 Klipper)始终保留运动、加热器、热保护和机器联锁;本桥接只负责读取就绪状态,并门控围绕它的*辅助*机器人工作。

**仍待完成:** 本桥接尚未控制过真实的打印机、热端或机器人 —— 发送真正的命令需要先有经过测试的打印机配置文件、身份验证和物理安全评审。

---

## 🔗 相关项目

本项目是同一作者(JuanenRac / Electro Hobby 3D)打造的 HYDRA-UMC 机器人生态系统的一部分。值得了解,因为某个请求实际上可能是关于这些项目之一,而非本仓库本身。

**父项目**
- **[HYDRA-UMC-SERVER](https://github.com/JuanenRac/HYDRA-UMC-SERVER)** — 每个控制客户端真正通信的真实无头后端(REST/WebSocket);每条指令通过本桥接自身的本地安全门限后,本桥接向其汇报的经过认证的生态系统边界。

**兄弟项目** —— 同样与 HYDRA-UMC-SERVER 自身 API 通信,各自作为独立客户端
- **[HYDRA-UMC-STUDIO](https://github.com/JuanenRac/HYDRA-UMC-STUDIO)** — 具有实时多机器人 3D 可视化的网页控制面板。
- **[HYDRA-UMC-SUITE](https://github.com/JuanenRac/HYDRA-UMC-SUITE)** — 面向多台服务器的桌面(PySide6)集群指挥中心，打包为独立可执行文件。
- **[HYDRA-UMC-ANDROID-CONTROL](https://github.com/JuanenRac/HYDRA-UMC-ANDROID-CONTROL)** — 具有生物识别登录和配对 Wear OS 伴侣应用的原生 Android 控制应用。
- **[HYDRA-UMC-IOS-CONTROL](https://github.com/JuanenRac/HYDRA-UMC-IOS-CONTROL)** — 具有实时 WebSocket 同步的 iOS/iPadOS 控制应用(Flutter)。
- **[HYDRA-UMC-DSI](https://github.com/JuanenRac/HYDRA-UMC-DSI)** — 面向机载 7 英寸 DSI 触摸屏的原生触控界面，直接嵌入 CM5 本体。
- **[HYDRA-UMC-BRIDGE-AMR](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-AMR)** — 通过真实的 VDA 5050 MQTT 发布者为 AGV/AMR 车队提供的协调边界。
- **[HYDRA-UMC-BRIDGE-CNC](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-CNC)** — 具备真实 GRBL 状态/控制字节访问能力的高层 CNC 单元协调器。
- **[HYDRA-UMC-BRIDGE-DROIDS](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-DROIDS)** — 面向足式/人形机器人的协调边界，具备真实的 Boston Dynamics Spot 指令发送器。
- **[HYDRA-UMC-BRIDGE-LASER](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-LASER)** — 读取 3 项真实钥匙/外壳/联锁 GPIO 安全信号的激光单元安全协调器。
- **[HYDRA-UMC-BRIDGE-OPENPNP](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-OPENPNP)** — 面向 OpenPnP 贴片机板级流程的安全高层协调器。
- **[HYDRA-UMC-BRIDGE-ROS2](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-ROS2)** — 具备真实的惰性导入 rclpy ROS 2 传输层的安全协调器。
- **[HYDRA-UMC-BRIDGE-UAV](https://github.com/JuanenRac/HYDRA-UMC-BRIDGE-UAV)** — 面向搭载摄像头的无人机的协调边界，具备真实的 MAVLink 指令发送器。

**直接相关**
- **[HYDRA-UMC-SDK](https://github.com/JuanenRac/HYDRA-UMC-SDK)** — 每个桥接都据此校验自身指令的共享 JSON-Schema 契约与安全门限边界。
- **[HYDRA-UMC-MQTT-BROKER](https://github.com/JuanenRac/HYDRA-UMC-MQTT-BROKER)** — `mqtt_transport.py` 为本桥接自身 `hydra/bridges/printer3d/...` 主题提供的真实传输——状态加上真实的 Moonraker start/pause/resume/cancel 指令,以及共享的作业门限;详见该仓库自身的 `docs/BRIDGE_TOPICS.md`。
- **[HYDRA-UMC-SAFETY-ZONES](https://github.com/JuanenRac/HYDRA-UMC-SAFETY-ZONES)** — 面向本桥接的未来工作空间安全验证。

**生态系统中的其他项目**

*核心硬件与平台*
- **[HYDRA-UMC](https://github.com/JuanenRac/HYDRA-UMC)** — 机器人手臂的真实主板——CM5 主机 + 双核 STM32H745，通过 CAN-OTA/SPI-OTA 协调最多 8 条工具臂。
- **[HYDRA-UMC-OS](https://github.com/JuanenRac/HYDRA-UMC-OS)** — 面向 CM5 的可复现 Raspberry Pi OS 产品层——只读代理、经过验证的配置/配置文件、WiFi 首次配网。

*核心后端与客户端*
- **[HYDRA-UMC-EDITOR-URDF](https://github.com/JuanenRac/HYDRA-UMC-EDITOR-URDF)** — 将完成的模型推送到 STUDIO 自身目录的桌面版图形化 URDF 创建/编辑工具。

*URTC 工具平台*
- **[URTC](https://github.com/JuanenRac/URTC)** — 面向实体 Universal Robot Tool Controller 板卡的固件，通过 CAN 总线支持 25 种以上工具配置。
- **[URTC-FLASHER](https://github.com/JuanenRac/URTC-FLASHER)** — 面向 URTC 板卡的桌面图形烧录工具，支持 CAN-OTA 以及全芯片 SWD/JTAG。
- **[URTC-TESTER](https://github.com/JuanenRac/URTC-TESTER)** — 面向 URTC 板卡的桌面实时 CAN 总线诊断工具，每种工具配置对应一个面板。
- **[URTC-WEB-STUDIO](https://github.com/JuanenRac/URTC-WEB-STUDIO)** — 通过 Web Serial API 实现的浏览器版 URTC-TESTER 替代方案，无需本地安装。

*视觉 AI 节点(Hailo-8)*
- **[HYDRA-UMC-VISION-NODE](https://github.com/JuanenRac/HYDRA-UMC-VISION-NODE)** — 面向 Hailo-8 视觉流水线的集成中枢，具备逐阶段的真实硬件就绪检测。
- **[HYDRA-UMC-DETECTION-HEF](https://github.com/JuanenRac/HYDRA-UMC-DETECTION-HEF)** — 具备 Hailo 架构/校验和安全加载验证的真实编译模型注册表。
- **[HYDRA-UMC-VISION-STREAMER](https://github.com/JuanenRac/HYDRA-UMC-VISION-STREAMER)** — 具备真实 HailoRT 集成边界的真实 GStreamer 流水线 + MediaMTX 配置生成器。
- **[HYDRA-UMC-VISUAL-SERVOING-API](https://github.com/JuanenRac/HYDRA-UMC-VISUAL-SERVOING-API)** — 具备真实 Position-Based Visual Servoing 修正律，并依据上游区域状态进行安全门控。

*认知 AI 节点(Hailo-10)*
- **[HYDRA-UMC-COGNITIVE-NODE](https://github.com/JuanenRac/HYDRA-UMC-COGNITIVE-NODE)** — 面向 Hailo-10 认知流水线(LLM/VLA/语音编排)的集成中枢。
- **[HYDRA-UMC-VLA-ENGINE](https://github.com/JuanenRac/HYDRA-UMC-VLA-ENGINE)** — 面向 Vision-Language-Action 模型的真实动作 token 编解码与轨迹生成。
- **[HYDRA-UMC-VOICE-UI](https://github.com/JuanenRac/HYDRA-UMC-VOICE-UI)** — 具备受限、需确认的 Watch 中继的真实语音前端(VAD + 意图解析)。
- **[HYDRA-UMC-SEMANTIC-PLANNER](https://github.com/JuanenRac/HYDRA-UMC-SEMANTIC-PLANNER)** — 基于真实规则的任务分解，以及针对 MCU 错误码的语义化错误恢复。
- **[HYDRA-UMC-DOCS-QA](https://github.com/JuanenRac/HYDRA-UMC-DOCS-QA)** — 面向本生态系统自身 Markdown 文档的真实纯标准库 TF-IDF 文档检索。

*编排与集群*
- **[HYDRA-UMC-ORCHESTRATOR](https://github.com/JuanenRac/HYDRA-UMC-ORCHESTRATOR)** — 具备真实 gRPC/Protobuf 健康报告契约与任务状态机的集成中枢。
- **[HYDRA-UMC-JOB-DISPATCHER](https://github.com/JuanenRac/HYDRA-UMC-JOB-DISPATCHER)** — 基于真实 HTTP API 的真实优先级任务队列，支持去重。
- **[HYDRA-UMC-NODE-HEALING](https://github.com/JuanenRac/HYDRA-UMC-NODE-HEALING)** — 具备重试/退避与身份不匹配检测的真实基于 gRPC 的车队健康看门狗。
- **[HYDRA-UMC-PATH-PLANNER-3D](https://github.com/JuanenRac/HYDRA-UMC-PATH-PLANNER-3D)** — 具备真实障碍物/工作空间碰撞校验的真实基于 RRT 的三维路径规划器。
- **[HYDRA-UMC-SWARM-SYNC](https://github.com/JuanenRac/HYDRA-UMC-SWARM-SYNC)** — 经过多单元收敛属性测试的真实 CRDT LWW-Element-Map 状态同步。

*数字孪生与仿真*
- **[HYDRA-UMC-TWIN](https://github.com/JuanenRac/HYDRA-UMC-TWIN)** — 面向数字孪生引擎的集成中枢，具备真实的版本兼容性同步契约。
- **[HYDRA-UMC-HIL-BRIDGE](https://github.com/JuanenRac/HYDRA-UMC-HIL-BRIDGE)** — 在仿真与真实硬件之间路由指令的真实硬件在环安全联锁。
- **[HYDRA-UMC-PHYSICS-REPLICA](https://github.com/JuanenRac/HYDRA-UMC-PHYSICS-REPLICA)** — 面向真实 URDF 子集的真实正向运动学与关节限位校验。
- **[HYDRA-UMC-SYNTHETIC-DATA-GEN](https://github.com/JuanenRac/HYDRA-UMC-SYNTHETIC-DATA-GEN)** — 具备 YOLO/COCO 标注导出功能的真实程序化 2D 场景生成器。

*数据与分析*
- **[HYDRA-UMC-DATALAKE](https://github.com/JuanenRac/HYDRA-UMC-DATALAKE)** — 具备真实数据摄入/查询 HTTP API 的真实 sqlite3 时序数据存储。
- **[HYDRA-UMC-ANOMALY-DETECTOR](https://github.com/JuanenRac/HYDRA-UMC-ANOMALY-DETECTOR)** — 具备漂移监测能力的真实 FFT + 统计基线异常检测器。
- **[HYDRA-UMC-PRODUCTION-REPORTS](https://github.com/JuanenRac/HYDRA-UMC-PRODUCTION-REPORTS)** — 基于 DATALAKE 历史数据的真实 OEE/可用率计算，支持可复现的 CSV 导出。
- **[HYDRA-UMC-TELEMETRY-COLLECTOR](https://github.com/JuanenRac/HYDRA-UMC-TELEMETRY-COLLECTOR)** — 面向 DATALAKE 的真实 CAN/WebSocket 数据摄入管道，支持序列去重。

*工业网关*
- **[HYDRA-UMC-GATEWAY-INDUSTRIAL](https://github.com/JuanenRac/HYDRA-UMC-GATEWAY-INDUSTRIAL)** — 中继至工业协议的集成中枢，具备真实的指令白名单/背压控制层。
- **[HYDRA-UMC-OPCUA-SERVER](https://github.com/JuanenRac/HYDRA-UMC-OPCUA-SERVER)** — 经真实二进制协议客户端会话验证的真实 OPC-UA 地址空间。
- **[HYDRA-UMC-MTCONNECT-ADAPTER](https://github.com/JuanenRac/HYDRA-UMC-MTCONNECT-ADAPTER)** — 具备降级模式输出的真实 MTConnect `/probe` 与 `/current` XML 端点。

*辅助工具与生态系统运维*
- **[HYDRA-UMC-DASHBOARD-AI](https://github.com/JuanenRac/HYDRA-UMC-DASHBOARD-AI)** — 基于 DATALAKE/ANOMALY-DETECTOR 的智能摘要与异常高亮面板，具备诚实的统计回退机制。
- **[HYDRA-UMC-TOOL-CLI](https://github.com/JuanenRac/HYDRA-UMC-TOOL-CLI)** — 具备真实、稳定退出码契约的车队 CLI，是 HYDRA-UMC-SERVER 自身 API 的真实在线客户端。
- **[HYDRA-UMC-WATCH](https://github.com/JuanenRac/HYDRA-UMC-WATCH)** — 具备真实触觉提醒与配对手机语音中继功能的 WearOS 伴侣应用。
- **[URTC-SMART-RACK](https://github.com/JuanenRac/URTC-SMART-RACK)** — 面向板卡安装机架的固件，具备真实的工具 ID 解码与 Smart Idle 预热逻辑。
- **[URTC-VISION-TOOL](https://github.com/JuanenRac/URTC-VISION-TOOL)** — 面向热成像/RGB 检测工具头的固件及真实 Python 视觉伴侣程序。
- **[HYDRA-UMC-UPDATER](https://github.com/JuanenRac/HYDRA-UMC-UPDATER)** — 发现、克隆并更新本生态系统中每个仓库的管理类桌面工具。

## 👤 作者
**JuanenRac** (Electro Hobby 3D)
📧 electrohobby3d@gmail.com
📺 [youtube.com/@electrohobby3d](https://youtube.com/@electrohobby3d)

## 📜 许可证
GPL-3.0 - 详见 LICENSE。
