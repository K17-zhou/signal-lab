# 模型对照提议的教学有效性校验（2026-11-07）

## 缺陷与边界

修复前 `service.py` 仅排除与当前运行或迁移题相同的参数。对普通 `alias-frequency` 练习，原信号为 70 Hz、采样率为 110 Hz；模型提出 140 Hz 时，提议符合参数 schema，却恰好落在两倍频率边界，不能作为恢复原频率的对照。该判断来自项目实际数值引擎，而不是模型自由文本中的意图。

| 参数（振幅 1、初相位 0） | 引擎状态 | 观测主峰 | 重建 RMSE | 结果 |
| --- | --- | --- | --- | --- |
| 70 Hz / 110 Hz | undersampled | 40 Hz | 0.9999999999999992 | 当前观测 |
| 70 Hz / 140 Hz | nyquist_boundary | 无可辨主峰 | 0.7071067811865476 | 抑制提议，`next_experiment=null` |
| 70 Hz / 200 Hz | well_sampled | 70 Hz | 1.3878554042239178e-14 | 保留模型原提议 |

本次后端测试以模型替身提供可控的 JSON 提议，实际运行 API、服务、存储和数值引擎。这里只证明输出校验与数值性质；不将替身输出当作真实 Qwen 调用或学习效果证据。完整实测数值保存在 `.cache/qa/defect-fixes/comparison/04-engine-observations.json`。

## 最小修复

- 保留 `TutorSelection` / `TutorReply` schema。恢复对照固定当前信号频率、振幅和初相位，只允许采样率严格高于当前值且严格高于两倍频率。调用实际周期采样引擎，验证 `well_sampled`、主峰回到原频率（绝对容差 1e-9 Hz）及 `RMSE ≤ 振幅 × 1e-8`。
- 对 `sampling-phase`、`nyquist-boundary`、`study-x-boundary`、`study-y-boundary`，仅当前运行实际位于两倍边界时，额外允许固定频率、采样率和振幅的相位对照。引擎须仍报告边界，且前后样本差的 RMS 必须大于振幅的 1e-6，以排除浮点噪声或观测等价的相位变化。模型 `focus` 和学生提问不能授权此目标。
- 合格相位对照保留；例如 50 Hz / 100 Hz 下，初相位从 0 改为 π/2，样本 RMS 从约 1.03e-14 变为 1。说明明确写出：出现主峰也无法保证唯一恢复。该 π/2 正弦在本引擎中可能恰好产生极小 RMSE，仍不等于未知振幅/相位信号的唯一可辨识性。
- 仅对接受的提议追加简短目的与实际验证说明。不合格的合法提议变为 `null`，原科学说明和证据保留。不会生成、替换或纠正模型的参数。跨实验类型仍按现有 schema 非法回复处理（502），不会变成可执行对照。
- 当前允许目标只追加到既有 `theory` 字段，不改变 context 的六个顶层字段。内容仅由当前运行和注册案例类型决定，不加入迁移题参数、题干或答案。B 模式继续原样返回模型自然语言，测试特意保留一段含错误科学结论的 B 原文，确认服务没有暗中改写。
- `SYSTEM` / `STRUCTURED` 明确严格大于两倍、固定原信号参数和边界相位目标限制。前端、冻结题目、冻结断言均未修改。

## 真实 RED → GREEN 记录

基线 HEAD：`2b6f3c6`。先新增 `backend/tests/test_tutor_comparison.py`，在修改任何生产代码前实跑：**20 failed，5 passed，9.23 s，退出码 1**。失败包括 140 Hz 被错误接受、仍欠采样的改变被接受、改变频率/振幅/相位被接受、无观测差异的相位改变被接受，以及缺少对照目的/引擎指标校验。

随后修复 `backend/app/tutor/service.py` 和 `backend/app/tutor/client.py`，对同一测试文件实跑：**25 passed，6.73 s，退出码 0**。完整后端回归：**155 passed，24.15 s，退出码 0**。原 130 项后端测试未修改，其中包括冻结数值用例与 I09 迁移题隔离校验。

原始日志保留，不覆盖、不删除：

- `.cache/qa/defect-fixes/comparison/00-runner-setup.txt`：首次 PowerShell 路径构造错误的说明；该次未执行 pytest，不计作 RED。
- `.cache/qa/defect-fixes/comparison/01-red.log`：生产代码修改前的真实失败输出、命令、HEAD、TEMP/TMP 与退出码。
- `.cache/qa/defect-fixes/comparison/01-red-hashes.txt`：原始红日志与源码快照的 SHA-256。
- `.cache/qa/defect-fixes/comparison/red-source/`：修复前 `service.py`、`client.py` 和同一新增测试文件，供过程复现；不是通过人为故障生成的日志。
- `.cache/qa/defect-fixes/comparison/02-green-comparison.log`：同一新增测试文件的真实通过输出。
- `.cache/qa/defect-fixes/comparison/03-green-backend.log`：完整后端回归输出。

关键日志 SHA-256：

```text
01-red.log                37ab05d6fba6d4689541c88711322fe69927c293c989a49614f570d429d83409
02-green-comparison.log   cf3a5c3535f93986cc5f2db4efd7c8afd1a7052e988d842e1cd846fdd9ea9c5b
03-green-backend.log      1cfd6689a6045648a210cd7de6c9b593b076ff86afa7009fce9f1059b8f020c0
```

## 复核命令

从仓库根目录打开 PowerShell；`TEMP` / `TMP` 始终指向项目内：

```powershell
$qaTemp = Join-Path (Get-Location).Path '.cache/qa/defect-fixes/comparison/temp'
New-Item -ItemType Directory -Path $qaTemp -Force | Out-Null
$env:TEMP = $qaTemp
$env:TMP = $qaTemp
Set-Location backend
../.venv/Scripts/python.exe -m pytest 'tests/test_tutor_comparison.py::test_recovery_proposal_rejects_boundary_and_still_aliased_rates[140]' -vv
```

最小命令在原 `2b6f3c6` 源码与新增测试组合上应失败（旧实现返回 140 Hz 提议），在修复源码上应通过（提议为 `null`）。完整新增用例命令为 `../.venv/Scripts/python.exe -m pytest tests/test_tutor_comparison.py -vv`；完整后端回归为 `../.venv/Scripts/python.exe -m pytest -q`。如果用于录制，应标注为同一真实缺陷的过程复现，保留本次原始 RED/GREEN 记录。
