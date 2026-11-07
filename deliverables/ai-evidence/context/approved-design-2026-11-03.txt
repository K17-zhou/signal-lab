# 信号实验工坊：省赛版本设计基线

日期：2026-11-03。本文是计划采用的设计，尚无产品实现或实验成绩。

## 1. 已知目标与时间

- 赛事：第九届传智杯 AI创新应用挑战赛，个人赛、A组；选题对应第5方向“AI驱动的高交互教育与可视化”。
- 目标：争取省一等奖，并为国赛高奖积累真实作品与验证材料；奖项不是验收承诺。
- 用户今晚开始；周五至周一全天可投入，周二至周四晚上1–2小时。
- 官方省赛最终截止：2026-11-18 15:00；内部计划2026-11-16完成首次正式提交，11月17日晚留作检查或获准更正。
- 全天按6小时有效工作估算，至11月16日约54–60小时；这只是排期假设。P0按53小时分配：核心开发22小时、对照/用例/试用7小时、复现与修复12小时、材料10小时、缓冲2小时；P1最多另占4小时，只在实际进度允许时采用。
- 本次只交付设计和计划；尚未创建代码工程、安装依赖、调用收费API或采购设备。

## 2. 方案取舍

| 方案 | 优点 | 代价 | 本计划取舍 |
| --- | --- | --- | --- |
| 浏览器生成任意实验页面 | 扩展快、演示丰富 | 数学正确性与执行边界难控制 | 不作为省赛基线 |
| 受约束实验引擎 + AI教学指导 | 结果可验证，学习流程与计算分离 | 需要先确定实验参数和判题规则 | 采用，属于助手的技术建议 |
| 数字孪生机器人 + 实物执行 | 现场展示强 | 标定、感知、执行联调占用较多时间 | 保留后续独立候选 |

用户已要求围绕推荐方向制定计划；上述具体实现选择仍是设计建议，不记为用户已经逐项确认。

## 3. 产品与范围

对象是正在学习信号与通信基础的大学生。核心流程：预测结果 → 运行实验 → 修改参数观察 → 根据本次结果获得AI指导 → 完成一道新参数迁移题 → 导出学习记录。

### 必须交付 P0

1. 采样、混叠与周期信号重建实验：时域、采样点、频谱、重建曲线、关键指标和边界说明。
2. 预测、观察、纠错和迁移题的完整流程；至少6类预先定义的误区。
3. 一个真实模型接入；可提议修改受约束参数，服务端执行实验，解释引用对应run_id及指标。
4. 学习记录：问题、预测、参数、结果、反馈、迁移题答案、耗时及错误状态可导出JSON/CSV。
5. 至少20个独立预定的数值/边界用例、10个AI/交互用例，以及完整主要流程的浏览器验证。
6. 环境说明、细粒度Git历史、至少3条真实AI开发迭代链、演示视频、PDF技术文档、提交材料索引。

### 条件扩展 P1

低通滤波与信号失真实验。11月8日完成P0核心流程后才进入开发，最多占用11月9日中的4小时；若核心仍有科学错误、真实AI未调通或记录不可导出，直接延期该实验，不挤占验证和材料时间。

### 国赛再扩展

采样前抗混叠与采样后滤波的对照、量化误差或数字调制、更多学习评估，以及一种经过标定的实测信号接入。硬件可采购，选型和购买另行落实；不把到货作为省赛P0的前置条件。

## 4. 科学边界与标准用例

### 采样实验

- 信号 x(t)=A*sin(2*pi*f0*t+phase)。f0取5–200的整数Hz，fs取20–1000的整数Hz，A取0.1–2，phase取[-pi, pi]，时长固定1秒。
- 参考网格4096点，采样时刻n/fs，n=0..fs-1。直接计算这些时刻的原信号，不能用带抗混叠滤波的降采样函数代替欠采样。
- 频谱采用单边幅度谱；DC和偶数点数下的奈奎斯特点不乘2，其余正频率乘2/N。频率轴单位Hz。
- 折叠频率 fa=abs(((f0+fs/2) mod fs)-fs/2)，只说明观测到的等效频率，不据此宣称知道未知原信号。
- 重建采用SciPy Fourier resample到4096点；当前限定为整周期的周期信号模型。界面、导出和README说明周期假设，禁止外推为任意真实信号的完美重建。
- fs>2*f0标记well_sampled；fs<2*f0标记undersampled；相等标记nyquist_boundary。边界不能直接宣称可无损重建。
- 样本RMS<1e-8时标记DEGENERATE_SAMPLES，频谱实测主峰返回null，避免把浮点噪声解释为真实主峰。
- 标准S1：f0=50, fs=400, A=1, phase=0，折叠频率50Hz；重建与原信号RMSE<1e-10。
- 标准S2：f0=70, fs=100, A=1, phase=0，折叠频率30Hz；重建是负的30Hz正弦，较原70Hz正弦RMSE约1，绝对误差<1e-10。
- 标准S3：f0=50, fs=100, A=1, phase=0，标记奈奎斯特边界和退化采样；不得显示“恢复成功”。
- 标准S4：f0=100, fs=100, phase=0，折叠为DC、样本退化；不得误判成奈奎斯特边界。

