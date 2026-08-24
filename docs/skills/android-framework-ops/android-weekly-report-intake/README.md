# android-weekly-report-intake

> GitHub 说明页。Runtime skill 文件位于 [../../../../plugins/android-framework-ops/skills/android-weekly-report-intake](../../../../plugins/android-framework-ops/skills/android-weekly-report-intake)。

成员个人周报入口。它只负责生成、替换、检查和提交周报包（weekly report package），并复用 `android-knowledge-intake` 的共享脚本和上传协议。成员侧不生成、不理解团队汇总报告；管理端汇总是管理员侧能力。

周报回答“这一周完成多少、还剩多少、风险和依赖是什么”。日报记录当天做了什么、怎么做、结果是什么；周报不复述每天流水，只做一周总结。新周报包生成：

- `reports/weekly.md`
- `materials/display/report_view.json`
- `materials/evidence/work_findings.json`
- `materials/evidence/weekly_fact_sources.json`

周报统计周期固定为周一至周日，起止日期都纳入统计；补交日期不改变日报所属日期，也不能导致周一日报被漏掉。周报事实优先读取 AKBS 中本周当前有效日报和上一周当前有效周报；API 不可用时回退到本机 `submitted` 包，并按替换链只选补交后的叶节点。Codex session 只补充有效日报未覆盖的事项，不能再把“一段会话”统计成“一项需求”。跨日长会话按消息日期和文件活跃时间补扫。

当前日报已携带由工作证据自动判定或成员确认的 Patch/App 项目范围、App 名称或独立 Document 文档范围，周报按该范围归并，不再根据事项文字重新猜类型。旧日报缺少范围字段时仍可读取，但不能证明周报类型，必须由成员补齐。

如果类型、App 名称（仅 App）、文档名称（仅 Document）、项目角色、需求时间、需求来源、主责总量、项目流转或剩余事项身份仍缺失，本地检查会列出准确字段并阻止上传。成员只确认缺失事实，Codex 将其写入 `$CODEX_HOME/artifacts/android-knowledge-intake/weekly-facts/` 下的 `akbs-weekly-work-facts-v5` JSON，再通过 `--weekly-facts <path>` 重新生成；不要求成员手改 JSON 或 Markdown。v5 显式事实必须绑定上一份有效周报，不能绕过上周台账重新填写总量。

`report_view.json` 是同一份周报正文的 UI 读模型（UI read model），使用 `schema=akbs-report-view-human-v1`，至少包含 `report_type=weekly`、`week_range`、`display_date`、`material_name`、`material_summary`、`member_alias`、`member_name`、`projects[]` 和 `documents[]`。项目行保留 Patch/App 项目台账；文档行使用 `work_type=Document`、`document_name`、完成/剩余数量和详情数组，不填写项目、客户、项目角色或需求字段。Document 数量不并入项目需求统计。周报包只归档，不进入知识库沉淀候选。

`类型`只允许 `Patch` 或 `App`。Patch 按“项目 + 直接客户”形成一个统计对象；App 再加 `App 名称`形成统计对象。同一公司项目可以有一个 Patch 和多个不同 App，但不得重复同一 Patch 或同一 App。普通功能名称写在完成项、剩余项或下周计划中。没有下周动作时 `next_week_plan` 使用空数组，Markdown 不显示该统计对象的计划块，不用“无”占位。生成和 `--submit-latest` 都会在 HTTP 前重新执行这些校验。

Patch 不再保留“定制”父分类，直接使用需求、移植和 Bug：以前没做过的客户需求计需求，以前做过并复用或移植的客户需求计移植，缺陷处理计 Bug。BSP 是责任状态而不是事项类型；转 BSP 后保留原需求/移植/Bug 分类，从 Android 当前剩余中扣除，并单独显示 `BSP 跟踪`。App 使用简单总量、完成量和剩余量，不套用 Patch 分类；两类数量不得相加。

成员周报以项目块为基线。主责负责新项目初始总量及后续新增、重新打开、无需修改关闭、移出、转 BSP 和 BSP 关闭；协作只报个人完成和个人剩余，不能修改项目总账。Markdown 只增加一行紧凑的 `本周变化`，总量、Android 当前剩余和 BSP 跟踪由上周基线自动计算。`需求来源`只允许 `CR`、`TL`、`PM`、`TE`、`BSP`。`项目详情`依次写 `1. 本周完成`、`2. 当前剩余`、`3. 重点说明`、`4. 风险 / 依赖`；最后写 `下周计划`。多项目时重复同一项目块，不用大表格堆字段。

`reports/weekly.md` 中项目名每次出现都加粗，包括概况正文、完成项、剩余项、风险、依赖和下周计划，不只处理标题；只加粗项目名，客户链保持普通文字。`report_view.json` 的项目与摘要字段保持纯文本，不写 Markdown 标记。

Markdown、`report_view.json` 和周报事实由 `report_render_binding` 绑定。只手改其中一份会导致校验失败；应修改结构化事实后重新生成。`--prepare` 本地校验失败时返回非零，提交前还会再次执行相同校验。

周报卡片不使用周范围当标题。`material_name` 写项目 + 客户链路，例如 `TVE1086U（青鸾云）` 或 `TVE1091U（AOC → 福建移动高清）`；多项目时每个项目都带自己的客户链路。`material_summary` 写各项目本周完成、剩余、风险或依赖，例如 `TVE1086U：本周完成 5 项，剩余 3 项，有风险。`。

执行生成或提交前，Codex 应先从当前请求和可见会话上下文里找项目名 + 直接客户；找不到时先在会话里提示 `缺少项目名和客户名，请补充，例如：TVE1086U 青鸾云；如有客户的客户，继续写第三段，例如：TVE1091U AOC 福建移动高清。`，不要直接跑命令。

成员本次明确要求生成周报，只授权本次周范围和本次选择的派生字段。最小范围使用 `--session-consent --session-field work_summary`；只有确有需要时才增加 `project_hint`、`command_summary` 或 `patch_discovery`，其中 `patch_discovery` 还要求 `project_hint`。没有本次明确请求时，必须在读取 session、打包和 HTTP 前停止；不得复用旧授权或给定时任务长期授权。

常用命令：

```bash
python3 "<android-knowledge-intake skill>/scripts/android_knowledge_intake.py" --profile <member_alias> weekly --session-consent --session-field work_summary --prepare
python3 "<android-knowledge-intake skill>/scripts/android_knowledge_intake.py" --profile <member_alias> weekly --submit-latest
python3 "<android-knowledge-intake skill>/scripts/android_knowledge_intake.py" --profile <member_alias> weekly --session-consent --session-field work_summary --prepare --replace-weekly-run-id <old_run_id>
python3 "<android-knowledge-intake skill>/scripts/android_knowledge_intake.py" --profile <member_alias> weekly --session-consent --session-field work_summary --weekly-facts "$CODEX_HOME/artifacts/android-knowledge-intake/weekly-facts/<week>.json" --prepare
```
