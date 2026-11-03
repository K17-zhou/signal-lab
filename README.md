# 信号实验工坊

面向通信原理学习的交互实验项目。当前已实现数值计算基础及标准案例导出；网页、AI教学、学习记录和滤波实验仍属于后续计划。

## 当前能做什么

- 运行一秒周期正弦信号的采样、混叠、单边幅度谱和周期重建。
- 区分正常采样、欠采样、奈奎斯特边界、采样全零等退化情况。
- 导出S1–S4的真实计算结果、运行编号、参数、指标和曲线数据。
- 拒绝范围外、非有限、错误类型和未知实验请求。

## Windows运行

本轮实测Python 3.13.13、Node.js v24.16.0；当前数值模块不依赖Node。项目声明Python>=3.12，但其他Python版本尚未实测。

在项目根目录的PowerShell中执行：

```powershell
# 使用项目内临时目录，适用于本次沙箱默认TEMP不可写的情况。
New-Item -ItemType Directory -Force .cache/tmp | Out-Null
$env:TEMP = (Resolve-Path .cache/tmp).Path
$env:TMP = $env:TEMP
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r .\backend\requirements.lock.txt

Push-Location backend
..\.venv\Scripts\python.exe -m pytest -q
..\.venv\Scripts\python.exe -m app.demo --output ..\artifacts\sampling-foundation
Pop-Location
```

已有.venv时可跳过环境创建。导出命令要求输出目录尚不存在，避免覆盖已有证据；再次运行请换一个目录名。

`artifacts/sampling-foundation/summary.json`是指标摘要；S1.json到S4.json包含完整曲线数据。这些是解析周期模型的计算结果，不是真人学习效果或硬件测量。

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
- 本轮没有调用模型API、使用密钥、采购硬件或发布服务。

## 文档与证据

- [执行计划](docs/superpowers/plans/2026-11-03-signal-lab-plan.md)
- [设计基线](docs/superpowers/specs/2026-11-03-signal-lab-design.md)
- [AI开发证据索引](evidence/ai-development/index.md)
- 本地测试环境以backend/requirements.lock.txt锁定；.venv、临时缓存、导出的大数组不进入Git。
