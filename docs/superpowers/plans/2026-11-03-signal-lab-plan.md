# 信号实验工坊 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在2026-11-16前交付可复现、有真实AI指导和验证材料的通信原理交互实验作品，参加11月18日截止的传智杯省赛。

**Architecture:** Python实验引擎输出真实计算结果，React前端负责交互与学习流程；模型通过后端获取运行证据、解释误区并建议合法参数。计算、判题和学习记录独立于模型，SQLite保存运行及匿名会话。

**Tech Stack:** React、TypeScript、Vite、ECharts；Python 3.12、FastAPI、Pydantic、NumPy、SciPy、SQLite；pytest、Vitest、Playwright。

**Spec:** [省赛版本设计基线](../specs/2026-11-03-signal-lab-design.md)。功能、工时和目标指标为计划基线；实际完成情况以下面的执行状态和对应证据为准，未测的成绩不记为成果。

**执行状态（2026-11-06）** Task 1 至 Task 5 已完成。Task 6 的分组软件、题组、冻结用例、统计和浏览器验收已就绪，真人试用待开展。 [最新进度](../../progress/2026-11-06.md)

## 你的排期与今晚任务

已确认：周五至周一全天，周二至周四晚间1–2小时。全天按6小时有效工作估算，至11月16日约54–60小时；11月17日晚另留1–2小时缓冲。所有日期和时间均为北京时间。

工时基线：P0核心开发22小时、用例与试用7小时、复现修复12小时、材料10小时、机动2小时，共53小时。P1滤波最多加4小时；正常进度总计57小时，投入偏低或任何核心任务超时则舍弃P1。正式真人评估只比较同一程序B/C两个模式，静态仿真A作为功能基线说明。

**今晚11月3日的必达目标：能运行首批采样标准案例，并保存第一次真实开发记录。**

| 顺序 | 预算 | 今晚做什么 | 结束时看到什么 |
| --- | --- | --- | --- |
| 1 | 10分钟 | 阅读并确认本计划范围，开始保存AI原始对话和决策记录 | 题目、P0范围和证据目录明确 |
| 2 | 20分钟 | 建立最小Git/Python环境，记录版本，加入密钥和运行数据忽略规则 | 仓库和测试入口可用 |
| 3 | 45分钟 | 写标准S1–S3测试，再实现采样状态和折叠频率计算 | 50/400→50Hz；70/100→30Hz；50/100→边界警告 |
| 4 | 15分钟 | 运行测试、保存真实输出和对应Prompt，做一次有意义的commit | 本次修改和验证能追溯 |
| 加做 | 余下30分钟 | 补采样点或频谱计算，或者整理最小绘图页面 | 不影响前三个标准案例 |

只有1小时就完成前两项和S1–S2，未完成项留到11月4日；不得把未运行的案例记成通过。今晚不以完整界面或聊天接入为验收条件。

## 日期安排

