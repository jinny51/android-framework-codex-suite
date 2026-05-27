# codex-chat-history-context-extractor

> GitHub 说明页。Runtime skill 文件位于 [../../../../plugins/codex-workspace-care/skills/codex-chat-history-context-extractor](../../../../plugins/codex-workspace-care/skills/codex-chat-history-context-extractor)；插件安装后的 skill 目录不包含本 README。文中的 `scripts/...`、`references/...` 指向该 runtime skill 目录。

Codex 聊天历史上下文（历史信息）提取 skill。

## 用途

该 skill 用于从本地 Codex 会话历史中提取隐私友好的上下文（历史信息）交接材料，让新的 Codex 对话可以接着旧任务继续，而不需要直接复制完整聊天记录。

它只做读取和生成摘要，不清理历史。

## 典型场景

- 一个长会话快要失控或需要换窗口继续，希望提取必要上下文（历史信息）给新会话接着干。
- 需要把历史会话中的决策、路径、命令、风险点整理成隐私友好的交接材料。
- 不想删除历史，只想生成一份可复制给新 Codex 会话的工作交接摘要。

## 文件入口

- [SKILL.md](../../../../plugins/codex-workspace-care/skills/codex-chat-history-context-extractor/SKILL.md)：给 Codex 自动加载的执行说明。
- [references/privacy.md](../../../../plugins/codex-workspace-care/skills/codex-chat-history-context-extractor/references/privacy.md)：隐私处理规则。
- [scripts/extract_codex_context.py](../../../../plugins/codex-workspace-care/skills/codex-chat-history-context-extractor/scripts/extract_codex_context.py)：上下文（历史信息）提取脚本。
- [scripts/self_test_extract_codex_context.py](../../../../plugins/codex-workspace-care/skills/codex-chat-history-context-extractor/scripts/self_test_extract_codex_context.py)：自测脚本。
