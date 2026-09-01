# android-member-setup

> GitHub 说明页。Runtime Skill 位于
> [plugins/android-framework-ops/skills/android-member-setup](../../../../plugins/android-framework-ops/skills/android-member-setup)。

成员首次启用与客户端健康检查入口。它负责成员 profile、`member_alias`、插件版本、当前
会话缓存和 AKBS endpoint doctor，不生成日报、周报或补丁 incoming。

```bash
python3 "scripts/android_member_setup.py" doctor \
  --profile <member_alias> \
  --strict \
  --check-remote
```

首次配置读取共享内核中的唯一
`android-knowledge-intake/references/member-setup-prompt.md`，避免维护两套身份和 endpoint 规则。
旧 `android-knowledge-intake doctor` 命令继续可用。