| 日期 | 可用时间 | 主要交付 | 当日验收 |
| --- | --- | --- | --- |
| 11/3 周二 | 晚间1–2h | 最小工程、首批采样案例、开发记录 | S1–S3状态与折叠频率；不足时按今晚缩减方案 |
| 11/4 周三 | 晚间1–2h | 频谱、周期重建和数值边界 | S1重建、S2混叠、S3退化均符合设计 |
| 11/5 周四 | 晚间1–2h | 后端运行接口与最小绘图页面 | 输入参数能返回一次真实运行并画图 |
| 11/6 周五 | 全天，约6h | 主实验界面、案例与学习记录 | 调参、比较、预测、导出走通 |
| 11/7 周六 | 全天，约6h | 真实模型、结果引用与误区反馈 | 至少一次真实API调用；错误引用被拒绝 |
| 11/8 周日 | 全天，约6h | 预测→实验→纠错→迁移题完整流程 | P0用户流程通过；建立首版验证用例 |
| 11/9 周一 | 全天，约6h | P0查漏与数值复核；满足条件才做滤波扩展 | 主流程无已知科学错误，导出可审查 |
| 11/10 周二 | 晚间1–2h | 小规模试用与问题归档 | 记录真实用户遇到的问题；邀请由用户安排 |
| 11/11 周三 | 晚间1–2h | 修复关键问题，补同难度对照题 | 复现问题、修复和回归记录齐全 |
| 11/12 周四 | 晚间1–2h | 统计已取得的结果、确定视频故事线 | 功能冻结；无数据的指标明确标为未测 |
| 11/13 周五 | 全天，约6h | 留出案例、独立复现和关键修复 | 新目录复现有真实计时记录 |
| 11/14 周六 | 全天，约6h | 交互、错误状态、试用记录与成果图表 | 标准完整流程稳定，结果与证据对应 |
| 11/15 周日 | 全天，约6h | 视频、PDF、README和仓库评审访问 | 5–8分钟视频，PDF≤30页，至少3条开发链 |
| 11/16 周一 | 全天，约6h | 最终核对、材料上传与用户正式提交 | 计划当天提交并保存成功回执 |
| 11/17 周二 | 晚间1–2h | 链接与回执复查，处理允许的更正 | 不重复提交；更正遵循组委会流程 |
| 11/18 周三 | 官方15:00截止 | 不安排首次提交或新增开发 | 截止前应已完成提交 |

**范围控制：** P0是一条完整学习流程；P1滤波最多占用11月9日中的4小时。11月8日P0未走通就延期P1；11月12日后只修复、验证和整理材料。

## Global Constraints

- f0取5–200的整数Hz，fs取20–1000的整数Hz，A取0.1–2，phase取[-pi, pi]，时长固定1秒。
- 参考网格4096点，采样时刻n/fs，n=0..fs-1。直接计算这些时刻的原信号，不能用带抗混叠滤波的降采样函数代替欠采样。
- 样本RMS<1e-8时标记DEGENERATE_SAMPLES，频谱实测主峰返回null，避免把浮点噪声解释为真实主峰。
- fs>2*f0标记well_sampled；fs<2*f0标记undersampled；相等标记nyquist_boundary。边界不能直接宣称可无损重建。
- 省赛只允许sampling_aliasing、lowpass_filter两种结构化实验；不执行模型生成的任意Python、JS或shell代码。
- 模型超时30秒，显示明确失败状态，实验计算仍可用。
- 计算指标由程序渲染，AI输出不能覆盖数值结果、标准答案或原始学习记录。
- 官方省赛最终截止：2026-11-18 15:00；内部计划2026-11-16完成首次正式提交，11月17日晚留作检查或获准更正。

## Review Focus

1. 奈奎斯特边界或全零采样被解释成成功重建：任务1用S3/S4钉住。
2. 快速连续调参后，旧请求覆盖新结果或引用错run_id：任务2、4、6验证。
3. 模型超时、返回非JSON或越界参数，被静默替换成成功演示：任务4验证明确失败和实验仍可用。
4. 刷新或模型重试覆盖原始预测、重复计入一次作答：任务3以event_id幂等验证。
5. 周期模型被外推到任意实测信号、对照题答案泄漏给指导模型：任务1、4、6核验假设展示、请求上下文和留出集。

## 文件结构与公共接口

以下是未来执行时创建的路径，本次没有创建这些产品文件。共享类型以设计基线第5节为准。