### 滤波实验 P1

- 输入sin(2*pi*20*t)+0.5*sin(2*pi*120*t)，fs=1000Hz，时长2秒；4阶Butterworth低通，cutoff在30–200Hz内选择。
- 使用butter(..., output='sos', fs=1000)与sosfilt；不混用零相位双向滤波的幅频响应。
- 指标在最后1秒稳态窗口计算；必须标注启动瞬态和因果相移。
- cutoff=60Hz时，理论幅度增益20Hz约0.99993001、120Hz约0.05380920；稳态测量绝对误差目标<0.005。理论来自数字Butterworth公式的独立计算，不以同一次被测输出充当标准答案。

## 5. 技术建议与接口

- 前端：React、TypeScript、Vite、ECharts；Python 3.12后端：FastAPI、Pydantic、NumPy、SciPy；SQLite保存匿名会话；pytest、Vitest、Playwright验证。
- 首次开发记录实际Node LTS与各依赖版本，提交前锁定Python依赖和前端lock文件。不在此文凭空指定未经本机验证的组合。
- 模型提供商通过后端适配器接入，实施时完成凭据与费用选择；浏览器不保存或接收API密钥。模型超时30秒，显示明确失败状态，实验计算仍可用。
- 省赛只允许sampling_aliasing、lowpass_filter两种结构化实验；不执行模型生成的任意Python、JS或shell代码。

共享接口名（路径均相对项目根目录）：

| 接口/类型 | 精确定义与责任 |
| --- | --- |
| SamplingParams | frequency_hz:int, sample_rate_hz:int, amplitude:float=1, phase_rad:float=0；范围见第4节 |
| FilteringParams | cutoff_hz:float；其余信号条件固定为第4节 |
| ExperimentRequest | experiment_type + 对应params，判别联合类型 |
| PlotSeries | name, domain(time/frequency), x_unit, y_unit, x:float[], y:float[] |
| ExperimentRun | run_id, experiment_type, params, engine_version, series:PlotSeries[], metrics, warnings |
| run_experiment(request: ExperimentRequest) -> ExperimentRun | 只负责数值计算与结果装配 |
| POST /api/experiments/run | 接受ExperimentRequest，保存并返回ExperimentRun |
| AssessmentAnswer | choice型为{kind:'choice', option_id:str}；numeric型为{kind:'numeric', value:float, unit:str} |
| ScoreResult | correct:bool, misconception_code:str或null, explanation_key:str |
| TutorRequest | session_id, message, run_id, prediction:AssessmentAnswer或null, mode:'B'或'C'（默认C） |
| EvidenceRef | run_id, metric_key；允许引用该次运行的参数、指标和已登记警告 |
| TutorReply | explanation, evidence:EvidenceRef[], next_experiment:ExperimentRequest或null, misconception_code或null |
| guide(request: TutorRequest) -> TutorReply | 后端获取真实运行，调用模型并校验结构与证据引用 |
| POST /api/tutor/guide | 返回TutorReply；未知run_id返回404；模型失败返回502/504 |
| LearningEvent | event_id, session_id, case_id, stage, run_id或null, answer:AssessmentAnswer或null, elapsed_ms, outcome, timestamp；stage取predict/run/reflect/transfer/export/error |
| POST /api/events | 保存LearningEvent |
| GET /api/sessions/{id}/export?format=json或csv | 导出该会话真实记录 |
| validate_evidence(reply: TutorReply, run: ExperimentRun) -> bool | 检查引用所属run及字段存在性，不宣称能自动证明全部自然语言论述正确 |

计算指标由程序渲染，AI输出不能覆盖数值结果、标准答案或原始学习记录。对解释正确性的评测必须包含人工核对。

TutorReply.next_experiment只表示建议，用户点击确认后运行接口才产生新run_id；后续指导引用新运行。模型建议不自动改写当前参数或已记录预测。同一event_id重发只写入一次。

## 6. 学习与评估

