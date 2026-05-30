# android-knowledge-intake

> GitHub 说明页。Runtime skill 文件位于 [../../../../plugins/android-framework-ops/skills/android-knowledge-intake](../../../../plugins/android-framework-ops/skills/android-knowledge-intake)；插件安装后的 skill 目录不包含本 README。文中的 `scripts/...`、`references/...` 指向该 runtime skill 目录。

成员端 incoming 自动汇总提交 skill。

## 用途

该 skill 用于在成员本机自动汇总 Codex 会话、源码改动记录、patch、readme 和验证结果，先生成本地 `pending`（待检查包），再提交到私有知识库服务器 Git 仓库的 `incoming` 提交目录。

成员端 Codex 是知识生成主体。它负责从会话、git、patch 和验证记录里整理知识资产；服务器收到 `incoming` 后只做验收、归档、索引和展示。

普通成员使用 `daily/weekly` 自动化；维护者 `jinny/吴金雨` 只在需要保存有价值补丁时使用 `patch` 模式，服务器只保存补丁并重建索引，不生成日报或周报。

需要联调协议或服务器链路时，单独创建合成数据 profile；合成 profile 不读取真实 Codex 会话、不扫描真实源码、不上传真实 patch。

## 典型场景

- 每天下班前，Codex 自动汇总当天会话、源码改动、patch 和验证结果，生成 `pending`（待检查包）。
- 成员在检查窗口内补充或修正内容；到点后自动提交到团队知识库 `incoming`。
- 维护者只想保存一个有价值补丁时，使用 `patch` 模式提交补丁包，不生成个人日报或周报。

## 常用命令

检查配置：

```bash
python3 "scripts/android_knowledge_intake.py" doctor
python3 "scripts/android_knowledge_intake.py" --profile <member_alias> doctor
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

维护者手动提交补丁：

```bash
python3 "scripts/android_knowledge_intake.py" --profile jinny patch --prepare --patch /path/to/jinny001-feature@framework.patch --project "Android Framework" --summary "功能补丁摘要" --status validated
python3 "scripts/android_knowledge_intake.py" --profile jinny patch --submit-latest
```

如果补丁由 `android-framework-patch-capture` 生成，优先传整个 capture 输出目录，这样 patch、readme、验证结果和开发前知识库检索证据都会一起进入 incoming：

```bash
python3 "scripts/android_knowledge_intake.py" --profile jinny patch --prepare --patch-package /path/to/.codex/patch-packages/20260526-120000-patch --project "Android Framework" --summary "功能补丁摘要" --status validated
```

只有历史散落补丁才继续用 `--patch /path/to/*.patch`。

维护者需要验证协议和服务器链路时，才使用临时合成测试 profile。普通成员不要用测试 profile 提交日报、周报或 patch。

## 文件入口

- [SKILL.md](../../../../plugins/android-framework-ops/skills/android-knowledge-intake/SKILL.md)：给 Codex 自动加载的执行说明。
- [config.example.toml](../../../../plugins/android-framework-ops/skills/android-knowledge-intake/config.example.toml)：成员本机配置示例。
- [references/incoming-package-protocol.md](../../../../plugins/android-framework-ops/skills/android-knowledge-intake/references/incoming-package-protocol.md)：`incoming` 提交目录规则。
- [references/patch-maturity-rules.md](../../../../plugins/android-framework-ops/skills/android-knowledge-intake/references/patch-maturity-rules.md)：补丁成熟度和上传策略。
- [references/android-framework-patch-rules.md](../../../../plugins/android-framework-ops/skills/android-knowledge-intake/references/android-framework-patch-rules.md)：Android Framework patch 规范。
- [scripts/android_knowledge_intake.py](../../../../plugins/android-framework-ops/skills/android-knowledge-intake/scripts/android_knowledge_intake.py)：日报、周报、维护者补丁包生成和提交脚本。
