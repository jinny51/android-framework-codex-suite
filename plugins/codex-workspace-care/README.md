# Codex Workspace Care

Codex Workspace Care 是独立的本地工作区维护插件，用于检查、修复和清理 Codex 本地会话历史状态，并生成隐私友好的新窗口上下文交接材料。

它不属于 Android Framework 工程链路，因此不放进 `android-framework-ops`。

## 包含的 skill

每个 skill 的详细说明放在 GitHub 源仓库的 `docs/skills/codex-workspace-care/` 下。插件安装后的 runtime skill 目录只保留 Codex 执行需要的文件，不放 `README.md`。

| Skill | 职责 |
| --- | --- |
| [codex-chat-history-cleaner](https://github.com/jinny51/android-framework-codex-suite/tree/main/docs/skills/codex-workspace-care/codex-chat-history-cleaner) | 检查、修复和清理本地 Codex 历史记录、归档残留、搜索索引痕迹和 SQLite 一致性问题 |
| [codex-chat-history-context-extractor](https://github.com/jinny51/android-framework-codex-suite/tree/main/docs/skills/codex-workspace-care/codex-chat-history-context-extractor) | 从本地 Codex 历史中提取隐私友好的上下文交接材料，让新窗口可以继续前一个任务 |

## 使用边界

这个插件处理的是用户本机 Codex 状态，默认不应该在 Android Framework 任务中自动触发。

适合使用的场景：

1. 删除或归档的 Codex 聊天仍然出现在搜索里。
2. 本地 Codex 历史数据库疑似存在重复记录、迁移错误或索引残留。
3. 需要把一个前一个窗口的任务上下文整理成新窗口可继续的交接材料。
4. 分享问题复现信息前，需要生成隐私意识更强的上下文摘要。

不适合使用的场景：

1. 普通 Framework 需求分析、代码修改、构建推送。
2. 没有用户明确要求时主动删除历史记录。
3. 把清理结果、数据库副本或隐私材料提交进插件仓库。

## 安全原则

- 先检查和报告，再执行会修改本地状态的操作。
- 对删除、清理、修复类动作保留明确边界和可解释输出。
- 不把本地聊天数据库、索引、归档文件或导出上下文提交到 Git。
- 生成交接材料时默认减少隐私暴露，只保留继续任务所需的信息。

## 验证

从仓库根目录执行：

```bash
scripts/validate_plugins.sh
```

修改清理脚本后，额外执行：

```bash
python3 -m pytest --capture=no \
  tests/plugins/codex-workspace-care/codex-chat-history-cleaner
```
