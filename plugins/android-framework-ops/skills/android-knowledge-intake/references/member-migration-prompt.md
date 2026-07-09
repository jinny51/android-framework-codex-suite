# 成员首次启用提示词

把下面整段交给成员端 Codex 使用。成员只需要提供自己的成员标识和姓名；插件更新、当前配置写入、仓库检查和健康检查都由 Codex 执行。

```text
你现在要帮我完成 Android Framework Ops incoming 上传材料的首次启用。

强制要求：
- 全程用中文说明；遇到英文定义时，先写中文，再把英文放在括号里，例如 数据库仓库（database repository）、知识库仓库（knowledge repository）、上传包（incoming package）、插件更新（plugin update）、当前配置（current configuration）。
- 不要让我手动理解或维护版本、配置字段、仓库路径。只有 member_alias、member_name、Git 用户名/邮箱需要向我确认。
- 成员端使用 Android Framework Ops 插件套件（plugin suite）生成和上传材料。
- 成员端通过 AKBS endpoint resolver 解析服务器上传入口（server upload endpoint）并发送上传包（incoming package）。当前 AKBS 默认使用 HTTP API。不要克隆、拉取、搜索或 push 数据库仓库（database repository）。
- 成员端用技能搜索（skill search）时优先调用 AKBS API；本地知识库仓库（knowledge repository）只作为离线兜底，可不配置。
- 成员查看 UI（member view UI）如果需要看本人提交记录，由服务器读取数据库仓库并按成员身份过滤，这不是成员本机 skill 的搜索入口。

请按顺序执行：

1. 先做插件更新（plugin update）。
   - 如果当前插件来自 android-framework-codex-suite 的 Git 仓库（git repository），找到仓库根目录并执行：
     git -C <android-framework-codex-suite> pull --ff-only
   - 如果当前插件来自 Codex 插件市场或缓存目录，先更新或重新安装 Android Framework Ops 插件，再继续后续步骤。
   - 更新后重新加载插件能力；如果本轮运行环境无法重新加载，就停止并告诉我重新打开一个 Codex 会话继续。

2. 找到成员端上传材料脚本（member-side intake script）：
   plugins/android-framework-ops/skills/android-knowledge-intake/scripts/android_knowledge_intake.py
   同目录还有配置迁移脚本（member config migration script）：
   plugins/android-framework-ops/skills/android-knowledge-intake/scripts/migrate_member_config.py

3. 如果 $CODEX_HOME/report/config.toml 已存在，先运行迁移脚本清理已废弃的 test35 / SSH / local 上传字段：
   python3 "<migrate_member_config.py>" --config "$CODEX_HOME/report/config.toml"
   迁移脚本只清理本地成员配置，不上传、不生成包、不修改服务器。

4. 直接创建或覆盖 $CODEX_HOME/report/config.toml，使用下面的当前配置。普通成员配置只写身份和本地路径，不写 server_profile、submission_ssh_host、submission_command 或 knowledge_repo_url；成员上传唯一入口是 AKBS HTTP API，由 AKBS endpoint resolver 提供。不解析残留配置字段，不把工作树放进 .codex/plugins/cache，不配置成员数据库仓库工作树。

   default_profile = "<member_alias>"

   [paths]
   codex_home = "$CODEX_HOME"
   out_dir = "$CODEX_HOME/artifacts/android-knowledge-intake"

   incoming_schema_version = "1"
   timezone = "Asia/Shanghai"

   [profiles.<member_alias>]
   member_alias = "<member_alias>"
   member_name = "<member_name>"
   role = "member"
   allowed_modes = ["daily", "weekly", "patch"]
   knowledge_repo_worktree = "$CODEX_HOME/worktrees/knowledge"
   git_user_name = "<member_name>"
   git_user_email = "<member_alias>@codex.local"
   synthetic_data = false

5. 可选：如果需要离线知识搜索兜底，成员端只克隆并更新知识库仓库（knowledge repository），不要克隆数据库仓库（database repository）。
   - 如果 $CODEX_HOME/worktrees/knowledge 不存在，可以先跳过；AKBS API 搜索仍可使用。
   - 如果 $CODEX_HOME/worktrees/knowledge 已经是 Git 仓库（git repository），执行：
     git -C "$CODEX_HOME/worktrees/knowledge" pull --ff-only
   - 如果该路径存在但不是 Git 仓库，先告诉我具体路径；这只影响本地兜底搜索，不应阻断 HTTP 上传。

6. 运行健康检查（doctor check）：
   python3 "<android_knowledge_intake.py>" --profile <member_alias> doctor --strict --check-remote

7. 如果健康检查（doctor check）失败，只修复报告里的具体问题，然后重跑第 6 步。不要生成日报（daily report）、周报（weekly report）或补丁包（patch package），直到健康检查通过。

8. 以后每次生成日报、周报或补丁包前，脚本会先检查 GitHub marketplace、本地插件缓存和当前会话技能缓存。发现新版时让脚本自动更新插件缓存并切到新版脚本继续执行；如果脚本明确提示当前 Codex 会话无法刷新技能缓存，就停止并告诉我需要新开或重启 Codex 会话。不要用过期插件继续生成上传包。

完成后告诉我：
- 插件更新（plugin update）状态
- 当前配置（current configuration）写入状态
- 服务器上传入口（server upload endpoint）状态
- 知识库仓库（knowledge repository）工作树路径
- 健康检查（doctor check）结果
```
