# android-knowledge-intake

> GitHub 说明页。Runtime skill 文件位于 [../../../../plugins/android-framework-ops/skills/android-knowledge-intake](../../../../plugins/android-framework-ops/skills/android-knowledge-intake)；插件安装后的 skill 目录不包含本 README。文中的 `scripts/...`、`references/...` 指向该 runtime skill 目录。

成员端 incoming 共享内核、配置诊断和旧命令兼容 skill。

## 用途

该 skill 用于成员首次启用、插件更新、配置迁移、doctor 检查、共享上传协议和旧命令兼容路由。新的成员业务入口已经拆成三个 skill：`android-daily-report-intake` 负责个人日报，`android-weekly-report-intake` 负责个人周报，`android-framework-patch-intake` 负责原始补丁包、补证包、替换包和补丁资产修正。三者都复用本 skill 的 `scripts/android_knowledge_intake.py`，不复制三套上传实现。

共享内核会在成员本机先生成本地 `pending`（待检查包），再通过服务器上传入口（server upload endpoint）提交为上传包（incoming package）。成员端 skill 不克隆、不拉取、不直接搜索、不 push 数据库仓库（database repository）。

成员端 Codex 是材料生成主体。它负责从会话、git、patch 和验证记录里整理上传包；服务器收到上传包后只做轻量接收并写入上传分支（intake branch），不直接入库、不做业务规则判断，也不批准为 AI 知识。后续由管理端本地推广入口决定推广、退回或要求补证。能否进入知识库仓库（knowledge repository）由你本机的本地技能（local skill）`akbs-curation-maintainer` 驱动的 AI 知识闭环（AI knowledge loop）判断。

普通成员新任务优先使用拆分入口：日报用 `android-daily-report-intake`，周报用 `android-weekly-report-intake`，补丁包和补证包用 `android-framework-patch-intake`。旧 `android-knowledge-intake daily|weekly|patch` 命令继续可用，只是作为旧命令路由（legacy route）进入同一共享内核。周报包（weekly report package）只做一周进度归档、成员查看和统计，不进入知识库仓库。非成员 profile 只用于协议和服务器链路测试，不能和你本机的 `akbs-curation-maintainer` 混为一谈。

默认策略是先在成员本机保存材料，再只把达到普通上传门禁的包送到服务器。普通补丁包和补证包上传默认必须是 `validated`：功能边界清楚、项目（project）、平台（platform）、Android 版本（Android version）可追溯、补丁资产干净，并且构建与设备或等价验证通过。`candidate`、`draft`、`failed` 或 `blocked` 可以作为本地材料或日报/周报上下文保留，但不直接进入服务器上传队列。包状态不是沉淀结论（curation decision）。

日报和周报没有“未来提交”模式。日报日期晚于当前本机日期时会停止；周报锚定日期晚于当前本机日期，或 `week_range` 晚于当前本机所属周时也会停止。过去日期日报和过去周期周报属于补交，允许生成。

日报正文和周报正文就是成员与管理员直接阅读的主产物。新包会按 Codex 办公版工作报告模板生成 `reports/daily.md` / `reports/weekly.md`，并同时写入 `materials/display/report_view.json` 作为 UI 读模型（UI read model），服务卡片、列表和详情展示；这个读模型只是同一份报告的结构化索引，不是另一套证据或 AI 层。日报重点回答“今天干了什么”，周报重点回答“这一周整体推进得怎么样”，并保留需求来源地、需求种类、来源清单、分类统计、剩余事项、风险、Patch 产出和验证交付字段。`work_findings.json` 仍保留为审计、归档和后续分析证据。

补丁包和补证包会同时写入两份稳定读模型：`materials/display/patch_view.json` 是成员端和管理端页面直接消费的人类可见材料视图，包含原始包/补证包身份、功能标题、问题、方案、验证结果、项目、平台、Android 版本、卡片和详情分区；`materials/evidence/patch_ai_facts.json` 是管理端本地校验、沉淀判断、复审和搜索索引使用的证据视图，包含模块、细分领域、代码锚点、补丁行为目标、验证目标、搜索使用和合并硬门禁输入。两者都来自同一份补丁事实，但 `patch_view` 不承担 AI 判断，`patch_ai_facts` 不作为 UI 主展示文案。

