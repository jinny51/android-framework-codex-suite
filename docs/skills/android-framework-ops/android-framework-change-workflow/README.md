# android-framework-change-workflow

> GitHub 说明页。Runtime skill 文件位于 [../../../../plugins/android-framework-ops/skills/android-framework-change-workflow](../../../../plugins/android-framework-ops/skills/android-framework-change-workflow)；插件安装后的 skill 目录不包含本 README。文中的 `scripts/...`、`references/...` 指向该 runtime skill 目录。

Android 全领域开发、问题分析和验证主流程 Skill。

## 用途

该 Skill 用于处理 Framework、SystemApp、App、HAL、native、vendor、kernel、driver、device 和 build 领域的开发、行为变更、问题分析、风险判断和最终验收。

它负责 Android 变更本身的工程流程，并按仓库选择 `registered_remote_tree` 或 `local_project` 源码权威及对应构建路由。注册的远程 Android 树必须走 `android-remote-channel`；真实本地项目使用项目自己的本地工具。源码接入、受支持的 AOSP/Soong/Make 远程构建和成员端材料上传由同插件内其他 Skill 配合完成。
进入源码分析前，可复用案例、平台实现、补丁、检索锚点和验证证据由 `android-knowledge-search` 配合检索。
当工作产生可复用、可参考、失败或阻塞经验时，应通过 `android-framework-patch-capture --change-domain <domain>` 整理本地材料。只有验证通过的 Framework capture 才由 `android-framework-patch-intake` 生成 incoming v1；其他领域明确停在本地材料。`android-knowledge-intake` 只保留共享内核和兼容 CLI。

代码修改前必须应用核心插件中唯一的 `android-change-policy/v1`：所有采用 patch 归档的 Android 变更都遵守成员溯源规则，FrameworkLog 等规则只在 Framework profile 下生效。个人或项目规则可以叠加，但不能改写核心身份和证据合同。

## 领域选择

- Framework/SystemApp/App：按真实 API、进程、签名和交付所有权选择，不按文件名猜测。
- HAL/native/vendor：按接口合同、ABI/VINTF/SELinux 和分区边界选择。
- kernel/driver/device：按子系统、probe/firmware/电源或板级集成的主要行为选择。
- build：仅在构建或发布图本身是产品行为时选择。

`scripts/collect_diagnostics.sh` 要求 AKBS 根已安装 outputs 合同。默认采集先写入受控 `outputs/tmp`，成功后原子晋升到 `$AKBS_ROOT/outputs/diagnostics/android-framework-change-workflow/<run-id>`，生成 `_manifest.json` 并重建 `outputs/manifests/catalog.jsonl`。显式输出也必须位于插件源码和缓存之外的新目录。脚本只在所有权标记与 canonical path 一致时清理本次调用目录；失败或受控中断会删除半成品，成功则保留诊断结果并移除标记。

## 典型配合

- 远程 AOSP/Soong/Make：`android-knowledge-search` -> 平台 `android-source-access` -> `android-framework-change-workflow` -> 核心 `android-remote-build-deploy`
- 远程 Gradle/Kbuild 等项目入口：`android-framework-change-workflow` -> `android-remote-channel` -> 项目自有构建命令
- 真实本地项目：`android-framework-change-workflow` -> 项目本地 wrapper/build entry
- 本地材料：`android-framework-change-workflow` -> `android-framework-patch-capture --change-domain <domain>`
- Framework 上传：validated Framework capture -> `android-framework-patch-intake` -> incoming v1

## 材料上传规则

该 Skill 在所有 Android 领域默认保留可审核的本地材料。只有 Framework 具备当前服务器 incoming v1 能力；其他领域不得伪装上传。是否沉淀进知识库由管理端后续决定。

- 开工前检索结果要进入后续 `search-before-change` 证据。
- 验证通过的修改可形成 `validated` 本地 capture；仅 Framework 可继续上传。
- 只有部分验证或需要目标平台复验的修改按 `candidate` 本地保存。
- 未完成但有明确修改或排查价值的工作按 `draft` 本地保存。
- 失败路径或阻塞原因按 `failed` / `blocked` 记录，不能让经验只留在成员电脑或会话里。
- 不能生成功能级补丁资料包时，应在最终报告中说明原因，并依赖 daily/weekly 自动化把 `work_findings` 写入 incoming。

## 文件入口

- [SKILL.md](../../../../plugins/android-framework-ops/skills/android-framework-change-workflow/SKILL.md)：给 Codex 自动加载的执行说明。
- [references/requirements-implementation.md](../../../../plugins/android-framework-ops/skills/android-framework-change-workflow/references/requirements-implementation.md)：需求实现规则。
- [references/diagnosis-and-instrumentation.md](../../../../plugins/android-framework-ops/skills/android-framework-change-workflow/references/diagnosis-and-instrumentation.md)：问题分析和调试日志/监控规则。
- [references/framework-risk-model.md](../../../../plugins/android-framework-ops/skills/android-framework-change-workflow/references/framework-risk-model.md)：Framework 风险模型。
- [references/verification-matrix.md](../../../../plugins/android-framework-ops/skills/android-framework-change-workflow/references/verification-matrix.md)：验证矩阵。
- [scripts/](../../../../plugins/android-framework-ops/skills/android-framework-change-workflow/scripts/)：日志切片、健康扫描、问题分析检查等辅助脚本。
