# android-framework-change-workflow

> GitHub 说明页。Runtime Skill 位于 [../../../../plugins/android-engineering-ops/skills/android-framework-change-workflow](../../../../plugins/android-engineering-ops/skills/android-framework-change-workflow)。

迁移期薄 wrapper。它保持旧 Skill ID 与调用意图，立即转交 `android-change-workflow`，只提供 `platform/framework` 兼容提示；partition/ownership 保持显式或 `unknown`，不复制 controller、provider、source-access、构建或验收实现。
