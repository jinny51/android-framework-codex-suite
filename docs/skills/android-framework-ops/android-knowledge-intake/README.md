# android-knowledge-intake

> GitHub 说明页。Runtime skill 文件位于 [../../../../plugins/android-framework-ops/skills/android-knowledge-intake](../../../../plugins/android-framework-ops/skills/android-knowledge-intake)；插件安装后的 skill 目录不包含本 README。文中的 `scripts/...`、`references/...` 指向该 runtime skill 目录。

成员端 incoming 材料包自动汇总提交 skill。

## 用途

该 skill 用于在成员本机自动汇总 Codex 会话、源码改动记录、功能 README、仓库级 patch 和验证结果，先生成本地 `pending`（待检查包），再通过服务器上传入口（server upload endpoint）提交为上传包（incoming package）。成员端 skill 不克隆、不拉取、不直接搜索、不 push 数据库仓库（database repository）。

成员端 Codex 是材料生成主体。它负责从会话、git、patch 和验证记录里整理上传包；服务器收到上传包后只做确定性验收、归档和数据库仓库提交，不直接批准为 AI 知识。能否进入知识库仓库（knowledge repository）由你本机的本地技能（local skill）`android-knowledge-curation-maintainer` 驱动的 AI 知识闭环（AI knowledge loop）判断。

普通成员使用 `daily/weekly` 自动化生成成员级上传包；其中周报包（weekly report package）只做一周进度归档、成员查看和统计，不进入知识库仓库。完成或阶段性完成 Framework 修改时，通过 `patch` 模式生成 `framework_change` incoming。非成员 profile 只用于协议和服务器链路测试，不能和你本机的 `android-knowledge-curation-maintainer` 混为一谈。

默认策略是先自动保存上传材料，再按包状态（package status）排序。缺少显式确认不等于丢弃；不满足 `validated` 时也应尽量按 `candidate`、`draft`、`failed` 或 `blocked` 保存证据。包状态不是沉淀结论（curation decision）。

需要联调协议或服务器链路时，单独创建合成数据 profile；合成 profile 不读取真实 Codex 会话、不扫描真实源码、不上传真实 patch。

## 首次启用

成员首次切到当前双仓库链路时，优先把 [references/member-migration-prompt.md](../../../../plugins/android-framework-ops/skills/android-knowledge-intake/references/member-migration-prompt.md) 里的整段提示词交给成员端 Codex。提示词会要求先完成插件更新（plugin update），再直接写入新配置（new configuration）、检查服务器上传入口（server upload endpoint）、克隆或更新唯一的知识库仓库（knowledge repository）工作树并运行健康检查（doctor check），成员只需要确认自己的 `member_alias`、姓名和 Git 作者信息。

严格健康检查（doctor strict check）会要求 `knowledge_repo_worktree` 存在且是 Git 仓库（git repository）。成员端只克隆知识库仓库（knowledge repository），不能克隆或直接读取数据库仓库（database repository）。

日报、周报和补丁生成入口会先做插件新鲜度检查（plugin freshness check）。Git checkout 会和上游分支比较；Codex 插件缓存安装会读取 `.codex-plugin/plugin.json` 的版本，并在可访问 GitHub marketplace 源时比较远端版本。如果能确认当前插件落后远端，脚本会停止本次生成并提示先更新插件，避免成员继续用过期协议生成上传包。

生成出的上传包会在 `materials/evidence/source.json` 写入 `plugin_name`、`plugin_version`、`skill_version`、`plugin_installation` 和可用的 `plugin_commit`。服务器新上传严格校验会拒绝缺少这些版本证据的包，避免项目（project）、平台（platform）或 Android 版本（Android version）错误时无法追溯生成入口。

