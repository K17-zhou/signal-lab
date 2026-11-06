# Task 7 独立目录复现与交互验收

2026 年 11 月 6 日在同一台 Windows 11 26H2 电脑上建了两个空目录，从本地 Git 的 `037b22f620c090e88c16d4d4cfa5cb898f5bb163` 归档展开源码。两次都新建虚拟环境，从 PyPI 和 npm 官方源安装锁定依赖并重新构建。计时起点为展开源码前，电脑已装好 Python、Node.js、PowerShell、Chrome 和显卡驱动。 [启动指南](../README.md) [阶段计时与指导记录](reproduction-timing.json)

冻结验收版本为 `24e7161d19998705e3f94365abb476d372bc0f2b`。它与计时源码使用同一套运行代码、启动脚本、依赖锁文件及冻结题组。该版本包含一键验证和新增回归测试。

| 复现路径 | 本轮实测 | 核对结果 |
| --- | ---: | --- |
| 从空目录到正常采样 | 2 分 32 秒 | 50 Hz 信号以 400 Hz 采样，主峰 50 Hz，重建 RMSE 为 1.02 × 10⁻¹⁴ |
| 预先备好权重和运行包 | 3 分 00 秒 | 包含源码、依赖、构建、复制、校验、模型启动与预热。C 指导引用本次运行的 40 Hz 主峰 |
| 全量在线下载 | 17 分 26 秒 | 含两次断流后的续传及启动复查。权重通过 SHA-256 校验，C 指导引用本次运行的 40 Hz 主峰。10 分钟目标未达成 |

预置路径中，建环境 7.02 秒，安装 Python 依赖 98.75 秒，安装前端依赖 18.81 秒，构建、启动及 S1 运行 13.53 秒，复制模型和运行包 2.02 秒。模型校验与就绪 15.86 秒，预热 12.75 秒，保存 22 Hz 预测、运行 70/110 Hz 实验并得到指导 9.54 秒。其余为源码归档和环境配置。

全量下载中，权重两次约 302 秒后出现 curl 56，文件分别保留 1,124,640,366 和 2,534,523,874 字节。两次续传均返回 HTTP 206，最终完整文件为 2,740,937,888 字节。三个传输请求共 662.06 秒，运行包下载、解压和校验 12.12 秒。两条路线同时验证时，冷启动的一次重试在空闲显存 3545 MiB 时被计时脚本的检查拦下。待另一实例退出后，在 6302 MiB 空闲时完成最后一次启动。17 分 26 秒为包含排查和等待的实际经过时间。

## 复现操作

按 `README.md` 在源码目录安装依赖，运行 `.\scripts\start.ps1`，打开自由实验并点「正常采样」。准备好校验过的 Vulkan 运行包及 Qwen 权重后，在另一终端运行 `.\scripts\start-tutor.ps1`。可以从 `http://127.0.0.1:8081/health` 确认模型就绪。计时中的预热请求如下。执行后在引导学习核对 22 Hz 原预测和 40 Hz 实测主峰。

```powershell
$warmup = @{
    model = 'signal-lab-tutor'
    messages = @(@{ role = 'user'; content = ('Verify the predicted sample frequency and the measured peak. ' * 24) + ' Reply OK.' })
    max_tokens = 5
    temperature = 0.2
    chat_template_kwargs = @{ enable_thinking = $false }
} | ConvertTo-Json -Depth 6
Invoke-RestMethod -Uri 'http://127.0.0.1:8081/v1/chat/completions' -Method Post -ContentType 'application/json' -Body $warmup -TimeoutSec 37 | Out-Null
```

若首次下载中断，在项目根目录对同一个部分文件执行续传。

```powershell
$modelUrl = 'https://huggingface.co/unsloth/Qwen3.5-4B-GGUF/resolve/e87f176479d0855a907a41277aca2f8ee7a09523/Qwen3.5-4B-Q4_K_M.gguf'
curl.exe --fail --location --continue-at - --output '.\model\Qwen3.5-4B-Q4_K_M.gguf' $modelUrl
Get-FileHash -Algorithm SHA256 -LiteralPath '.\model\Qwen3.5-4B-Q4_K_M.gguf'
```

固定权重 SHA-256 为 `00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4`。运行包为 llama.cpp b11814 Windows Vulkan 版，校验值见启动指南。

