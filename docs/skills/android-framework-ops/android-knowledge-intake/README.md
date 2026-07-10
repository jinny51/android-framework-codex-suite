# Android Knowledge Intake

`android-knowledge-intake` 是成员 incoming 的唯一共享内核，负责首次启用、当前配置、doctor、插件版本门禁、包生成底层命令、上传前校验和 AKBS HTTP 上传。

成员日常使用三个业务入口：

- 日报：`android-daily-report-intake`
- 周报：`android-weekly-report-intake`
- 补丁包、补证包和补丁资产修正：`android-framework-patch-intake`

三个入口都调用本 skill 的同一套脚本，不各自复制上传实现。知识沉淀、新建/合并判断和知识有效度不属于成员插件。

## 首次启用

使用 [member-setup-prompt.md](../../../../plugins/android-framework-ops/skills/android-knowledge-intake/references/member-setup-prompt.md)。提示词让成员端 Codex 完成：

1. 从 Codex 插件市场更新 `android-framework-ops` 和当前操作系统的平台插件。
2. 检查当前会话是否仍加载旧缓存；无法热刷新时停止生成和上传。
3. 写入只包含成员身份和本地路径的当前配置。
4. 运行 `doctor --strict --check-remote`。

普通成员不维护服务器地址、SSH 上传命令或数据库路径。AKBS endpoint resolver 提供 HTTP 上传入口；受控测试覆盖使用环境变量。

## 当前配置

```toml
default_profile = "member_alias"

[paths]
codex_home = "$CODEX_HOME"
out_dir = "$CODEX_HOME/artifacts/android-knowledge-intake"

incoming_schema_version = "1"
timezone = "Asia/Shanghai"

[profiles.member_alias]
member_alias = "member_alias"
member_name = "成员姓名"
role = "member"
allowed_modes = ["daily", "weekly", "patch"]
knowledge_repo_worktree = "$CODEX_HOME/worktrees/knowledge"
synthetic_data = false
```

`knowledge_repo_worktree` 只用于 AKBS API 不可用时的本地离线搜索。路径不存在时不阻断 HTTP 上传。

## 健康检查

```bash
python3 scripts/android_knowledge_intake.py --profile <member_alias> doctor --strict --check-remote
```

检查内容包括成员身份、允许模式、产物目录、HTTP 上传入口、插件安装版本、远端版本和当前会话缓存版本。

## 共享命令

业务 skill 调用以下底层命令：

```bash
python3 scripts/android_knowledge_intake.py --profile <member_alias> daily --prepare
python3 scripts/android_knowledge_intake.py --profile <member_alias> weekly --prepare
python3 scripts/android_knowledge_intake.py --profile <member_alias> patch --prepare --patch-package <capture-dir>
```

`--upload` 生成并上传，`--submit-latest` 上传最近一个已准备包。日报按日期、周报按周周期保持唯一；替换必须显式提供被替换的运行编号。

日报和周报必须在生成阶段识别项目名和客户名。无法识别时，Codex 应在会话中提示成员补充，例如 `TVE1086U 青鸾云`；未补齐的包可以保留在本地，但上传前必须拒绝。

普通补丁包和补证包上传必须为 `validated`，并具备功能边界、项目、平台、Android 版本、干净补丁资产和 PASS 验证。无共同目标的聚合包必须按功能重新采集，不能作为补证包继续包装。

## 版本证据

生成前门禁比较：

- 当前运行脚本版本
- 本机已安装插件版本
- 当前会话 skill 缓存版本
- GitHub marketplace 版本

生成包在 `materials/evidence/source.json` 记录这些版本和检查结果。发现新版时可自动刷新磁盘缓存；当前会话无法热加载时停止本次生成或上传。

## 规则归属

项目、平台、Android 版本、聚合包、开发前搜索、搜索使用决策、补证关系、文本质量和补丁资产基础规则只来自 `android_framework_ops.knowledge_rules`。本地 `akbs-curation-maintainer` 在沉淀前加载同一份规则，不再实现另一套。

详细合同：

- [incoming-package-protocol.md](../../../../plugins/android-framework-ops/skills/android-knowledge-intake/references/incoming-package-protocol.md)
- [deterministic-rules-contract.md](../../../../plugins/android-framework-ops/skills/android-knowledge-intake/references/deterministic-rules-contract.md)
- [report-rules.md](../../../../plugins/android-framework-ops/skills/android-knowledge-intake/references/report-rules.md)
- [android-framework-patch-rules.md](../../../../plugins/android-framework-ops/skills/android-knowledge-intake/references/android-framework-patch-rules.md)
- [patch-package-status-rules.md](../../../../plugins/android-framework-ops/skills/android-knowledge-intake/references/patch-package-status-rules.md)