日报包（daily report package）和补丁包（patch package）会携带成员侧知识搜索使用证据（search usage evidence）。Codex 正常开发流程生成的已验证（validated）补丁包必须携带开发前知识搜索（pre-change knowledge search）证据，`search_before_change.searched` 必须为 `true`；没有找到可用知识时也要记录未命中（not_found）。如果命中了知识搜索候选，local-check 会要求把未知（unknown）闭合为直接复用（reuse）、适配复用（adapt）、仅作参考（reference_only）、不适用（not_applicable）或未命中（not_found）。手动实现（manual implementation）、外部实现、历史材料、混合实现或未知来源不能事后伪造开发前搜索；可以如实记录 `searched=false`，后续由管理端本地技能执行沉淀前重叠检索（post-change overlap check）。捕获包（patch capture package）里只有未知（unknown）时，只能用和当前功能锚点匹配的当天搜索记录补齐；同一成员同一天并不足以关联。这些值只说明开发时如何使用搜索结果，不是沉淀结论（curation decision）。

## 典型场景

- 每天下班前，Codex 自动汇总当天会话、源码改动、候选 patch、失败路径、阻塞点和验证结果，生成 `pending`（待检查包）。
- 成员在检查窗口内补充或修正内容；到点后通过服务器上传入口提交。
- Framework 修改满足条件时，成员端 Codex 自动通过 `patch-capture -> intake` 生成功能级补丁资料上传包。
- `framework_change` 会携带 patch 内容 `sha1`；如果明确来自某次日报或周报上下文，可显式携带 `related_report_run_ids`。周报 run id 只是来源背景，不代表周报包进入知识库仓库。
- 需要验证协议或服务器链路时，使用临时测试 profile 生成测试补丁包；普通成员不要使用测试 profile。

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

如果补丁资料由 `android-framework-patch-capture` 生成，优先传整个 capture 输出目录，这样功能 README、仓库级 patch、构建结果、验证结果和真实存在的开发前知识库检索证据都会一起进入 incoming：

```bash
python3 "scripts/android_knowledge_intake.py" --profile <member_alias> patch --prepare --patch-package /path/to/.codex/patch-packages/20260526-120000-patch --project "TVE8402M" --summary "功能补丁摘要" --status validated
```

成员查看界面如果提示某个补丁包需补证据（needs_evidence），不要新建第四类上传包。成员端 Codex 应重新生成或提交普通补丁包（patch package），补齐缺失证据，并用原始上传包键关联：

```bash
python3 "scripts/android_knowledge_intake.py" --profile <member_alias> patch --prepare --patch-package /path/to/.codex/patch-packages/20260612-171820-feature --project "TVE1067M" --platform mtk --android-version 16 --summary "功能补丁摘要" --status validated --supplement-for-package-key 20260612/lincong/20260612-172836-patch --supplement-reason "补充项目（project）、平台（platform）和 Android 版本（Android version）证据"
```

该命令仍生成 `framework_change` 上传包，只是额外携带 `materials/evidence/evidence_supplement.json`，用于说明它补充哪个原始上传包。

补证包会先做本地校验。如果 `--supplement-reason` 说明在补项目（project）、平台（platform）、Android 版本（Android version）或验证（verification），新包不能继续保留对应的 `unknown`、缺失或未验证状态：补项目时必须有可追溯 `TVD`/`TVE`/`TVA`/`TVI` 项目和 `project_inference` 依据；补平台或 Android 版本时对应字段不能为 `unknown`，必要时使用显式 `--platform` 和 `--android-version`；补验证时 `verification_result` 必须为 `PASS`。如果缺口是开发前知识搜索（pre-change knowledge search），但事实是手动实现或开发前没有搜索，成员不能补造搜索；应记录实现来源，交给管理端本地技能做沉淀前重叠检索（post-change overlap check）。

`--project` 只有包含 `TVD`/`TVE`/`TVA`/`TVI` 公司项目号时才作为高优先级项目名。对 capture 包，intake 还会读取 capture manifest/patch item、`source_root`、repo 路径、git 分支/remote、WSL source-access registry、功能 README/diff/summary，以及显式关联的日报/周报上下文来识别项目；泛化标签不会写入 `manifest.project`。结构化项目字段只保存规范项目型号；分支、客户、业务、模块、构建或中文描述等规范外尾随内容只进入 `project_inference` 证据，不能进入 `manifest.project`。

