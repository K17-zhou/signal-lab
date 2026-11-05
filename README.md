# 信号实验工坊

面向通信原理学习的交互实验项目，支持自由实验和引导学习。

## 当前能做什么

- 运行一秒周期正弦信号的采样、混叠、单边幅度谱和周期重建。
- 在网页切换四个标准案例、调整参数、对照波形与频谱，导出当前运行JSON。
- 在引导学习中完成六组采样练习，依次保存预测、运行实验和提交新参数迁移题。迁移题由服务端判分。
- 在实验运行后请求本地模型指导。可点按反馈引用跳回本次运行的实测数据，确认建议参数后生成单独的对照运行。
- 在同一标签页刷新后恢复已保存的学习进度。观察记录、耗时、真实运行及判题结果可导出为JSON和CSV。
- 将成功运行追加保存到SQLite，并按运行编号查询；快速切换时仅显示最新请求结果。
- 区分正常采样、欠采样、奈奎斯特边界、采样全零等退化情况。
- 导出S1–S4的真实计算结果、运行编号、参数、指标和曲线数据。
- 拒绝范围外、非有限、错误类型和未知实验请求。

## Windows运行

本轮实测Python 3.13.13、Node.js v24.16.0。项目声明Python>=3.12，但其他Python版本尚未实测；前端构建需要Node>=22.12（当前依赖要求）。

在项目根目录的PowerShell中执行：

```powershell
# 使用项目内临时目录，适用于本次沙箱默认TEMP不可写的情况。
New-Item -ItemType Directory -Force .cache/tmp | Out-Null
$env:TEMP = (Resolve-Path .cache/tmp).Path
$env:TMP = $env:TEMP
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r .\backend\requirements.lock.txt

Push-Location frontend
npm.cmd ci
Pop-Location
.\scripts\start.ps1
```