日报包和周报包按成员与报告身份防重复：日报使用 `date`，周报使用 `week_range`。成员本机已有同身份 pending 或 submitted 报告包时，`--prepare`、`--upload` 和 `--submit-latest` 会停止，避免静默产生第二个普通报告包。成员要么取消本次提交，要么显式替换已有包：日报使用 `daily --replace-daily-run-id <old_run_id>`，周报使用 `weekly --replace-weekly-run-id <old_run_id>`；新包会写入 `replacement_for_run_id` 和 `supersedes` 元数据。

需要联调协议或服务器链路时，单独创建合成数据 profile；合成 profile 不读取真实 Codex 会话、不扫描真实源码、不上传真实 patch。

## 首次启用

成员首次切到当前双仓库链路时，优先把 [references/member-migration-prompt.md](../../../../plugins/android-framework-ops/skills/android-knowledge-intake/references/member-migration-prompt.md) 里的整段提示词交给成员端 Codex。提示词会要求先完成插件更新（plugin update），再直接写入新配置（new configuration）、检查服务器上传入口（server upload endpoint）、克隆或更新唯一的知识库仓库（knowledge repository）工作树并运行健康检查（doctor check），成员只需要确认自己的 `member_alias`、姓名和 Git 作者信息。

严格健康检查（doctor strict check）会要求 `knowledge_repo_worktree` 存在且是 Git 仓库（git repository）。成员端只克隆知识库仓库（knowledge repository），不能克隆或直接读取数据库仓库（database repository）。

日报、周报和补丁生成入口会先做插件版本门禁（plugin version gate）。脚本会比较三类版本：当前正在运行脚本的插件版本、Codex 已安装的最新插件缓存版本、可访问时的 GitHub marketplace 远端版本。Git checkout 如果可以安全快进，会自动执行 `git pull --ff-only`，然后停止当前生成，因为已经加载的 Python 进程和 Codex 会话不能热刷新技能说明；成员需要重新运行原命令。如果 Codex 已安装新插件，但当前会话仍在旧技能缓存里运行，也会停止并提示新开或重启 Codex 会话。

生成日报包、周报包、补丁包或补证包之前，技能会先确认运行插件、已安装插件缓存、会话技能缓存和远端插件版本兼容；无法确认最新时停止生成，避免旧规则继续产出材料。生成出的上传包会在 `materials/evidence/source.json` 写入 `plugin_name`、当前 `plugin_version`、当前 `skill_version`、`plugin_installation`、可用的 `plugin_commit`、`installed_plugin_version`、`remote_plugin_version`、`skill_cache_version` 和 `plugin_version_check` 检查结果；补丁包还会同步写入实现来源（implementation origin），例如 `codex`、`manual`、`external` 或 `mixed`。服务器上传入口只做轻量接收并写入上传分支（intake branch）；管理端本地推广入口用这些字段区分插件未更新、会话缓存未刷新、旧包不再兼容或版本证据缺失。

生成前门禁仍按最新插件和当前会话缓存判断；处理历史上传包时按共享规则层的 source version compatibility matrix 判断生成时能力，不要求旧包的 `plugin_version` / `skill_version` 等于处理时最新插件版本。显式 `SESSION_CACHE_STALE` 或 `plugin_version_check.blocking=true` 仍表示当次生成/上传应被阻止。

生成出的上传包还会做基础文本质量和时间检查。`summary`、补证原因、案例标题、问题和方案摘要不能包含连续问号乱码（garbled question marks）；如果出现这类文本，说明生成阶段已经损坏，必须重新生成，不能上传。包的 `run_id` 也不能晚于服务器当前时间；如果服务器提示未来上传时间（future upload timestamp），先同步本机时间并更新整个插件（plugin update），再重新生成和上传。

日报包（daily report package）和补丁包（patch package）会携带成员侧知识搜索使用证据（search usage evidence）。Codex 正常开发流程应在开发前执行开发前知识搜索（pre-change knowledge search）；没有找到可用知识时也要记录未命中（not_found）。如果命中了知识搜索候选，local-check 会要求把未知（unknown）闭合为直接复用（reuse）、适配复用（adapt）、仅作参考（reference_only）、不适用（not_applicable）或未命中（not_found）。如果开发前搜索事实没有发生，成员上传技能会如实保留 `searched=false` 并给出警告，不要求成员补造搜索；后续由管理端本地技能执行沉淀前重叠检索（post-change overlap check），且不获得搜索闭环加分。手动实现（manual implementation）、外部实现、历史材料、混合实现或未知来源也不能事后伪造开发前搜索。捕获包（patch capture package）里只有未知（unknown）时，只能用和当前功能锚点匹配的当天搜索记录补齐；同一成员同一天并不足以关联。这些值只说明开发时如何使用搜索结果，不是沉淀结论（curation decision）。

