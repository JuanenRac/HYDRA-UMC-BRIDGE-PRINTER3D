<!-- =============================================================================
HYDRA-UMC-BRIDGE-PRINTER3D - 3D 打印机软件桥接
Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
GPL-3.0-or-later - see LICENSE
============================================================================= -->

# HYDRA-UMC-BRIDGE-PRINTER3D

🇺🇸 [English](README.md) | 🇪🇸 [Español](README_spa.md) | 🇫🇷 [Français](README_fra.md) | 🇮🇹 [Italiano](README_ita.md) | 🇩🇪 [Deutsch](README_deu.md) | 🇨🇳 **简体中文** | 🇯🇵 [日本語](README_jpn.md)

面向开放 3D 打印软件与 HYDRA-UMC 机器人辅助设备的高级协调器。原生打印机
固件仍负责运动、加热器、热保护和机器联锁。

## 架构

```text
Moonraker/Klipper <-> BRIDGE-PRINTER3D <-> SDK <-> SERVER <-> 单元安全
```

首个适配器使用 Moonraker 的 `/printer/info` 就绪响应。只有 `ready` 映射为
空闲打印机。启动、关机和错误状态均默认安全拒绝；不得围绕未就绪的打印机
规划机器人作业。

## 构建与测试

Windows 运行 `build-test.bat`，Linux 运行 `bash build-test.sh`。脚本会编译并
测试响应解析器和安全门，不发送 G-code、不更改版本，也不接触打印机。真实
命令需要经过验证的配置、身份验证和物理安全审查。

## 相关项目

| 项目 | 作用 |
| --- | --- |
| [HYDRA-UMC-SDK](https://github.com/JuanenRac/HYDRA-UMC-SDK) | 共享契约。 |
| [HYDRA-UMC-SERVER](https://github.com/JuanenRac/HYDRA-UMC-SERVER) | 已授权的协调端点。 |
| [HYDRA-UMC-SAFETY-ZONES](https://github.com/JuanenRac/HYDRA-UMC-SAFETY-ZONES) | 未来的工作区证据。 |

## 状态

版本 `0.0.1` 包含本地、已测试的 Moonraker 就绪状态适配器。它尚未控制真实的
打印机、热端或机器人。
