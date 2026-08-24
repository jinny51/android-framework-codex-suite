# android-daily-report-intake

> GitHub 说明页。Runtime skill 文件位于 [../../../../plugins/android-framework-ops/skills/android-daily-report-intake](../../../../plugins/android-framework-ops/skills/android-daily-report-intake)。

成员个人日报入口。它只负责生成、替换、检查和提交日报包（daily report package），并复用 `android-knowledge-intake` 的共享脚本和上传协议。

日报回答“今天干了什么、怎么干的、结果是什么”。新日报包生成：

- `reports/daily.md`
- `materials/display/report_view.json`
- `materials/evidence/work_findings.json`

`report_view.json` 是同一份日报正文的 UI 读模型。五个分类固定为 `Patch`、`App`、`GMS`、`Doc`、`Other`。Patch/App/GMS 项目行保留项目和客户链；独立 Doc/GMS/Other 行使用具体 `document_name` 或 `work_name`，不伪造项目或客户。历史 `Document` 兼容读取为 `Doc`。每个范围都包含 `today_topic`、`current_result`、`work_items[]` 和 `tomorrow_focus[]`。

日报卡片不使用日期当标题。`material_name` 写项目 + 客户链路，例如 `TVE1086U（青鸾云）` 或 `TVE1091U（AOC → 福建移动高清）`；多项目时每个项目都带自己的客户链路。`material_summary` 写今日主题，例如 `TVE1086U：今日处理锁屏鼠标位置刷新、云电脑崩溃排查。`。新包不得再写已废弃的 `report_view` 字段，例如 `display_title`、`ui_card`、`one_line_summary`、顶层 `work_items`、`risks` 或 `outputs`。

日报项目行必须同时有公司项目名和直接客户。成员可以说 `TVE1086U 青鸾云`，也可以说 `TVE1091U AOC 福建移动高清`；后者识别为项目 `TVE1091U`、直接客户 `AOC`、客户的客户 `福建移动高清`。直接客户和下游客户不得跨层当作别名。缺项目或直接客户时提交会被本地校验拦住。

Codex 优先采用成员明确分类，否则根据源码、产物和工作语义进行高置信度判断；只有冲突或名称缺失时才询问。GMS 可表示正式项目测试或独立测试环境，Doc 表示独立文档，Other 表示其余具体工作。存在处理中、待验证或阻塞事项时，该范围必须填写明日重点。

正常生成先由共享内核自动识别并按范围绑定工作项。`$CODEX_HOME/artifacts/android-knowledge-intake/daily-facts/` 下的 `akbs-daily-work-facts-v2` 只用于补齐未决字段、纠正判定或记录成员显式覆盖；显式事实优先于自动判定。一个混合会话若不能可靠绑定各事项，必须补齐范围事实，不得猜测拆分。

`reports/daily.md` 中项目名每次出现都加粗，不限于项目标题；只加粗项目名，例如 `**TVE1091U** AOC 福建移动高清`，客户链保持普通文字。`report_view.json` 是结构化数据，项目及摘要字段不写 Markdown 标记。

日报按独立事项拆分同一会话中的多项工作，并合并不同会话里重复推进的同一事项。`怎么做的`来自授权会话中的实际排查、修改、构建、部署或验证信息；命令只转换成方法摘要，不展示原始命令，也不再使用“根据 Codex 会话记录整理”之类固定套话。

Markdown、`report_view.json` 和日报事实由 `report_render_binding` 绑定。只手改其中一份会导致校验失败；应修改结构化事实后重新生成。`--prepare` 本地校验失败时返回非零，`--submit-latest` 在 HTTP 前再次执行相同校验。

执行生成或提交前，Codex 应先从当前请求和可见会话上下文里找项目名 + 直接客户；找不到时只要求成员补这两个最小字段，并提示正确流程：`当前会话未关联项目，请补充项目名和客户名。例如：TVE1086U 青鸾云；如有客户的客户：TVE1091U AOC 福建移动高清。建议后续先创建项目，再在项目下创建开发会话。` 不要把项目角色、需求时间、需求来源、项目总量或剩余量等周报字段塞进日报追问。

成员本次明确要求生成日报，只授权本次日报日期和本次选择的派生字段。默认使用 `work_summary`、`command_summary`、`project_hint` 和 `work_scope_hint`，以便提取工作内容、处理方法和安全的源码范围提示；原始路径不进入报告或证据文件。只有确有需要时才增加 `patch_discovery`，且它要求 `project_hint`。没有本次明确请求时，必须在读取 session、打包和 HTTP 前停止；不得复用旧授权或给定时任务长期授权。

常用命令：

```bash
python3 "<android-knowledge-intake skill>/scripts/android_knowledge_intake.py" --profile <member_alias> daily --session-consent --session-field work_summary --session-field command_summary --session-field project_hint --session-field work_scope_hint --prepare
python3 "<android-knowledge-intake skill>/scripts/android_knowledge_intake.py" --profile <member_alias> daily --submit-latest
python3 "<android-knowledge-intake skill>/scripts/android_knowledge_intake.py" --profile <member_alias> daily --session-consent --session-field work_summary --session-field command_summary --session-field project_hint --session-field work_scope_hint --daily-facts "$CODEX_HOME/artifacts/android-knowledge-intake/daily-facts/<report-date>.json" --prepare
python3 "<android-knowledge-intake skill>/scripts/android_knowledge_intake.py" --profile <member_alias> daily --session-consent --session-field work_summary --session-field command_summary --session-field project_hint --session-field work_scope_hint --prepare --replace-daily-run-id <old_run_id>
```
