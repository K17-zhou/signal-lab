# Delivery Defect Fixes Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans. Independent tutor and portable-runtime work may use superpowers:dispatching-parallel-agents with exclusive file ownership.

**Goal:** 完成用户已经确认的教学对照、快速复现、视频展示与发布缺口。

**Architecture:** 沿用现有前后端和本地模型，增加服务端对照验算、独立便携启动器与交付流程。发布源代码保留增量提交，视频与大包独立版本化。

**Tech Stack:** FastAPI、NumPy/SciPy、pytest、Windows CPython 3.13.13 embedded、现有 React 构建、Playwright、ffmpeg、B站、百度网盘。

**Spec:** [已授权修复设计](../specs/2026-11-07-delivery-defect-fixes-design.md)

## Global Constraints

- 所有文件、运行缓存和测试副本留在传智杯项目目录。
- 使用既有工作分支与环境，保留已公开的历史、v1.1 与冻结输入。
- 不改判题标准，不向模型泄漏迁移参数或答案，不虚构模型建议。
- 视频重放明确标注；正式赛事表单、真人与异机测试不在本轮执行。

## Review Focus

- 合法参数但无法达到目标的边界建议应被抑制，有意义的相位对照应可保留。
- 模型建议不能通过改变原信号或直接使用迁移题参数获得虚假的正确结果。
- 便携包在含空格/中文的新目录及隔离 PATH 下能够启动，未复制主项目虚拟环境。
- 已占用端口、损坏资源和启动失败不影响其他进程，子进程可收尾。
- 视频实际内容、发布时间与包内源码、图表及测试数字分别可核对。

## Tasks

- [x] 对照教学目的修复。修改 `backend/app/tutor/service.py` 与 `client.py`，在 `backend/tests/test_tutor_comparison.py` 先复现140Hz误导性建议，再验证过滤、有效恢复、相位对照、跨类型和迁移隔离。保存真实红/绿日志，相关测试与全量回归通过。
- [x] 便携运行环境。新增 `scripts/portable.py`、`scripts/build_portable.py` 和 `开始演示.cmd`。验证固定资源、锁版本、端口冲突、ZIP安全与进程收尾，使用官方嵌入式 Python 实测 S1 与真实模型指导。
- [x] 连续实操视频。记录真实浏览器操作和超过2分钟的修复过程复现，配音与版本标注一致；核验完整解码、分辨率、时长与关键画面。
- [x] 新版材料与完整包。更新 README、技术文档、介绍、脚本、验收结果及来源。冻结发布提交并生成便携完整 ZIP，逐项校验，在 `测试` 下新目录从最终 ZIP 实测并分别记录下载/解压/启动/功能耗时。
- [ ] 发布与接续。将新源码和文档推送 GitHub，上传 B站与百度网盘，核对实际分享与播放结果，保留URL、版本和接续记录。登录或平台审核等外部状态按实际记录。

## 用户要求暂停时的状态

11月8日继续后，最终ZIP3938成员的SHA/CRC及独立解压功能验证已通过；校验与解压28.446秒，启动至READY49.138秒，累计134.403秒完成功能核验。默认Vulkan同机通过，CPU真实指导未通过的原始失败保留。16项启动器测试通过。新版视频431.059秒，开发复现连续跨度162.281秒；两份PDF9页/1页已渲染检查。GitHub v1.2四附件匿名下载哈希匹配，B站BV1tz4x6dE2B已审核并在正式页播放。百度完整ZIP上传和分享仍在处理，因此最后一项暂不勾选。[当前交接](../../progress/2026-11-08-delivery-handoff.md)

2026 年 11 月 7 日用户要求今天先停。教学对照修复已完成并通过155后端、16前端、生产构建和9条浏览器流程。便携运行环境与启动器已构建，12项启动器测试及私有解释器155项后端测试通过；最终完整ZIP的独立复现仍待进行，因此第二项保留未完成。视频、文档整合和发布下次继续。详见[接续记录](../../progress/2026-11-07-defect-fixes-handoff.md)。
