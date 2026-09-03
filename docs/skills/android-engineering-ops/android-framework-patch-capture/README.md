# android-framework-patch-capture

> GitHub 说明页。Runtime Skill 位于 [../../../../plugins/android-engineering-ops/skills/android-framework-patch-capture](../../../../plugins/android-engineering-ops/skills/android-framework-patch-capture)。

迁移期薄 wrapper。旧 `capture_framework_patch.py` 以原参数和退出语义 exec canonical `android-patch-capture/scripts/capture_android_patch.py`；旧调用未提供 component 时只补 legacy Framework route，产生 platform/framework 与 `unknown` facets。Wrapper 不包含 capture、状态或提交逻辑。
