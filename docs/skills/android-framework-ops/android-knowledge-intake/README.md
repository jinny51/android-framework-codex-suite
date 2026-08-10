# Android Knowledge Intake

`android-knowledge-intake` 是成员 incoming 的唯一共享内核，负责首次启用、当前配置、doctor、插件版本门禁、包生成底层命令、上传前校验和 AKBS HTTP 上传。

成员日常使用三个业务入口：

- 日报：`android-daily-report-intake`
- 周报：`android-weekly-report-intake`
- 完整补丁包和按 `request_id` 执行的同包队列资料补充：`android-framework-patch-intake`

三个入口都调用本 skill 的同一套脚本，不各自复制上传实现。知识沉淀、新建/合并判断和知识有效度不属于成员插件。

## 首次启用

使用 [member-setup-prompt.md](../../../../plugins/android-framework-ops/skills/android-knowledge-intake/references/member-setup-prompt.md)。提示词让成员端 Codex 完成：

1. 从 Codex 插件市场更新 `android-framework-ops` 和当前操作系统的平台插件。
2. 检查当前会话是否仍加载旧缓存；无法热刷新时停止生成和上传。
3. 写入只包含成员身份和本地路径的当前配置；成员不配置或保存上传 token。
4. 运行 `doctor --strict --check-remote`，确认 member_alias 已配置，服务器将按固定来源 IP 验证身份。

普通成员不维护服务器地址、SSH 上传命令或数据库路径。AKBS endpoint resolver 提供 HTTP 上传入口；上传、搜索和合并确认只发送 member alias，服务器按固定来源 IP 验证身份。成员不得发送 token、session cookie、role 或客户端 IP 声明。

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

检查内容包括成员身份、允许模式、产物目录、HTTP 上传入口、固定 IP 身份状态、插件安装版本、远端版本和当前会话缓存版本。缺 alias 时会在本地失败，且不会打包或发出 HTTP 请求。

## 逐成员自然观察

插件发布后，每位成员从已映射工作站完成一次真实 search 与一次正常业务 upload；确认 HTTP 成功、package/member 归属正确、没有 token 提示或存储，并从错误来源 IP 验证服务会拒绝请求。本插件发布不伪造这些生产业务包。

## 共享命令

业务 skill 调用以下底层命令：

```bash
python3 scripts/android_knowledge_intake.py --profile <member_alias> daily --session-consent --session-field work_summary --prepare
python3 scripts/android_knowledge_intake.py --profile <member_alias> weekly --session-consent --session-field work_summary --prepare
python3 scripts/android_knowledge_intake.py --profile <member_alias> patch --prepare --patch-package <capture-dir>
```

`--upload` 生成并上传，`--submit-latest` 上传最近一个已准备包。日报按日期、周报按周周期保持唯一；替换必须显式提供被替换的运行编号。`--prepare` 本地校验失败时返回非零，上传与提交都会在 HTTP 前重新校验。

日报要求成员确认每个范围的 `Patch` 或 `App` 类型，App 还必须提供 App 名称。Codex 将范围写入 `$CODEX_HOME/artifacts/android-knowledge-intake/daily-facts/` 下的 `akbs-daily-project-facts-v1`，再用 `--daily-facts <path>` 生成。同一项目可包含一个 Patch 和多个不同 App；日报不填写项目角色、需求来源或数量台账。

周报生成优先消费 AKBS 当前有效日报和上一周项目台账，离线时只读取本机 submitted 替换链的当前叶节点；session 仅作补充，不参与需求总量口径。每个周报包写 `weekly_fact_sources` 证据，事实缺口会阻止上传。Codex 应只向成员追问缺失字段，生成 `akbs-weekly-project-facts-v3` artifact 后用 `--weekly-facts <path>` 重新生成。旧`定制`数量不能自动拆成`需求`和`移植`。

周报的`类型`只允许 `Patch` 或 `App`。同一公司项目保持一条客户链，但可以有一个 Patch 和多个不同 App；App 必须填写 App 名称。门禁按“项目 + 客户 + 类型 + App 名称（仅 App）”校验统计对象唯一性，以及展示身份与来源证据的一致性；冲突会在 HTTP 前失败。无下周动作时使用空计划数组，不渲染“无”占位项目块。

日报和周报的 Markdown、`report_view.json` 与结构化事实由 `report_render_binding` 绑定。本地校验还会从 `report_view.json` 确定性重渲染 Markdown 并要求完全一致；不得只手改其中一份。

真实日报或周报的生成必须来自成员本次明确请求，并通过 `--session-consent` 和最小 `--session-field` 集合授权。本次日期或周范围就是授权时间窗；授权不写入 profile，也不能跨运行或定时任务复用。缺少授权时脚本在读取 session、创建包和 HTTP 前失败。包内只保留最小 source session ID、时间窗、consent version/fields 和 retention policy，不复制 thread 名、cwd、原始消息或原始命令。

日报和周报必须在生成阶段识别项目名和客户名。无法识别时，Codex 应在会话中提示成员补充，例如 `TVE1086U 青鸾云`；未补齐的包可以保留在本地，但上传前必须拒绝。

补丁上传必须是一个 `validated` 补丁包，并具备共同功能边界、项目、平台、Android 版本、干净不可变补丁和 PASS 验证。`implementation_origin` 记录代码作者，`workflow_contract` 记录当前 Codex + Skill 流程或真实导入流程；两者不能互相推断。直接 `--patch` 默认当前工作流，旧采集包或既有代码导入必须显式使用 `--workflow-contract manual_import|historical_import`。服务端 `patch_package_id` 是队列和主分支唯一业务身份，`package_key` 只标识上传来源。队列轻量缺口通过 `--inspect-information-request` 与 `--complete-information-request` 按因果 `request_id` 补到同一主体；提交后进入 `information_review`，需要改补丁或拆分功能时重新采集补丁包。

## 版本证据

生成前门禁比较：

- 当前运行脚本版本
- 本机已安装插件版本
- 当前会话 skill 缓存版本
- GitHub marketplace 版本

生成包在 `materials/evidence/source.json` 记录这些版本和检查结果。发现新版时可自动刷新磁盘缓存；当前会话无法热加载时停止本次生成或上传。

## 规则归属

项目、平台、Android 版本、共同功能目标、开发前搜索、搜索使用决策、文本质量和补丁资产完整性规则来自 `android_framework_ops.knowledge_rules`。服务端按公开包合同做独立安全复核；本地 `akbs-curation-maintainer` 只负责入库后的沉淀判断。

详细合同：

- [incoming-package-protocol.md](../../../../plugins/android-framework-ops/skills/android-knowledge-intake/references/incoming-package-protocol.md)
- [deterministic-rules-contract.md](../../../../plugins/android-framework-ops/skills/android-knowledge-intake/references/deterministic-rules-contract.md)
- [report-rules.md](../../../../plugins/android-framework-ops/skills/android-knowledge-intake/references/report-rules.md)
- [android-framework-patch-rules.md](../../../../plugins/android-framework-ops/skills/android-knowledge-intake/references/android-framework-patch-rules.md)
- [patch-package-status-rules.md](../../../../plugins/android-framework-ops/skills/android-knowledge-intake/references/patch-package-status-rules.md)