如果这些来源识别出多个不同项目（project）候选，成员上传技能不会任选一个写入包，而是写成 `project=unknown`，在 `project_inference.candidates` 保留全部候选，并把冲突写进 `project_inference.limits`。即便成员传入 `--status validated`，这类包也会降为候选（candidate），后续由补证包（evidence supplement package）闭合。

补丁包的平台（platform）只允许 `mtk`、`rk`、`unisoc` 或 `unknown`。`android14`、`app15` 这类前缀不能写成平台，只能在数字可信时作为 Android 版本线索；平台未知的补丁包可以被服务器归档，但管理端本地沉淀技能必须把它作为需补证据处理。补证时如果补丁捕获包或文件名不能证明平台和 Android 版本，可以通过 `--platform mtk|rk|unisoc|unknown` 和 `--android-version <number>` 显式写入边界字段。

如果这个补丁包明确来自某个 `daily_trace` 或 `weekly_trace` 上传包，显式带上 run id，后续 AI 知识闭环会用它做确定性关联。没有显式 run id 时，补丁包生成会尝试读取同一成员同一天的日报包（daily report package）；只有日报上下文里能识别出唯一 `TVD`/`TVE`/`TVA`/`TVI` 项目时，才自动继承项目（project）并写入 `related_report_run_ids`。如果日报缺失、多项目或冲突，仍保持 `project=unknown` 并交给补证包（evidence supplement package）闭合。`weekly_trace` 只能作为背景关联，周报包本身固定仅归档：

```bash
python3 "scripts/android_knowledge_intake.py" --profile <member_alias> patch --prepare --patch-package /path/to/.codex/patch-packages/20260526-120000-patch --summary "功能补丁摘要" --status candidate --related-report-run-id 20260601-210000-daily
```

只有直接指定单个独立 patch 文件时才使用 `--patch /path/to/*.patch`。多个原始 patch 文件不能直接塞进一个上传包；必须先用补丁采集技能（android-framework-patch-capture）按功能生成补丁包（patch package），再用 `--patch-package` 提交。补丁包（patch package）的单位是功能，不是日期；“今日补丁合集”或一个包包含多个独立功能会在本地校验失败，不设补丁数量例外，需要拆成多个普通补丁包。已经生成的日期聚合包不要继续补证，应重新按功能生成并分别上传。

管理员需要验证协议和服务器链路时，才使用临时合成测试 profile。普通成员不要用测试 profile 提交日报、周报或 patch。

## 文件入口

- [SKILL.md](../../../../plugins/android-framework-ops/skills/android-knowledge-intake/SKILL.md)：给 Codex 自动加载的执行说明。
- [config.example.toml](../../../../plugins/android-framework-ops/skills/android-knowledge-intake/config.example.toml)：成员本机配置示例，使用服务器上传入口和知识库仓库字段。
- [references/member-migration-prompt.md](../../../../plugins/android-framework-ops/skills/android-knowledge-intake/references/member-migration-prompt.md)：成员首次启用提示词，覆盖插件更新、新配置、服务器上传入口和知识库仓库健康检查。
- [references/incoming-package-protocol.md](../../../../plugins/android-framework-ops/skills/android-knowledge-intake/references/incoming-package-protocol.md)：`incoming` 提交目录规则。
- [references/patch-package-status-rules.md](../../../../plugins/android-framework-ops/skills/android-knowledge-intake/references/patch-package-status-rules.md)：补丁包状态和上传策略。
- [references/android-framework-patch-rules.md](../../../../plugins/android-framework-ops/skills/android-knowledge-intake/references/android-framework-patch-rules.md)：Android Framework patch 规范。
- [scripts/android_knowledge_intake.py](../../../../plugins/android-framework-ops/skills/android-knowledge-intake/scripts/android_knowledge_intake.py)：生成并提交 `daily_trace`、`weekly_trace`、`framework_change` incoming 包。
