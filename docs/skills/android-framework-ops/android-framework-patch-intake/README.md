# Android Framework Patch Intake

成员补丁包入口。成员侧 Codex + Skill 负责在上传前收集完整的功能边界、项目/平台/Android 版本、不可变补丁、代码锚点和真实验证，并只生成一个 `framework_change` 补丁包。服务端生成的 `patch_package_id` 是队列与主分支唯一业务身份，上传 `package_key` 只标识不可变物理来源。

管理端队列检查是安全兜底：轻量文字、字段或非补丁附件缺口按请求事件 `request_id` 补到同一个 `patch_package_id`；需要修改补丁或拆分功能时，退回并重新生成补丁包。队列阶段是 `received / under_review / information_required / information_review / closed`，入库后同一主体进入主分支 `under_review / pending_merge_confirmation / dispute_open / closed`。通知、资料请求和合并确认保留各自事件 ID 作为因果标识，不形成第二个补丁包身份。

```bash
python3 "<android-knowledge-intake skill>/scripts/android_knowledge_intake.py" --profile <member_alias> patch --prepare \
  --patch-package /path/to/.codex/patch-packages/<run-id> \
  --project TVE8402M --summary "功能补丁摘要" --status validated

python3 "<android-knowledge-intake skill>/scripts/android_knowledge_intake.py" --profile <member_alias> patch \
  --inspect-information-request <request-id>

python3 "<android-knowledge-intake skill>/scripts/android_knowledge_intake.py" --profile <member_alias> patch \
  --complete-information-request /path/to/response.json
```

补充响应只允许说明、受控字段和非补丁附件；客户端会重新读取请求，核对同一 `patch_package_id`，并绑定服务端权威 patch-set hash。知识新建/计划合并属于入库后的管理端沉淀流程。