打开[本机实验页面](http://127.0.0.1:8000)。脚本先构建前端，再启动同源API和网页，按Ctrl+C停止。已构建后可用`.\scripts\start.ps1 -SkipBuild`；端口占用时加`-Port 8001`。仅监听本机，不需要模型密钥。开发时可在backend启动Uvicorn，在frontend运行`npm.cmd run dev`，Vite会把`/api`转发到8000端口。

验证与命令行案例导出：

```powershell
Push-Location backend
..\.venv\Scripts\python.exe -m pytest -q
..\.venv\Scripts\python.exe -m app.demo --output ..\artifacts\sampling-foundation
Pop-Location
Push-Location frontend
npm.cmd run test -- --run
npm.cmd run build
Pop-Location
```

已有.venv时可跳过环境创建。导出命令要求输出目录尚不存在，避免覆盖已有证据；再次运行请换一个目录名。

`artifacts/sampling-foundation/summary.json`是指标摘要；S1.json到S4.json包含完整曲线数据。这些是解析周期模型的计算结果，不是真人学习效果或硬件测量。

运行和学习记录默认保存在项目内`.cache/signal-lab.sqlite3`，可通过`SIGNAL_LAB_DB_PATH`指定其他路径。`POST /api/experiments/run`接受`experiment_type: "sampling_aliasing"`及`params`，`GET /api/experiments/{run_id}`取回同一记录。自由实验刷新时会生成一次默认运行。[API文档](http://127.0.0.1:8000/docs)

进入引导学习后选择案例，填写预测并保存，再运行本题实验。可记录观察并完成迁移题。顶部的JSON和CSV链接导出当前会话全部案例的记录。浏览器在同一标签页保存匿名会话编号，新建会话会从空进度开始。[打开引导学习](http://127.0.0.1:8000/#learn)

学习接口包括`GET /api/learning/cases`读取题面，`POST /api/events`写入学习事件，`GET /api/sessions/{id}/events`恢复进度，以及`GET /api/sessions/{id}/export?format=json`或`format=csv`导出。同一事件编号和内容重发时返回原记录，冲突提交返回HTTP 409。

## 本地 AI 指导

本项目使用便携版 llama.cpp，默认加载 Qwen3.5-4B 的 Q4_K_M 权重。配置为 2048 token 上下文、单并发、4 个 CPU 线程和关闭思考模式，推理服务默认监听 `127.0.0.1:8081`。 [llama.cpp 接口](https://github.com/ggml-org/llama.cpp/blob/b11814/tools/server/README.md)

1. 将 Windows Vulkan 版 llama.cpp b11814 解压到 `.cache/runtimes/llama-b11814/`，使 `llama-server.exe` 位于该目录下。本机项目的便携运行器已就绪。 [运行包](https://github.com/ggml-org/llama.cpp/releases/download/b11814/llama-b11814-bin-win-vulkan-x64.zip)
2. 将默认权重放在 `model/Qwen3.5-4B-Q4_K_M.gguf`，启动时会校验长度和 SHA-256。 [Qwen3.5-4B 固定权重](https://huggingface.co/unsloth/Qwen3.5-4B-GGUF/blob/e87f176479d0855a907a41277aca2f8ee7a09523/Qwen3.5-4B-Q4_K_M.gguf)
3. 在项目根目录运行启动脚本。可用 `-ModelPath` 指定绝对路径或相对项目根目录的路径，也可用 `-Cpu` 选择 CPU。脚本仍接受两种已登记的旧版 Q4_K_M 权重。 [Qwen3-4B-Instruct-2507](https://huggingface.co/unsloth/Qwen3-4B-Instruct-2507-GGUF/blob/a06e946bb6b655725eafa393f4a9745d460374c9/Qwen3-4B-Instruct-2507-Q4_K_M.gguf) · [Qwen3-1.7B](https://huggingface.co/ggml-org/Qwen3-1.7B-GGUF/blob/daeb8e2d528a760970442092f6bf1e55c3b659eb/Qwen3-1.7B-Q4_K_M.gguf)

```powershell
.\scripts\start-tutor.ps1
```

另开一个项目目录终端启动 `.\scripts\start.ps1`，完成一次预测和实验后点击“获取 AI 指导”。本地模型选择观察重点、引用字段和对照参数，程序根据实验记录和已保存预测生成科学说明。应用和模型服务默认使用统一别名 `signal-lab-tutor`。更改模型端口时，在应用终端设置 `SIGNAL_LAB_TUTOR_PORT` 与 `-Port` 一致。使用自定义别名时，在两个终端设置同一 `SIGNAL_LAB_TUTOR_MODEL`。

## 标准案例与限制

| 案例 | 原频率 / 采样率 | 应观察到的结果 |
| --- | --- | --- |
| S1 | 50Hz / 400Hz | 50Hz，无混叠，周期重建RMSE小于1e-10 |
| S2 | 70Hz / 100Hz | 观测30Hz混叠，重建为负30Hz正弦；不能宣称恢复原70Hz信号 |
| S3 | 50Hz / 100Hz，初相位0 | 奈奎斯特边界，样本几乎全零，实测主峰为null |
| S4 | 100Hz / 100Hz，初相位0 | 欠采样折叠到DC、样本退化；不属于奈奎斯特边界 |

- 当前只支持整数频率、整数采样率和固定1秒周期模型；参数范围见[设计基线](docs/superpowers/specs/2026-11-03-signal-lab-design.md)。
- Fourier重建具有周期假设；不推广为任意真实信号的完美恢复。
- 欠采样直接在原信号上取样，不经过会抑制混叠的降采样滤波器。
- 同一参数得到同一数值结果，每次运行编号不同。数值正确不等同教学效果已验证。
- 本地指导通过本机模型服务运行。真实模型验收记录将补充在开发证据中。

## 文档与证据

- [最新进度与接续入口](docs/progress/2026-11-05.md)
- [执行计划](docs/superpowers/plans/2026-11-03-signal-lab-plan.md)
- [设计基线](docs/superpowers/specs/2026-11-03-signal-lab-design.md)
- [AI开发证据索引](evidence/ai-development/index.md)
- [网页与API实际开发记录](evidence/ai-development/2026-11-03-interactive-lab.md)
- [引导学习与判题开发记录](evidence/ai-development/2026-11-04-guided-learning.md)
- [本地 AI 科学正文与交互验收](evidence/ai-development/2026-11-05-tutor-grounded.md)
- 本地测试环境以backend/requirements.lock.txt锁定；.venv、临时缓存、导出的大数组不进入Git。
