# android-daily-report-intake

> GitHub 说明页。Runtime skill 文件位于 [../../../../plugins/android-framework-ops/skills/android-daily-report-intake](../../../../plugins/android-framework-ops/skills/android-daily-report-intake)。

成员个人日报入口。它只负责生成、替换、检查和提交日报包（daily report package），并复用 `android-knowledge-intake` 的共享脚本和上传协议。

日报回答“今天干了什么、怎么干的、结果是什么”。新日报包生成：

- `reports/daily.md`
- `materials/display/report_view.json`
- `materials/evidence/work_findings.json`

`report_view.json` 是同一份日报正文的 UI 读模型（UI read model），使用 `schema=akbs-report-view-human-v1`，至少包含 `report_type=daily`、`report_date`、`display_date`、`material_name`、`material_summary`、`member_alias`、`member_name` 和 `projects[]`。每个项目行包含 `project`、直接客户 `customer`、可选的客户的客户 `downstream_customer`、`today_topic`、`current_result`、`work_items[]` 和 `tomorrow_focus[]`。每个工作项包含 `name`、`did[]`、`how[]`、`result` 和 `status`；`status` 只能是 `已完成`、`处理中`、`待验证` 或 `阻塞`。它不是 AI 证据层，也不改变日报只归档的性质。

日报卡片不使用日期当标题。`material_name` 写项目 + 客户链路，例如 `TVE1086U（青鸾云）` 或 `TVE1091U（AOC → 福建移动高清）`；多项目时每个项目都带自己的客户链路。`material_summary` 写今日主题，例如 `TVE1086U：今日处理锁屏鼠标位置刷新、云电脑崩溃排查。`。新包不得再写已废弃的 `report_view` 字段，例如 `display_title`、`ui_card`、`one_line_summary`、顶层 `work_items`、`risks` 或 `outputs`。

日报项目行必须同时有公司项目名和直接客户。成员可以说 `TVE1086U 青鸾云`，也可以说 `TVE1091U AOC 福建移动高清`；后者识别为项目 `TVE1091U`、直接客户 `AOC`、客户的客户 `福建移动高清`。直接客户和下游客户不得跨层当作别名。缺项目或直接客户时提交会被本地校验拦住。

`reports/daily.md` 中项目名每次出现都加粗，不限于项目标题；只加粗项目名，例如 `**TVE1091U** AOC 福建移动高清`，客户链保持普通文字。`report_view.json` 是结构化数据，项目及摘要字段不写 Markdown 标记。

日报按独立事项拆分同一会话中的多项工作，并合并不同会话里重复推进的同一事项。`怎么做的`来自授权会话中的实际排查、修改、构建、部署或验证信息；命令只转换成方法摘要，不展示原始命令，也不再使用“根据 Codex 会话记录整理”之类固定套话。

执行生成或提交前，Codex 应先从当前请求和可见会话上下文里找项目名 + 直接客户；找不到时只要求成员补这两个最小字段，并提示正确流程：`当前会话未关联项目，请补充项目名和客户名。例如：TVE1086U 青鸾云；如有客户的客户：TVE1091U AOC 福建移动高清。建议后续先创建项目，再在项目下创建开发会话。` 不要把项目角色、需求时间、需求来源、项目总量或剩余量等周报字段塞进日报追问。

成员本次明确要求生成日报，只授权本次日报日期和本次选择的派生字段。默认使用 `work_summary` 和 `command_summary`，以便同时提取工作内容和处理方法；只有确有需要时才增加 `project_hint` 或 `patch_discovery`，其中 `patch_discovery` 还要求 `project_hint`。没有本次明确请求时，必须在读取 session、打包和 HTTP 前停止；不得复用旧授权或给定时任务长期授权。

常用命令：

```bash
python3 "<android-knowledge-intake skill>/scripts/android_knowledge_intake.py" --profile <member_alias> daily --session-consent --session-field work_summary --session-field command_summary --prepare
python3 "<android-knowledge-intake skill>/scripts/android_knowledge_intake.py" --profile <member_alias> daily --submit-latest
python3 "<android-knowledge-intake skill>/scripts/android_knowledge_intake.py" --profile <member_alias> daily --session-consent --session-field work_summary --session-field command_summary --prepare --replace-daily-run-id <old_run_id>
```
