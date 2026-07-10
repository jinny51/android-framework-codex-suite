# 成员首次启用提示词

把下面整段交给成员端 Codex。成员只需要提供自己的成员标识和姓名；插件安装、当前配置和健康检查由 Codex 执行。

```text
你现在要帮我完成 Android Framework Ops incoming 上传材料的首次启用。

强制要求：
- 全程用中文说明；英文定义放在中文后面的括号中。
- 只向我确认 member_alias、member_name 和 Git 用户名/邮箱。
- 成员上传使用 AKBS HTTP API，由 AKBS endpoint resolver 提供入口；不要让我维护服务器名、服务器路径、上传脚本或数据库地址。
- 知识搜索优先调用 AKBS API；本地知识工作树只作为已经存在时可用的离线兜底。

请按顺序执行：

1. 完成插件更新（plugin update），安装当前 WSL 应使用的插件：
   codex plugin marketplace upgrade android-framework-codex-suite
   codex plugin add android-framework-ops@android-framework-codex-suite
   codex plugin add android-wsl-ops@android-framework-codex-suite

   macOS 环境把 android-wsl-ops 换成 android-mac-ops。不要在同一台机器同时安装 WSL 和 Mac 平台插件。

2. 更新后检查当前会话加载的 skill 版本。如果当前会话仍显示更新前的缓存路径，停止生成或上传，并明确告诉我需要新开 Codex 会话。不要用旧会话继续。

3. 写入当前配置（current configuration），创建或覆盖 $CODEX_HOME/report/config.toml：

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

4. 找到当前 android-knowledge-intake skill 中的脚本：
   scripts/android_knowledge_intake.py

5. 检查服务器上传入口（server upload endpoint）并运行健康检查：
   python3 "<android_knowledge_intake.py>" --profile <member_alias> doctor --strict --check-remote

6. 健康检查失败时，只修复报告中的当前问题并重跑。检查通过前不要生成日报、周报或补丁包。

7. 如果 $CODEX_HOME/worktrees/knowledge 已经存在，确认它是可读的本地离线搜索索引；不存在时不创建、不克隆，也不影响 AKBS API 搜索和上传。

完成后告诉我：
- 插件安装版本和当前会话缓存版本
- 当前配置写入状态
- AKBS HTTP 上传入口状态
- 可选本地离线搜索路径状态
- doctor --strict --check-remote 结果
```