| 路径 | 职责 |
| --- | --- |
| backend/app/main.py | FastAPI装配与路由 |
| backend/app/schemas.py | 设计基线中的请求、结果、证据及学习事件类型 |
| backend/app/experiments/sampling.py | 采样、频谱、周期重建与警告 |
| backend/app/experiments/filtering.py | P1低通滤波 |
| backend/app/experiments/runner.py | run_experiment(request: ExperimentRequest) -> ExperimentRun |
| backend/app/store.py | Store.put_run(run), get_run(run_id), append_event(event), list_events(session_id) |
| backend/app/tutor/client.py | TutorClient.complete(context: dict) -> str，真实模型适配 |
| backend/app/tutor/service.py | guide(request: TutorRequest) -> TutorReply及证据校验 |
| frontend/src/api.ts | 类型化API请求与错误处理 |
| frontend/src/features/lab/ | 参数、波形、频谱、运行比较 |
| frontend/src/features/learning/ | 预测、步骤、迁移题、记录导出 |
| frontend/src/features/tutor/ | 指导内容、证据跳转、建议参数确认 |
| content/cases.json | 公开学习案例；不放留出题答案 |
| backend/content/assessment_keys.json | 服务端判题及留出题答案；不随前端打包 |
| evaluation/ | 用例清单、对照配置、匿名原始结果和分析 |
| evidence/ai-development/ | 原始AI交互、commit映射、实际验证记录 |
| deliverables/ | 与最终源码版本对应的文档、视频及材料索引 |

LearningEvent含event_id字符串；同一event_id重复写入只计一次。Store.get_run返回ExperimentRun或null；Store.list_events返回LearningEvent列表。TutorReply.next_experiment仅为建议，用户确认后运行接口才产生新run_id；禁止把建议当作已执行结果。

AssessmentAnswer固定为choice(option_id)或numeric(value, unit)；ScoreResult包含correct、misconception_code、explanation_key。频率数值题容差0.5Hz，P1增益题容差0.02；反思文字不自动判分。评估B/C以同一程序的模式开关实现，两者都可获得当前参数与真实指标，模型与调用限制相同，C使用结构化建议和证据引用。

## Task 1: 可核验的采样实验引擎（11/3–11/4，约3小时）

**Files:** 创建backend/pyproject.toml、backend/app/schemas.py、backend/app/experiments/sampling.py、backend/app/experiments/runner.py、backend/tests/test_sampling.py、.gitignore；开始evidence/ai-development/index.md。

**Interfaces:** 消费SamplingParams；产生run_experiment(request: ExperimentRequest) -> ExperimentRun，采样指标包含alias_frequency_hz、sampling_state、sample_rms、peak_frequency_hz、reconstruction_rmse。

- [x] 写失败测试test_safe_sampling_reconstructs：50/400→50Hz，状态well_sampled，RMSE<1e-10。
- [x] 写test_aliases_70hz_to_negative_30hz：70/100→30Hz，重建等于负30Hz正弦，较原信号RMSE与1之差<1e-10。
- [x] 写test_nyquist_zero_samples：50/100、phase=0，边界与DEGENERATE_SAMPLES同时成立，实测主峰null；补100/100的S4区分用例。
- [x] 从backend运行python -m pytest tests/test_sampling.py -q，确认先出现缺少实现的失败。
- [x] 实现请求范围、解析采样、单边谱与周期重建；按SciPy文档处理DC/Nyquist系数和周期假设；建立实际依赖锁定。
- [x] 重跑同一测试，预期全部通过；将实际输出、失败修复过程和对应commit记录到证据索引。

## Task 2: 真实运行API与交互实验页面（11/5–11/6，约6小时）

**Files:** 创建backend/app/main.py、backend/app/store.py、backend/tests/test_runs_api.py、frontend/package.json、frontend/src/api.ts、frontend/src/features/lab/LabPage.tsx、frontend/src/features/lab/plots.ts；测试frontend/src/features/lab/LabPage.test.tsx。

**Interfaces:** 消费Task 1的ExperimentRequest/ExperimentRun；产生POST /api/experiments/run、Store.put_run/get_run，以及LabPage显示真实run_id与科学边界说明。