- 误区至少包括：低频外观等于原频率、到奈奎斯特边界必然可恢复、只加插值点即可找回丢失信息、图更光滑等于更准确、采样后滤波总能消除混叠，以及忽略采样相位。
- 核心实验、标准答案与AI教学共用同一运行记录，但客观判题不交给模型自由打分。预测和迁移题只采用单选题或有限数值题：选项ID精确匹配；频率答案统一Hz且绝对误差≤0.5Hz；P1归一化幅度增益题绝对误差≤0.02。每题在题库固定题型、答案、容差和错项误区映射；正确答案的misconception_code为null。开放文字只作为反思记录，不自动判分。
- 学生题目只接收实验参数与学习目标；标准答案、误区标签和留出的迁移题答案只给服务器判题器/评估器。指导模型可读取当前已完成实验的实测结果，不读取留出题答案。
- 30个预先标注用例中20个数值/边界、10个指导/交互；至少10个案例在完成开发前保留作留出验证。标注先于正式测评，不根据测评表现修改答案。
- 试用目标8–12名学生、1名教师。邀请与联系由用户自行安排；本次没有联系任何人。
- 省赛正式比较只保留B/C两个条件，以同一产品的模式开关实现。B为同实验、同模型、同材料的普通文本指导；C增加结构化参数建议、结果引用和误区指导。B也获得本次参数与实测指标，不能故意扣除信息使对照失真。两者采用同样的预测/运行/答题步骤、模型配置和调用限制。
- B的模型文本包装为TutorReply（evidence为空、next_experiment为null），不伪造结构化引用。用evaluation/assignments.csv记录匿名participant_id、session_id、condition、form、order_index与模型配置；单次会话固定一种模式，正式试验中不切换。
- 预先准备难度匹配的X/Y两套新题，各含3个任务及3个未见参数的迁移题，均覆盖安全采样、混叠、奈奎斯特边界。按参与者依次循环分配B-X→C-Y、C-X→B-Y、B-Y→C-X、C-Y→B-X四种顺序，正式测评前冻结分配。每位参与者约20–30分钟；记录条件与题组，不重复同一道题。
- 静态仿真A仅作产品功能基线说明，不在本次工时中承诺第三组真人试验。若实际招募少于4人，仅报告定性可用性观察；其余小样本也只给描述性结果，不写已证实的教学普遍优势。
- 记录实验完成率、迁移题正确数、耗时、数值解释错误、失败次数；请求耗时和调用次数记录实测值。
- 招募不足时保留实际人数并说明限制；演示数据、自动用例和真人记录分开标注。

## 7. 参赛证据与验收

- 每个有意义的AI迭代保存原始对话/截图/录屏、对应commit、测试结果及决策说明；至少三链覆盖数值边界、AI证据引用和浏览器交互修复。
- README提供启动、依赖、变量模板、标准案例和限制；在声明的Python/Node前提下，从干净目录实测复现耗时，目标10分钟，不扣除必须的下载或配置步骤来凑数。
- 视频5–8分钟、1080p MP4，至少2分钟展示真实AI协同开发；技术PDF不超过30页。
- 完整作品网盘链接、单独作品介绍文档、可公开观看的视频链接按实际表单要求准备。正式提交由用户操作，并保存成功回执；表单写明每人仅提交一次，需更正时先核对允许的流程。
- 省赛完成要求：P0全部成立、无已知科学错误、真实模型可用、失败状态清楚、另一环境可复现、仓库可评审、视频与PDF对应实际版本。

## 8. 来源与证据边界

- [官方赛道规则](https://www.boxuegu.com/matchTrack/detail/?id=10039)
- [个人参赛流程](https://xuexi.boxuegu.com/matchProcess/?id=160136)
- [省赛最终提交表](https://f.kdocs.cn/g/CZ14BoMv/)
- [SciPy rfft](https://docs.scipy.org/doc/scipy/reference/generated/scipy.fft.rfft.html)
- [SciPy resample及周期假设](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.resample.html)
- [SciPy Butterworth与SOS建议](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.butter.html)
- [SciPy sosfilt](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.sosfilt.html)
- [PhET教学研究](https://phet.colorado.edu/en/research)、[Wokwi AI仿真](https://docs.wokwi.com/wokwi-ci/mcp-support)用于识别已有能力，不作为本作品教学效果或原创首创的证明。

以上网页已在本次会话中读取。官方页面部分日期及奖项比例有冲突；省赛最终截止采用个人流程与实际表单一致的11月18日15:00；国赛暂按详情页12月27日，晋级后再核对正式通知。
