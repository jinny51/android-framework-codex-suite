# Android Framework Patch Intake

成员补丁包入口。成员侧 Codex + Skill 负责在上传前收集完整的功能边界、项目/平台/Android 版本、不可变补丁、代码锚点和真实验证，并只生成一个 `framework_change` 补丁包。

管理端队列检查是安全兜底：轻量文字、字段或非补丁附件缺口补到同一个补丁包；需要修改补丁或拆分功能时，退回并重新生成补丁包。AKBS 不再生成原始包、补证包或逻辑包。

```bash
python3 "<android-knowledge-intake skill>/scripts/android_knowledge_intake.py" --profile <member_alias> patch --prepare \
  --patch-package /path/to/.codex/patch-packages/<run-id> \
  --project TVE8402M --summary "功能补丁摘要" --status validated

python3 "<android-knowledge-intake skill>/scripts/android_knowledge_intake.py" --profile <member_alias> patch \
  --inspect-information-request <request-id>

python3 "<android-knowledge-intake skill>/scripts/android_knowledge_intake.py" --profile <member_alias> patch \
  --complete-information-request /path/to/response.json
```

补充响应只允许说明、受控字段和非补丁附件；客户端会重新读取请求并绑定服务端权威 patch-set hash。知识新建/计划合并属于入库后的管理端沉淀流程。
