# android-framework-patch-intake

> GitHub 说明页。Runtime skill 文件位于 [../../../../plugins/android-framework-ops/skills/android-framework-patch-intake](../../../../plugins/android-framework-ops/skills/android-framework-patch-intake)。

成员补丁包入口。它负责把功能级补丁资料包、补证包、替换包或补丁资产修正包生成 `framework_change` incoming，并复用 `android-knowledge-intake` 的共享脚本和上传协议。

补丁包生成：

- `manifest.json`
- `patches/*`
- `materials/display/patch_view.json`
- `materials/evidence/patch_ai_facts.json`
- 项目、平台、Android 版本、验证、风险、搜索使用和补证关系证据

常用命令：

```bash
python3 "<android-knowledge-intake skill>/scripts/android_knowledge_intake.py" --profile <member_alias> patch --prepare --patch-package /path/to/.codex/patch-packages/<run-id> --project "TVE8402M" --summary "功能补丁摘要" --status validated
python3 "<android-knowledge-intake skill>/scripts/android_knowledge_intake.py" --profile <member_alias> patch --submit-latest
```

实际源码变更应先用 `android-framework-patch-capture` 生成一个功能级 capture package。补丁资产修正也必须重新 capture，不能复制既有 patch 或手写说明伪装为修正。

轻量补证只适用于字段级元数据缺口，例如 `project`、`platform`、Android 版本。补证包继承目标原始包的材料名和材料摘要；如果材料名或材料摘要错误，必须重新生成替换原始包，不能用补证包改写。

```bash
python3 "<android-knowledge-intake skill>/scripts/android_knowledge_intake.py" --profile <member_alias> patch --prepare \
  --supplement-for-package-key 20260702/lincong/20260702-193308-patch \
  --supplement-mode field_correction \
  --corrected-field project=TVI3315A \
  --corrected-field platform=rk \
  --corrected-field android_version=14 \
  --correction-reason "管理端提示项目名缺失，按成员可追溯字段补证" \
  --summary "补充 TVI3315A 项目字段" \
  --status validated
```

缺验证、缺补丁资产、缺 `patch_ai_facts`、local-check 失败或补丁资产污染时，仍必须完整重采并走资产级补证。
