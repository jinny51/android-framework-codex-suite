# akbs-knowledge-merge-review

> GitHub 说明页。Runtime Skill 位于
> [plugins/akbs-member-ops/skills/akbs-knowledge-merge-review](../../../../plugins/akbs-member-ops/skills/akbs-knowledge-merge-review)。

成员侧 AKBS 知识合并复核入口。

任何列表、读取、比较、分析或 dispute 前，必须先运行
`akbs_member_setup.py preflight-install-family` 并取得 `status=PASS`；只有纯
`--help` 可以跳过。

它使用通知或列表返回的 `confirmation_id` 查看 detail、目标知识、compare 和合并依据，
并生成 Codex 分析摘要。`patch_package_id` 是补丁业务主体，`package_key` 只表示上传来源。

`list`、`detail`、`target`、`compare` 和 `analyze` 都是只读操作。服务端不可用时明确失败，
不能回退成本地搜索后伪造合并依据。只有成员明确要求发送异议，并同时提供
`--send-dispute` 和理由/评估时，才允许 POST dispute。

```bash
python3 "scripts/akbs_knowledge_merge_review.py" analyze \
  --confirmation-id <confirmation_id>
```

原 `android-knowledge-search --merge-confirmation ...` 在兼容期继续可用，但普通知识检索和
合并复核是两个不同的用户意图。
