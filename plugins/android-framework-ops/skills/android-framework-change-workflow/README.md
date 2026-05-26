# android-framework-change-workflow

Android Framework 开发、问题分析和验证主流程 skill。

## 用途

该 skill 用于处理 Android Framework 开发、行为变更、bug 问题分析、风险判断、调试日志/监控和最终验收报告。

它负责框架改动本身的工程流程；源码访问和远程构建部署由其他 skill 配合完成。
进入源码分析前，历史报告、补丁和代码标识检索由 `android-knowledge-search` 配合完成。
当修改需要进入团队知识库时，补丁资料整理由 `android-framework-patch-capture` 负责。

## 典型场景

- 用户提出一个 Framework 行为变更需求，需要 Codex 分析影响范围、修改代码、处理风险，并给出最终验收结论。
- 设备上出现 SystemUI、WindowManager、PackageManager、ActivityTaskManager 等 Framework 问题，需要基于源码、logcat、dumpsys 和复现现象定位根因。
- 构建和推送已经完成，但还需要判断目标行为是否真的满足需求、是否引入附近回归。

## 典型配合

- WSL 场景：`android-knowledge-search` -> `android-wsl-source-access` -> `android-framework-change-workflow` -> `android-wsl-remote-build-deploy`
- Windows 原生场景：`android-knowledge-search` -> `android-windows-source-access` -> `android-framework-change-workflow` -> `android-windows-remote-build-deploy`
- 知识库入库：`android-framework-change-workflow` -> `android-framework-patch-capture` -> `android-knowledge-intake`

## 文件入口

- [SKILL.md](SKILL.md)：给 Codex 自动加载的执行说明。
- [references/requirements-implementation.md](references/requirements-implementation.md)：需求实现规则。
- [references/diagnosis-and-instrumentation.md](references/diagnosis-and-instrumentation.md)：问题分析和调试日志/监控规则。
- [references/framework-risk-model.md](references/framework-risk-model.md)：Framework 风险模型。
- [references/verification-matrix.md](references/verification-matrix.md)：验证矩阵。
- [scripts/](scripts/)：日志切片、健康扫描、问题分析检查等辅助脚本。
