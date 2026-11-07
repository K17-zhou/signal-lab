# 缺陷修复暂停与接续记录

2026 年 11 月 7 日，用户要求“今天就先做到这吧，进度已经很快了”。停止开发、录制和发布，保存当前工作。下次仅在用户继续后恢复，不设置定时任务。

## 已完成

- 现有分支 `feat/signal-lab-foundation`。计划提交 `90e7291`，对照修复提交 `57018cef9ba0e04a3b3ecbdf45817fc0ea142ef5`。原公开 v1.1 和历史不变。
- 对照建议由实际数值引擎验算。恢复对照固定原频率、振幅和相位，只提高采样率至严格大于两倍频率；保留有明确目标和实际变化的边界相位对照。不合格的模型提议置空，不替换或伪造参数，B 原始文本保留。
- 新增25项后端测试在旧代码上20失败/5通过，修复后25通过。根代理全量回归为 **155后端（39.25秒）、16前端、构建（899ms）、9浏览器（36.8秒）通过**。日志在 `.cache/qa/defect-fixes/full-check-v2.log`，首次I08失败保留在 `full-check.log`。
- 新规则使旧 I08 的跨信号提议被过滤。保留原四份冻结文件与哈希；当前浏览器 I08 明确升级v2，先验证旧提议过滤，再用70/200有效对照验证旧运行引用仍返回502。见 [v2说明](../../evaluation/comparison-policy-v2.md)。没有跳过用例或放宽引用断言。
- 便携脚本、双击入口和私有 CPython 已准备。`runtime/python` 为3690文件、191727673字节，28个锁定分发，含许可证，无虚拟环境依赖。官方CPython ZIP SHA-256已与上游SPDX核对。
- 12项启动器测试通过，私有解释器以隔离PATH运行155项后端测试通过。CPU/Vulkan启动、两项健康检查、S1和真实模型短请求均实测；端口占用拒绝、owned进程关闭与退出0均已验证。这些结果不替代最终ZIP复现，也不是CPU/GPU性能基准。

## 保留的产物与位置

- [便携启动器](../../scripts/portable.py)、[运行环境构建器](../../scripts/build_portable.py)、[双击入口](../../开始演示.cmd)、[启动器测试](../../scripts/tests/test_portable.py)。
- 私有Python位于 `runtime/python`，被Git忽略，不得误删。最终包使用 `runtime/llama-b11814-bin-win-vulkan-x64.zip`，模型位置保持 `model/Qwen3.5-4B-Q4_K_M.gguf`。
- 便携证据与资源摘要在 `.cache/qa/defect-fixes/portable/final-inventory.json`、`unittest-final.log`、`pytest-private-final.log`、`check-final.log` 与 `integration-2976becc0b034f559297943becdac721/evidence.json`。
- 真实对照红/绿日志、旧源码和测试快照在 `.cache/qa/defect-fixes/comparison/`，说明在 [校验记录](../../evidence/ai-development/2026-11-07-comparison-validation.md)。
- 新视频的查看器、脚本、配音、旧/新真实测试重放输出位于 `.cache/qa/defect-fixes/video/`，精确停点以其 `PAUSED.md` 为准。计划片长7分10秒，其中开发过程复现162秒，尚未完成最终录制、编码和审核，不能作为已交付视频。

## 下次继续

1. 先读本记录、`video/PAUSED.md` 和[本轮计划](../superpowers/plans/2026-11-07-delivery-defect-fixes.md)，检查Git状态，不重复已通过的实现。
2. 连续实操视频完成后，更新README、技术PDF、作品介绍和交付清单，严格区分历史与本轮数字。便携包的实际耗时未知，不能预写结果。
3. 从冻结的新发布提交构建含Python、已构建前端、模型、llama ZIP与许可的完整v1.2包。原v1.0/v1.1保留。在用户指定的 `测试` 下创建新的便携验证子目录，原 `测试` 克隆及其环境不可清空。最终ZIP实际解压后，在隔离PATH下完成真实指导、证据、对照、迁移、恢复和退出检查，分别记录下载/解压/启动/流程耗时。
4. 用户已登录B站，IAB原tab1，停在投稿入口。用户指定百度网盘，后又明确要求使用本机客户端；客户端路径 `E:/BaiduNetdisk/BaiduNetdisk.exe`，主窗口进程 `BaiduNetdiskUnite.exe`，已观察到正常登录的网盘首页。下次必须重新获取窗口，不复用旧索引或句柄。
5. 百度网盘浏览器页面被站点安全策略拦截，该路径停止。后续遵循用户明确指定的原生客户端正常界面操作，不尝试浏览器绕过。尚未上传新版视频或完整包，亦未生成B站视频地址/网盘分享地址。
6. 新版材料和最终包验证后再同步GitHub、发布B站及网盘。今天的新修复只作本地checkpoint，远端仍是先前的v1.1交付版本。

正式赛事表单仍按用户要求暂缓。真人学习效果与异机复现保持未测，不能把合成演示或同机隔离PATH验证写成真人/异机结论。
