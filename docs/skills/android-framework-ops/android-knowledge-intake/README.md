# android-knowledge-intake

> GitHub 说明页。Runtime skill 文件位于 [../../../../plugins/android-framework-ops/skills/android-knowledge-intake](../../../../plugins/android-framework-ops/skills/android-knowledge-intake)；插件安装后的 skill 目录不包含本 README。文中的 `scripts/...`、`references/...` 指向该 runtime skill 目录。

成员端 incoming 自动汇总提交 skill。

## 用途

该 skill 用于在成员本机自动汇总 Codex 会话、源码改动记录、patch、readme 和验证结果，先生成本地 `pending`（待检查包），再提交到私有知识库服务器 Git 仓库的 `incoming` 提交目录。

成员端 Codex 是知识生成主体。它负责从会话、git、patch 和验证记录里整理知识资产；服务器收到 `incoming` 后只做验收、归档、索引和展示。

普通成员使用 `daily/weekly` 自动化作为保底沉淀；完成或阶段性完成 Framework 修改时，通过 `patch` 模式生成 `framework_change` incoming。管理员 profile 只在需要手动保存有价值补丁时使用 `patch` 模式，不生成个人日报或周报。

默认策略是先自动沉淀，再按成熟度排序。没有人工确认不等于丢弃；不满足 `validated` 时也应尽量按 `candidate`、`draft`、`failed` 或 `blocked` 保存证据。

需要联调协议或服务器链路时，单独创建合成数据 profile；合成 profile 不读取真实 Codex 会话、不扫描真实源码、不上传真实 patch。

## 典型场景

- 每天下班前，Codex 自动汇总当天会话、源码改动、候选 patch、失败路径、阻塞点和验证结果，生成 `pending`（待检查包）。
- 成员在检查窗口内补充或修正内容；到点后自动提交到团队知识库 `incoming`。
- Framework 修改满足条件时，成员端 Codex 自动通过 `patch-capture -> intake` 生成 `framework_change` incoming。
- `framework_change` 会携带 patch 内容 `sha1`；如果明确来自某次日报或周报上下文，可显式携带 `related_report_run_ids`。
- 管理员只想保存一个有价值补丁时，使用 `patch` 模式提交补丁包，不生成个人日报或周报。

## 常用命令

检查配置：

```bash
python3 "scripts/android_knowledge_intake.py" doctor
python3 "scripts/android_knowledge_intake.py" --profile <member_alias> doctor
python3 "scripts/android_knowledge_intake.py" --profile <member_alias> doctor --strict --check-remote
```

生成当天 pending 包：

```bash
python3 "scripts/android_knowledge_intake.py" --profile <member_alias> daily --prepare
```

提交最新 pending 包：

```bash
python3 "scripts/android_knowledge_intake.py" --profile <member_alias> daily --submit-latest
```

生成周报 pending 包：

```bash
python3 "scripts/android_knowledge_intake.py" --profile <member_alias> weekly --prepare
```

生成 Framework change incoming：

```bash
python3 "scripts/android_knowledge_intake.py" --profile <member_alias> patch --prepare --patch /path/to/rk14-frameworks-base@feature.patch --project "TVE8402M" --summary "功能补丁摘要" --status candidate
python3 "scripts/android_knowledge_intake.py" --profile <member_alias> patch --submit-latest
```

如果补丁由 `android-framework-patch-capture` 生成，优先传整个 capture 输出目录，这样 patch、readme、验证结果和开发前知识库检索证据都会一起进入 incoming：

```bash
python3 "scripts/android_knowledge_intake.py" --profile <member_alias> patch --prepare --patch-package /path/to/.codex/patch-packages/20260526-120000-patch --project "TVE8402M" --summary "功能补丁摘要" --status validated
```

如果这个 Framework change 明确来自某个 `daily_trace` 或 `weekly_trace` incoming 包，显式带上 run id，服务器会用它做确定性关联：

```bash
python3 "scripts/android_knowledge_intake.py" --profile <member_alias> patch --prepare --patch-package /path/to/.codex/patch-packages/20260526-120000-patch --summary "功能补丁摘要" --status candidate --related-report-run-id 20260601-210000-daily
```

只有直接指定单个 patch 文件时才使用 `--patch /path/to/*.patch`。

管理员需要验证协议和服务器链路时，才使用临时合成测试 profile。普通成员不要用测试 profile 提交日报、周报或 patch。

## 文件入口

- [SKILL.md](../../../../plugins/android-framework-ops/skills/android-knowledge-intake/SKILL.md)：给 Codex 自动加载的执行说明。
- [config.example.toml](../../../../plugins/android-framework-ops/skills/android-knowledge-intake/config.example.toml)：成员本机配置示例。
- [references/incoming-package-protocol.md](../../../../plugins/android-framework-ops/skills/android-knowledge-intake/references/incoming-package-protocol.md)：`incoming` 提交目录规则。
- [references/patch-maturity-rules.md](../../../../plugins/android-framework-ops/skills/android-knowledge-intake/references/patch-maturity-rules.md)：补丁成熟度和上传策略。
- [references/android-framework-patch-rules.md](../../../../plugins/android-framework-ops/skills/android-knowledge-intake/references/android-framework-patch-rules.md)：Android Framework patch 规范。
- [scripts/android_knowledge_intake.py](../../../../plugins/android-framework-ops/skills/android-knowledge-intake/scripts/android_knowledge_intake.py)：生成并提交 `daily_trace`、`weekly_trace`、`framework_change` incoming 包。