## 典型场景

- 每天下班前，Codex 自动汇总当天会话、源码改动、候选 patch、失败路径、阻塞点和验证结果，生成日报/周报 `pending`（待检查包）；只有已验证的功能级补丁包才进入普通补丁上传。
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

旧命令路由生成当天 pending 包：

```bash
python3 "scripts/android_knowledge_intake.py" --profile <member_alias> daily --prepare
```

提交最新 pending 包：

```bash
python3 "scripts/android_knowledge_intake.py" --profile <member_alias> daily --submit-latest
```

旧命令路由生成周报 pending 包：

```bash
python3 "scripts/android_knowledge_intake.py" --profile <member_alias> weekly --prepare
```

显式重传同一天日报：

```bash
python3 "scripts/android_knowledge_intake.py" --profile <member_alias> daily --prepare --replace-daily-run-id 20260629-210000-daily
```

显式重传同一周期周报：

```bash
python3 "scripts/android_knowledge_intake.py" --profile <member_alias> weekly --prepare --replace-weekly-run-id 20260618-090102
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

成员查看界面如果提示某个补丁包需补证据（needs_evidence），不要新建第四类上传包。成员端 Codex 应使用成员补丁入口（android-framework-patch-intake），并按缺口分流：项目、平台、Android 版本、验证、风险和回滚等缺口只补真实证据并关联原始上传包；补丁资产修正（patch asset correction）才需要先重新采集补丁资料包；无共同目标聚合包（aggregate package）不补证，必须按功能重新上传新的原始包（original package）。

补证包必须关联最初被打回的原始上传包。`--supplement-for-package-key` 不能指向另一个补证包；如果目标 run id 看起来是 `verification-supplement`、`project-supplement` 等补证包，先找原始包键。原始包如果是无共同目标聚合包、日期合集或功能边界过宽，不继续套补证包，而是按功能上传新的原始补丁包。

证据补齐型补证示例：

```bash
python3 "scripts/android_knowledge_intake.py" --profile <member_alias> patch --prepare --patch-package /path/to/.codex/patch-packages/20260612-171820-feature --project "TVE1067M" --platform mtk --android-version 16 --summary "功能补丁摘要" --status validated --supplement-for-package-key 20260612/lincong/20260612-172836-patch --supplement-reason "补充项目（project）、平台（platform）和 Android 版本（Android version）证据"
```

该命令仍生成 `framework_change` 上传包，只是额外携带 `materials/evidence/evidence_supplement.json`，用于说明它补充哪个原始上传包。

补证包会先做本地校验。如果 `--supplement-reason` 说明在补项目（project）、平台（platform）、Android 版本（Android version）或验证（verification），新包不能继续保留对应的 `unknown`、缺失或未验证状态：补项目时必须有可追溯 `TVD`/`TVE`/`TVA`/`TVI` 项目和 `project_inference` 依据；补平台或 Android 版本时对应字段不能为 `unknown`，必要时使用显式 `--platform` 和 `--android-version`；补验证时 `verification_result` 必须为 `PASS`，且必须是设备验证或带理由、覆盖范围和剩余风险的等价验证，静态补丁审查不能闭合验证缺口。如果缺口是开发前知识搜索（pre-change knowledge search），但事实是手动实现或开发前没有搜索，成员不能补造搜索；应记录实现来源，交给管理端本地技能做沉淀前重叠检索（post-change overlap check）。

如果缺口是补丁资产修正（patch asset correction），成员端 Codex 必须从干净工作树重新运行补丁采集技能（android-framework-patch-capture），再通过成员补丁入口（android-framework-patch-intake）关联原始包上传补证包。README 里的“关键符号”“字符串资源”等清单不能用来证明污染项属于当前功能；本地校验只把功能目标和修改说明作为范围依据。如果补证包仍包含大量与功能目标无关的资源、设置、属性或日志锚点，会在上传前失败。

补丁资产修正补证必须使用 `--patch-package <capture package dir>`。直接 `--patch`、复制旧 patch 或手写说明不能证明已经从干净源码工作树重新采集；本地校验会停止上传。

结构化证据不能残留无关模板文本。比如补丁摘要、补丁文件名和修改文件都指向 E-Ink/显示模式时，`case.json` 或 `patch_problem_summary` 里不能出现 CameraService、Camera2、相机预览、拍照、扫码等相机模板内容。出现这种情况必须重新生成补丁说明和问题/方案证据，不能上传。

`--project` 只有包含 `TVD`/`TVE`/`TVA`/`TVI` 公司项目号时才作为高优先级项目名。对 capture 包，intake 还会读取 capture manifest/patch item、`source_root`、repo 路径、git 分支/remote、WSL source-access registry、功能 README/diff/summary，以及显式关联的日报/周报上下文来识别项目；泛化标签不会写入 `manifest.project`。结构化项目字段只保存规范项目型号；分支、客户、业务、模块、构建或中文描述等规范外尾随内容只进入 `project_inference` 证据，不能进入 `manifest.project`。

如果这些来源识别出多个不同项目（project）候选，成员上传技能不会任选一个写入包，而是写成 `project=unknown`，在 `project_inference.candidates` 保留全部候选，并把冲突写进 `project_inference.limits`。即便成员传入 `--status validated`，这类包也会降为候选（candidate）；候选包不能普通上传，成员需要先补齐项目边界并重新生成已验证补丁包，或按成员查看界面给出的原始包键上传已验证补证包（evidence supplement package）。

补丁包的平台（platform）只允许 `mtk`、`rk`、`unisoc` 或 `unknown`。`android14`、`app15` 这类前缀不能写成平台，只能在数字可信时作为 Android 版本线索；平台未知的补丁包可以被服务器归档，但管理端本地沉淀技能必须把它作为需补证据处理。补证时如果补丁捕获包或文件名不能证明平台和 Android 版本，可以通过 `--platform mtk|rk|unisoc|unknown` 和 `--android-version <number>` 显式写入边界字段。

如果这个补丁包明确来自某个 `daily_trace` 或 `weekly_trace` 上传包，显式带上 run id，后续 AI 知识闭环会用它做确定性关联。没有显式 run id 时，补丁包生成会尝试读取同一成员同一天的日报包（daily report package）；只有日报上下文里能识别出唯一 `TVD`/`TVE`/`TVA`/`TVI` 项目时，才自动继承项目（project）并写入 `related_report_run_ids`。如果日报缺失、多项目或冲突，仍保持 `project=unknown` 并交给补证包（evidence supplement package）闭合。`weekly_trace` 只能作为背景关联，周报包本身固定仅归档：

```bash
python3 "scripts/android_knowledge_intake.py" --profile <member_alias> patch --prepare --patch-package /path/to/.codex/patch-packages/20260526-120000-patch --summary "功能补丁摘要" --status candidate --related-report-run-id 20260601-210000-daily
```

只有直接指定单个独立 patch 文件时才使用 `--patch /path/to/*.patch`。多个原始 patch 文件不能直接塞进一个上传包；必须先用补丁采集技能（android-framework-patch-capture）按功能生成补丁包（patch package），再用 `--patch-package` 提交。补丁包（patch package）的单位是功能，不是日期；“今日补丁合集”或一个包包含多个独立功能会在本地校验失败，不设补丁数量例外，需要拆成多个新的原始包。已经生成的日期聚合包不要继续补证，应重新按功能生成并分别上传。

管理员需要验证协议和服务器链路时，才使用临时合成测试 profile。普通成员不要用测试 profile 提交日报、周报或 patch。

## 文件入口

- [SKILL.md](../../../../plugins/android-framework-ops/skills/android-knowledge-intake/SKILL.md)：给 Codex 自动加载的执行说明。
- [config.example.toml](../../../../plugins/android-framework-ops/skills/android-knowledge-intake/config.example.toml)：成员本机配置示例，使用服务器上传入口和知识库仓库字段。
- [references/member-migration-prompt.md](../../../../plugins/android-framework-ops/skills/android-knowledge-intake/references/member-migration-prompt.md)：成员首次启用提示词，覆盖插件更新、新配置、服务器上传入口和知识库仓库健康检查。
- [references/incoming-package-protocol.md](../../../../plugins/android-framework-ops/skills/android-knowledge-intake/references/incoming-package-protocol.md)：`incoming` 提交目录规则。
- [references/patch-package-status-rules.md](../../../../plugins/android-framework-ops/skills/android-knowledge-intake/references/patch-package-status-rules.md)：补丁包状态和上传策略。
- [references/android-framework-patch-rules.md](../../../../plugins/android-framework-ops/skills/android-knowledge-intake/references/android-framework-patch-rules.md)：Android Framework patch 规范。
- [scripts/android_knowledge_intake.py](../../../../plugins/android-framework-ops/skills/android-knowledge-intake/scripts/android_knowledge_intake.py)：共享生成和提交内核；拆分后的日报、周报和补丁入口都调用它。
