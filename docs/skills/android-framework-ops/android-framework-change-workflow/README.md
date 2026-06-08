# android-framework-change-workflow

> GitHub 说明页。Runtime skill 文件位于 [../../../../plugins/android-framework-ops/skills/android-framework-change-workflow](../../../../plugins/android-framework-ops/skills/android-framework-change-workflow)；插件安装后的 skill 目录不包含本 README。文中的 `scripts/...`、`references/...` 指向该 runtime skill 目录。

Android Framework 开发、问题分析和验证主流程 skill。

## 用途

该 skill 用于处理 Android Framework 开发、行为变更、bug 问题分析、风险判断、调试日志/监控和最终验收报告。

它负责框架改动本身的工程流程；源码访问、远程构建部署和成员端材料上传由同插件内其他 skill 配合完成。
进入源码分析前，可复用案例、平台实现、补丁、检索锚点和验证证据由 `android-knowledge-search` 配合检索。
当工作产生可复用、可参考、失败或阻塞经验时，应通过 `android-framework-patch-capture` 整理补丁资料，再由 `android-knowledge-intake` 生成 incoming 包。

如果同时安装或明确要求 `jinny-framework-coding-standards`，应在代码修改前应用团队补丁开发规范和 FrameworkLog 日志规范，不能等补丁采集阶段再补规范。

## 典型场景

- 用户提出一个 Framework 行为变更需求，需要 Codex 分析影响范围、修改代码、处理风险，并给出最终验收结论。
- 设备上出现 SystemUI、WindowManager、PackageManager、ActivityTaskManager 等 Framework 问题，需要基于源码、logcat、dumpsys 和复现现象定位根因。
- 构建和推送已经完成，但还需要判断目标行为是否真的满足需求、是否引入附近回归。

## 典型配合

- WSL 场景：`android-knowledge-search` -> `android-wsl-source-access` -> `android-framework-change-workflow` -> `android-wsl-remote-build-deploy`
- 材料上传：`android-framework-change-workflow` -> `android-framework-patch-capture` -> `android-knowledge-intake` -> incoming

## 材料上传规则

该 skill 的目标不是“成员想起来才上传补丁”，而是在成员端 Codex 完成 Framework 需求时默认保留可审核材料。是否沉淀进知识库仓库（knowledge repository）由管理端本地技能（local skill）后续决定。

- 开工前检索结果要进入后续 `search-before-change` 证据。
- 验证通过的修改按 `validated` 包状态上传。
- 只有部分验证或需要目标平台复验的修改按 `candidate` 包状态上传。
- 未完成但有明确 Framework 修改或排查价值的工作按 `draft` 包状态上传。
- 失败路径或阻塞原因按 `failed` / `blocked` 记录，不能让经验只留在成员电脑或会话里。
- 不能生成功能级补丁资料包时，应在最终报告中说明原因，并依赖 daily/weekly 自动化把 `work_findings` 写入 incoming。

## 文件入口

- [SKILL.md](../../../../plugins/android-framework-ops/skills/android-framework-change-workflow/SKILL.md)：给 Codex 自动加载的执行说明。
- [references/requirements-implementation.md](../../../../plugins/android-framework-ops/skills/android-framework-change-workflow/references/requirements-implementation.md)：需求实现规则。
- [references/diagnosis-and-instrumentation.md](../../../../plugins/android-framework-ops/skills/android-framework-change-workflow/references/diagnosis-and-instrumentation.md)：问题分析和调试日志/监控规则。
- [references/framework-risk-model.md](../../../../plugins/android-framework-ops/skills/android-framework-change-workflow/references/framework-risk-model.md)：Framework 风险模型。
- [references/verification-matrix.md](../../../../plugins/android-framework-ops/skills/android-framework-change-workflow/references/verification-matrix.md)：验证矩阵。
- [scripts/](../../../../plugins/android-framework-ops/skills/android-framework-change-workflow/scripts/)：日志切片、健康扫描、问题分析检查等辅助脚本。
