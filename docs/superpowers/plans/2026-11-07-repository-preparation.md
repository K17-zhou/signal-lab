# Repository Preparation Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans for the repository and README work. Evidence curation may run independently under superpowers:dispatching-parallel-agents.

**Goal:** 准备 K17-zhou 的 GitHub 评审仓库，完善安装与启动指南，并在用户指定的 `测试` 空目录完成同机复现。

**Architecture:** 沿用冻结版应用、计算、学习和本地模型接口。仓库收录源码、依赖锁和可审查的开发证据。模型、运行包及大体积成片由完整作品包提供。README 给出两条实际可用的准备路径。

**Tech Stack:** Git、PowerShell 7、Python 3.13.13、Node.js 24.16.0、llama.cpp b11814、Qwen3.5-4B Q4_K_M、既有 pytest/Vitest/Playwright。

**Spec:** [项目基线](../specs/2026-11-03-signal-lab-design.md) 以及用户 11 月 7 日的仓库、README、本机复现与证据准备指令。

## Global Constraints

- 所有新产物保存在传智杯项目内。
- 干净复现使用项目根目录下的 `测试`。
- 使用 GitHub 账号 `K17-zhou`，保留真实细粒度开发提交。
- Python 项目声明 ≥3.12，Node.js 构建要求 ≥22.12。复现结论按本轮实际版本记录。
- 模型路径、长度、SHA-256、回环监听和运行编号校验沿用现有约束。
- 新材料引用真实原文、运行和测试记录。
- 真人学习效果继续记录为未测。正式参赛提交留在后续排期。

## Review Focus

1. 首次拿到源码的人能否定位项目根目录并装好锁定依赖。
2. 源码路径与完整包的模型、运行器目录能否按文档准备。
3. 两个终端中的模型端口和别名是否匹配，失败是否能按指南定位。
4. 本地测试复制是否带入原虚拟环境、依赖目录或正式学习数据。
5. 上传分支是否只携带真实可达历史与审核材料，大文件是否留在作品包。

## Tasks

- [ ] 完善 README 和仓库忽略规则，说明下载、安装、普通实验、本地 AI、验证与排错。
- [ ] 审核可达 Git 历史大小和敏感信息，准备 GitHub 仓库与细粒度历史。
- [ ] 将更新提交独立克隆到 `测试`，新建依赖环境，按 README 实测标准案例和真实指导。
- [ ] 强化三条开发链的已批准上下文与实际模型输入，更新视频、文档及作品包。
- [ ] 核对 C 主流程的科学事实、引用归属、对照和保存恢复，保留 B 的原始比较记录。
- [ ] 完成同版回归、材料校验、GitHub 推送及可访问性检查，保存接续记录。