## 冻结留出用例

首次运行前校验清单、题组、答案键和分配表四份 SHA-256。首次运行 10 条均通过。交互用例使用可控模型响应，运行计算、API、SQLite、浏览器和导出走实际实现。代码审查后进一步断言 I09 模型上下文完整结构、I10 原始运行参数和连续调参时旧请求的取消状态。 [冻结清单](case_manifest.csv) [校验表](frozen_inputs.sha256)

| 用例 | 首轮观测 |
| --- | --- |
| N04 | 1000 个样本，末样本 0.999 s，主峰 200 Hz，谱幅约 2，重建 RMSE 为 8.49 × 10⁻¹⁴ |
| N06 | 主峰 25 Hz，4096 点重建与解析参考的最大绝对误差为 1.63 × 10⁻¹³ |
| N10 | 主峰 53 Hz，前四点为 −1.5、1.5、−1.5、1.5，采样状态为欠采样 |
| N12 | 主峰 0 Hz，DC 幅度约 0.4，4096 点最大绝对误差为 1.14 × 10⁻¹³ |
| N14 | 极小相位的边界样本 RMS 约 2.60 × 10⁻⁸，仍检出 66 Hz 主峰 |
| N16 | 非整数采样率返回 422，错误定位到 `sample_rate_hz`，库中运行数保持为 0 |
| N19 | 20 Hz 和 120 Hz 增益分别为 0.999999797 和 0.707106781，稳态窗口为 1–2 s |
| I08 | 拒绝跨运行引用并显示 502，保留 22 Hz 预测和 48 Hz 对照，仅发起两次真实运行 |
| I09 | C-Y 迁移参数提议被过滤，指导返回 200，直接写入观察返回 409，保留 Y 题组和原预测 |
| I10 | 丢失保存响应后刷新恢复原判分，原样重发返回同一事件，改答案重发返回 409，JSON 和 CSV 各一条原迁移记录 |

## 一键验证与桌面检查

执行 `.\scripts\check.ps1`。最终通过 130 项后端测试、16 项前端单测、生产构建和 9 条 Chrome 流程，退出码为 0。首轮命令在测试通过后因 Windows 拒绝关闭进程树而返回失败。改为由合成服务接收本次运行目录下的停止标记，复测日志确认服务正常退出。注入浏览器命令退出码 37 后，一键脚本返回 37，合成服务同样正常退出。

- 断开网络后提示重试，恢复后空会话从未保存预测开始。模拟模型离线时保留 22 Hz 预测和 40 Hz 图表。未知运行编号返回 404，重试读取后恢复已保存图表。
- 1024 × 768 下检查参数、Hz 和 rad 单位、按钮和两张图。延迟旧响应并快速切换到边界退化时，旧请求被取消，摘要仍是 50/100 Hz 的奈奎斯特边界。 [桌面截图](../evidence/screenshots/task7-desktop-1024.jpg)
- 1280 × 720 下点击「观测主峰 51 Hz」，焦点回到当前运行证据，摘要显示 51 Hz。切换对照时旧运行引用被拒绝。 [证据定位](../evidence/screenshots/task7-desktop-c-evidence.jpg) [旧运行引用提示](../evidence/screenshots/task7-holdout-i08.jpg)

## 环境与已知限制

- Python 3.13.13，FastAPI 0.162.0，NumPy 2.5.4，SciPy 1.18.1，pytest 9.2.0。Node.js 24.16.0，npm 11.13.0，React 19.3.1，Vite 8.3.5，Vitest 5.1.0，Playwright 1.65.0，Chrome 157.0.8103.38。依赖由后端和前端锁文件固定。
- 启动与完整测试使用 PowerShell 7.6.9。本机 Windows PowerShell 5.1 的现有执行策略阻止脚本运行。构建输出的图表异步包为 510.93 kB，Vite 给出体积提示。
- RTX 4060 Laptop 8 GB 使用 Vulkan 加载 Qwen3.5-4B Q4_K_M。本轮计时适用于该机器和当时的网络。公开仓库下载和另一台电脑复现待测。
- B 组自由文本曾出现一处奈奎斯特频率关系错误。真人学习效果为「未测」，样本量 0。 [试跑记录](results.md#全流程合成试跑)
