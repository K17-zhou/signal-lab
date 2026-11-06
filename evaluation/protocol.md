# 信号实验工坊试用方案 v1

## 对照设计

B 与 C 都使用同一版程序、同一个本地模型、实际运行参数和指标、已保存预测以及同一指导问题。B 展示普通文本，C 另外展示可定位的证据和可确认的对照参数。两组每题各有一次生成机会，超时也保存为一次尝试。重新打开会话可以查看已保存的结果。

X 和 Y 各有三项任务，依次覆盖充分采样、混叠和奈奎斯特边界。每项包含预测、运行、AI 指导、可选观察和一题采用新参数的迁移题。两套题的题型和提示一致，参数各自独立。指导步骤结束后，页面显示迁移题，服务端判分。

正式学生编号 S01 至 S12 按下列顺序循环，每人两轮，共约 20–30 分钟。主持人按照第一轮、第二轮的顺序交付链接。 [分配表](assignments.csv)

| 顺序 | 第 1 轮 | 第 2 轮 |
| --- | --- | --- |
| 1 | B-X | C-Y |
| 2 | C-X | B-Y |
| 3 | B-Y | C-X |
| 4 | C-Y | B-X |

由参赛者邀请 2–3 名同意试用的学生先走完整流程，使用 P01 至 P03。正式试用目标为 8–12 名学生。教师使用 T01，提供清晰度和可用性意见。试跑和教师反馈单列。

## 软件验收

从项目根目录进入 `frontend`，构建后运行以下命令。浏览器测试使用本机 Chrome、合成指导和独立 SQLite 库，输出放在项目内的 `.cache/qa/task6`。

```powershell
npm.cmd run build
npx.cmd --no-install playwright test e2e/learning-flow.spec.ts
```

如果 Windows 的测试运行器卡在服务回收，先在项目根目录用独立终端运行 `.\.venv\Scripts\python.exe frontend/e2e/serve_study.py`。在测试终端设 `$env:PLAYWRIGHT_REUSE_FIXTURE = '1'`，再运行同一测试命令。结束后用 Ctrl+C 停止该测试服务。两种方式都用 18082 端口和合成分配表。

## 冻结输入

- [用例清单](case_manifest.csv) 固定 20 个数值与边界用例和 10 个指导与交互用例，标有预期结果、依据与验收标准。
- N04、N06、N10、N12、N14、N16、N19、I08、I09、I10 作为 Task 7 的首次运行留出集。
- [题组](forms.json)、[服务端答案](../backend/content/study_keys.json)、分配表与用例清单的 SHA-256 保存在 [冻结校验表](frozen_inputs.sha256)。校验前将文本的 CRLF 归一为 LF。
- 试用采用分配表中的同一套模型配置。参赛者只向参与者提供当轮页面，题库和答案材料留在主持端。

## 现场操作

1. 在项目根目录用一个 PowerShell 窗口设 `$env:SIGNAL_LAB_TUTOR_MODEL = 'signal-lab-tutor'`，再启动 `.\scripts\start-tutor.ps1`。使用默认 Qwen3.5-4B Q4_K_M 权重和 Vulkan。脚本校验权重，等待 `http://127.0.0.1:8081/health` 返回 `ok`。把实际模型文件、设备、启动命令和两轮所用端口记录到项目内 `evaluation/raw/runtime.txt`，两轮共用该进程。先在独立测试数据库确认指导能返回。
2. 用另一个 PowerShell 窗口设置分配表和独立数据库，然后启动网页。两项服务仅监听本机。

   ```powershell
   $env:SIGNAL_LAB_STUDY_ASSIGNMENTS = (Resolve-Path 'evaluation/assignments.csv').Path
   $env:SIGNAL_LAB_DB_PATH = Join-Path (Resolve-Path 'evaluation/raw').Path 'study.sqlite3'
   $env:SIGNAL_LAB_TUTOR_PORT = '8081'
   $env:SIGNAL_LAB_TUTOR_MODEL = 'signal-lab-tutor'
   .\scripts\start.ps1 -Port 8000
   ```

3. 每个试用数据库由一份网页服务打开，并绑定原分配表。读取参与者的两条记录，先打开第一轮的 `http://127.0.0.1:8000/#learn?study=<session_id>`，结束后再打开第二轮。两轮统一说明为“依次完成三道题，先预测，再运行实验并查看指导，最后独立提交迁移题”。
4. 在 `evaluation/raw/attendance.csv` 登记实际开始的匿名编号，表头为 `participant_id,source,status`。真人填 `human`，状态为 `started` 或 `stopped`。用 `stopped` 记录中途结束，保留经同意留存的部分记录。模拟数据使用独立数据库。
5. 等当轮所有指导结束后，用下面的命令将已开展的每轮导出存到项目内。用分配表中的 UUID 替换示例值。指导仍在运行时，接口返回 HTTP 409，结束后再导出。观察记录只写实验现象和操作问题。

   ```powershell
   $session = '<session_id>'
   $out = Join-Path (Resolve-Path 'evaluation/raw').Path "$session.json"
   if (Test-Path -LiteralPath $out) { throw '导出文件已存在，请核对原记录。' }
   curl.exe --noproxy 127.0.0.1 -fsS "http://127.0.0.1:8000/api/sessions/$session/export?format=json" -o $out
   if ($LASTEXITCODE -ne 0) { throw '导出失败。' }
   ```

6. 可逐条将成功指导与对应运行参数、指标和理论对照，在 `evaluation/raw/feedback_audit.csv` 用 `session_id,case_id,has_numeric_error` 登记，最后一列填 `yes` 或 `no`。未审查的回复单列。

## 统计口径

在项目根目录运行 `.\.venv\Scripts\python.exe evaluation/analyze.py`。每位实际开始的正式学生在 B、C 各计三项计划任务。提交迁移题算完成，正确与错误分别计数。退出、失败和缺失导出均保留在分母，失败请求单列。各阶段耗时按已观测记录统计，模型耗时按服务器实测记录统计。

零名正式学生显示「未测」。正式学生少于 4 名时只写定性可用性观察。达到 4 名后可描述 B/C 的完成率、正确数、耗时和失败，不据小样本作普遍学习效果推断。教师和试跑反馈在 [结果页](results.md) 单列，原始导出保存在本地忽略目录。
