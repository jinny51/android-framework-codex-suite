# jinny-android-coding-practices

> GitHub 说明页。Runtime Skill 位于 [../../../../plugins/jinny-android-practices/skills/jinny-android-coding-practices](../../../../plugins/jinny-android-practices/skills/jinny-android-coding-practices)。

显式选择 Jinny provider 后返回 `coding-policy-decision-v1`。规则只能叠加于核心 `android-change-policy`，decision 必须绑定 core policy、provider manifest 与 Skill 内容；行为性 advisory 直接位于已哈希的 `SKILL.md`，入口在执行共享 helper 前也会校验其固定 SHA-256。本 Skill 不改源码、不执行 workflow，也不拥有 Gate。