- [x] 写API失败测试：合法请求返回200及可查run_id，越界/NaN/未知experiment_type返回422，P1未启用时明确拒绝。
- [x] 写前端异步顺序测试：先发A后发B，B先完成、A后完成，最终仍显示B的run_id和参数。
- [x] 分别运行backend的python -m pytest tests/test_runs_api.py -q、frontend的npm run test -- --run，确认目标测试先失败。
- [x] 实现SQLite运行保存、接口、参数调整及曲线绘制；参考线、采样点、频谱和重建曲线使用同一运行结果；最新请求优先。
- [x] 重跑测试并在浏览器完成S1/S2/S3切换，确认轴单位、边界说明和数据同步；记录实际截图和错误修复。
- [x] 提交这一可运行实验版本，保存对应AI对话与验证结果。

## Task 3: 预测、迁移题和真实记录（11/6余时–11/7前半，约5小时）

**Files:** 创建content/cases.json、backend/content/assessment_keys.json、backend/app/learning.py、backend/tests/test_learning.py、frontend/src/features/learning/LearningFlow.tsx及LearningFlow.test.tsx；修改schemas.py、store.py、main.py。

**Interfaces:** 消费实验run_id；产生LearningEvent(event_id+设计字段)、POST /api/events、GET /api/sessions/{id}/export?format=json或csv；score_answer(case_id: str, answer: AssessmentAnswer) -> ScoreResult执行客观判题。

- [x] 写失败测试，覆盖事件重发、原预测恢复、新参数迁移题和公开题库的字段边界。
- [x] 写判题边界断言，覆盖选项编号、30.5与30.6Hz、非法单位及不自动判分的观察记录。
- [x] 写导出断言，覆盖会话隔离、运行编号、答案、耗时、失败及中文换行。
- [x] 运行后端及前端目标测试，分别保存9项与3项初次失败。
- [x] 实现学习步骤、六类案例、服务端判题、记录恢复和导出，正式作答追加保存。
- [x] 重跑测试，浏览器完成一次新会话并核对迁移题和两种导出。修复小屏阅读顺序及审查发现。
- [x] 保存本地提交与真实开发证据。 [Task 3开发记录](../../../evidence/ai-development/2026-11-04-guided-learning.md)

## Task 4: 真实AI指导与证据引用（11/7后半–11/8，约8小时）

**Files:** 创建backend/app/tutor/client.py、backend/app/tutor/service.py、backend/tests/test_tutor.py、frontend/src/features/tutor/TutorPanel.tsx及TutorPanel.test.tsx、.env.example；修改main.py与学习流程。

**Interfaces:** 消费Store.get_run、TutorRequest和真实运行；产生TutorClient.complete(context: dict) -> str、guide(request) -> TutorReply、validate_evidence(reply, run) -> bool和POST /api/tutor/guide。

