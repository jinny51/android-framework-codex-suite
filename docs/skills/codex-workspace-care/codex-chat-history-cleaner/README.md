# Codex Chat History Cleaner

> GitHub 说明页。Runtime skill 文件位于 [../../../../plugins/codex-workspace-care/skills/codex-chat-history-cleaner](../../../../plugins/codex-workspace-care/skills/codex-chat-history-cleaner)；插件安装后的 skill 目录不包含本 README。文中的 `scripts/...`、`references/...` 指向该 runtime skill 目录。

这是一个用于检查、修复和清理本地 Codex 聊天历史状态的 Codex skill。

它存在的原因是：WSL 里的 Codex agent 不能直接使用 Codex 桌面端自带的归档/删除 UI 控件。这个 skill 先在 Codex 内读取 UI 可见会话并生成 dry-run 计划；用户确认后，退出 Codex 桌面端，再从外部 WSL/PowerShell 执行脚本清理本地状态文件，避免 `.codex-global-state.json` 被运行中的桌面端内存状态写回。

它适用于排查和清理归档会话、搜索索引残留、聊天记录文件、SQLite 外键孤儿记录、重复 workspace root，以及“清理过程本身又被当前会话记录下来，后续又被搜出来”的情况。

## 典型场景

- 用户删除或归档了 Codex 会话，但搜索结果里仍然能看到历史痕迹，需要检查本地索引和缓存。
- Codex 更新或启动时曾经出现 SQLite migration、foreign key、disk I/O 相关报错，需要做本地状态健康检查。
- 准备共享机器或清理隐私数据前，需要确认哪些 Codex 历史记录仍保存在本地。
- 需要安全清理归档残留、搜索索引残留，或当前清理记录又被搜出来的痕迹。
- 只保留 Codex UI 当前可见会话，并清掉 UI 不再显示的本地 DB/index/transcript/global-state 残留。

## 包含内容

- `SKILL.md`：给 Codex 自动加载的执行说明和安全边界。
- `scripts/clean_codex_history.py`：确定性的清理脚本。默认只做 dry-run 检查，只有传入 `--execute` 才会修改文件；UI 保留集模式会保留可见会话和其关联子智能体，删除 UI 不再显示的本地残留。
- `references/privacy.md`：发布或分享清理流程前的隐私检查清单。
- `agents/openai.yaml`：Codex skill 展示和触发所需的元数据。
- `.gitignore`：防止误提交本地 Codex 状态、聊天记录、认证文件、数据库、截图和备份文件。

## 使用示例

最常用：清理归档会话，并修复可能影响 SQLite 更新的状态残留。先预览：

```bash
python3 scripts/clean_codex_history.py --codex-home "$HOME/.codex" --archived-sqlite-cleanup --dry-run
```

确认后执行：

```bash
python3 scripts/clean_codex_history.py --codex-home "$HOME/.codex" --archived-sqlite-cleanup --execute
```

只检查，不做任何清理计划：

```bash
python3 scripts/clean_codex_history.py --codex-home "$HOME/.codex" --dry-run --summary
```

按 Codex UI 可见会话生成保留集清理计划。先在 Codex 内 dry-run，只列计划：

```bash
python3 scripts/clean_codex_history.py --codex-home "$HOME/.codex" \
  --delete-not-in-keep --keep-ids THREAD_ID... --dry-run --summary
```

用户确认后，完全退出 Codex 桌面端，再从外部 WSL/PowerShell 执行：

```bash
python3 scripts/clean_codex_history.py --codex-home "$HOME/.codex" \
  --delete-not-in-keep --keep-ids THREAD_ID... \
  --execute --require-codex-exited-for-global-state --summary
```

`--delete-not-in-keep` 会保留 `--keep-ids` 以及这些父会话通过 `thread_spawn_edges` 关联的子智能体；不在保留集里的 DB 线程、搜索索引记录、归档残留和 thread-keyed global-state 会进入删除计划。

确认 dry-run 结果后，删除本地已归档的 Codex 会话：

```bash
python3 scripts/clean_codex_history.py --codex-home "$HOME/.codex" --all-archived --execute --summary
```

修复线程子表里的 SQLite 孤儿记录：

```bash
python3 scripts/clean_codex_history.py --codex-home "$HOME/.codex" --repair-thread-orphans --execute --summary
```

清理搜索索引和全局 workspace 状态里的 stale 记录：

```bash
python3 scripts/clean_codex_history.py --codex-home "$HOME/.codex" --clean-stale-index --clean-global-state --execute --summary
```

## 安全提醒

这个工具操作的是本地 Codex 状态文件。建议总是先运行 `--dry-run`，确认将要处理的范围后再执行。默认会在修改数据库、索引或全局状态前创建备份，除非你明确传入 `--no-backup`。

清理 `.codex-global-state.json` 前最好完全退出 Codex，否则运行中的 Codex 可能把运行中的内存状态重新写回文件。

如果目标是清掉搜索残留，尽量不要在新的清理对话里打印私密聊天标题、完整 thread ID 或本机绝对路径，否则当前清理对话可能会变成新的搜索命中。

如果目标是清理 UI 不再显示的会话，子智能体是否已 hydration 不参与删除判断：UI 可见父会话关联的子智能体一律保留。