- [x] 测试错误运行编号、未知字段、非 JSON、非法建议参数和超时。
- [x] 测试模型上下文隔离，并区分原预测题参数和当前运行参数。
- [x] 保存固定响应测试初次失败及后续通过的记录。
- [x] 按用户最终选择接入本机 llama.cpp 与 Qwen3.5-4B Q4_K_M。启动时校验文件。
- [x] 实现证据跳转、参数确认和失败提示，确认后生成独立对照运行并保留已有预测。
- [x] 重跑自动测试，再用真实模型跑至少10条指导请求并人工核对，记录配置、耗时、失败和修复。 [真机记录](../../../evidence/ai-development/2026-11-05-tutor-real.md)
- [x] 完成真实模型的接口级学习流程，保存证据引用错误的修复迭代链。
- [x] 从运行记录和已保存预测生成科学正文，复验模型选择、引用和对照，以及连接真实服务的 React 学习流程。 [复验记录](../../../evidence/ai-development/2026-11-05-tutor-grounded.md)
- [x] 在本地浏览器连接真实模型复验画面和滚动定位，确认对照图表更新、原预测保留和会话恢复。 [浏览器验收](../../../evidence/ai-development/2026-11-05-tutor-grounded.md#实际浏览器验收)

## Task 5: 有条件的滤波扩展（11/9，最多4小时）

**Files:** 创建backend/app/experiments/filtering.py、backend/tests/test_filtering.py；修改runner.py、schemas.py、LabPage.tsx与cases.json。

**Interfaces:** 消费FilteringParams；仍返回ExperimentRun，增加gain_20hz、gain_120hz及稳态窗口说明。

- [x] 根据 Task 4 的实际浏览器、真实模型和导出记录确认 P0 已通过。
- [x] 先写 60 Hz 截止增益和 cutoff 范围测试，另覆盖有效端点与小数参数。
- [x] 运行滤波与学习目标测试，观察到 6 个预期失败，前端入口另有 1 个预期失败。
- [x] 用四阶 Butterworth SOS 和单向 sosfilt 实现，取最后 1 秒的稳态增益，展示启动瞬态和相移。
- [x] 重跑测试并在浏览器走通滤波迁移题、刷新恢复、JSON 与 CSV 导出，以及采样学习回归。
- [x] 单独提交滤波扩展与验收证据。 [Task 5 验收记录](../../../evidence/ai-development/2026-11-05-lowpass-filtering.md)

## Task 6: 对照、留出用例与真实试用（11/8余时–11/12，约7小时）

**Files:** 创建evaluation/case_manifest.csv、evaluation/protocol.md、evaluation/assignments.csv、evaluation/raw/、evaluation/analyze.py、backend/tests/test_evaluation.py、frontend/e2e/learning-flow.spec.ts；维护evaluation/results.md；在tutor服务及前端加入B/C模式开关。

**Interfaces:** 消费Task 3导出记录；analyze(events: list[dict]) -> dict返回样本数、完成率、迁移题正确数、耗时分布及失败计数。

- [x] 冻结 30 个标注用例，包含 20 个数值与边界、10 个指导与交互，以及其中 10 个留出案例。保留标注依据与版本。
- [x] 冻结 X/Y 两套匹配题组，各有 3 项任务与 3 道新参数迁移题。
- [x] 先写分析测试并观察预期失败，再实现分析脚本。零真人显示「未测」，失败和退出保留在分母，重复事件去重，合成记录与真人结果分开。
- [x] Playwright 实测参数切换、预测与实验、两种指导、迁移题、刷新恢复、超时和导出。
- [x] 预分配 B-X→C-Y、C-X→B-Y、B-Y→C-X、C-Y→B-X 四种顺序。两组共用实测参数、指标、模型配置和调用预算。
- [x] 分配表锁定会话条件和题组。B 包装普通文本，C 校验证据和建议对照，记录调用结果与耗时。
- [x] 统计状态区分「未测」「仅定性」「描述性比较」，保存分析命令和合成验收证据。 [试用方案与状态](../../../evaluation/protocol.md)
- [ ] 用户邀请 2–3 名学生先试跑，再按方案安排正式学生和教师体验，保存匿名记录和实际反馈。
- [ ] 收到真实记录后生成相应口径的结果摘要。

## Task 7: 独立复现与交互打磨（11/13–11/14，约12小时）

**Files:** 创建README.md、scripts/start.ps1、scripts/check.ps1、evaluation/reproduction.md；更新测试和已有功能文件。

**Interfaces:** 在已声明的Python/Node前提下，start.ps1启动后端和前端；check.ps1运行后端测试、前端测试、构建及主要浏览器流程，并根据失败返回非零退出码。

- [ ] 执行冻结的留出案例，记录真实失败；对修复项先补能复现问题的测试，再做针对性修复。
- [ ] 使用新的目录或另一台环境按README获取源码、安装依赖、配置变量、启动标准案例，全程计时；目标10分钟，记录所有必要步骤耗时。
- [ ] 核查模型不可用、空会话、网络中断、未知run_id和连续调参；界面保持结果归属清楚，失败不会被成功提示覆盖。
- [ ] 前端执行npm run test -- --run、npm run build、npx playwright test；后端执行python -m pytest -q，确认实际输出。
- [ ] 只在新修改或失败出现后补充或重跑相关验证；核对桌面常用窗口尺寸下的图表、单位、按钮和证据定位。
- [ ] 冻结可交付版本，记录commit、实际依赖版本、已知限制、实测耗时和截图；保存最终缺陷清单。

## Task 8: 参赛材料与提交（11/15–11/16，材料约10小时，缓冲2小时）

**Files:** 创建deliverables/作品说明.md、deliverables/技术文档提纲.md、deliverables/视频脚本.md、deliverables/提交清单.md；完成最终PDF、MP4及证据索引。

**Interfaces:** 消费冻结版本、真实评估结果、开发证据；生成材料版本与源码commit的一一对应索引。

- [ ] 汇总至少3个核心AI开发链：完整原始交互、关键修改、失败及修复、实际测试、对应commit；检查截图中的凭据和私人信息。
- [ ] 写不超过30页的技术PDF，覆盖问题、同类差异、架构、意图控制、科学假设、验证、实际结果及限制；按页渲染检查图表、引用和文字。
- [ ] 录制5–8分钟1080p MP4，至少2分钟真实AI协同开发过程；功能展示、数据与技术文档对应同一冻结版本。
- [ ] 测试仓库评审权限、完整作品网盘、单独介绍文档和公开视频链接；用未登录视角检查可访问性。
- [ ] 用户在11月16日按实际表单完成正式提交，保存成功回执、提交时间、材料链接及版本；此项不是本次已完成的操作。
- [ ] 11月17日晚复查链接和回执；如需更正，遵循组委会允许的流程，避免在“一人一次”的表单上擅自重复提交。

## 晋级后的国赛深化路线

| 时间 | 深化重点 | 证据要求 |
| --- | --- | --- |
| 11/19–11/30 | 根据省赛反馈和真实错误扩展教学案例、抗混叠对照或量化实验 | 新案例标准答案、修复对照、版本记录 |
| 12/1–12/10 | 如选择硬件拓展，接入一种实测信号链路并记录校准、采样率和误差 | 原始采集数据、设置、与仿真对照；设备与预算再确认 |
| 12/11–12/20 | 扩大学生试用，做静态指导/普通聊天/本产品的公平对照 | 匿名原始数据、分配方法、失败记录和限制 |
| 12/21–12/24 | 冻结版本，更新文档、视频与复现包 | 与最终commit一致的完整材料 |
| 12/25 | 内部计划提交国赛，留补传缓冲 | 以晋级后的正式通知重核截止及流程 |

国赛目前暂按官网12月27日提交截止安排，需在晋级后核对正式通知；上述是深化计划，不代表已晋级或已取得效果。

## 主要取舍与计划自检

- 科学正确性、真实AI、完整学习流程、开发证据和提交材料先于增加实验数量。
- 若11月8日P0未完成，延期P1；若11月12日真人数据不足，保留真实样本量和限制，不编造效果。
- 硬件可采购；是否接入以及何时购买，在测量目标和接口确定后决定，不把设备采购数量作为成果。
- 所有开发任务有明确文件、公共接口、失败测试和验收方式；Review Focus中的五项分别归入任务1/2/3/4/6。
- 任务勾选、测试通过、真人数量、复现耗时、上传及回执仅按执行时的实际证据更新。
- 实施建议在当前聊天逐项执行，便于追踪这一紧密相连的核心流程。当前交付到计划阶段，实施时再按用户的开始指令进入任务1。

设计独立审阅已完成：客观题型与容差、B/C题组分配、53小时P0预算和削减规则均已修订，复核未发现重要缺口。这是对文档可执行性的审阅，不是产品功能或教学效果已经验证。

规则来源：[官方赛道](https://www.boxuegu.com/matchTrack/detail/?id=10039)、[个人流程](https://xuexi.boxuegu.com/matchProcess/?id=160136)、[最终提交表](https://f.kdocs.cn/g/CZ14BoMv/)。技术来源和边界见设计基线第8节。
