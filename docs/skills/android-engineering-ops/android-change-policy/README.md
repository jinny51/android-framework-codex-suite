# android-change-policy

> GitHub 说明页。Runtime Skill 位于 [../../../../plugins/android-engineering-ops/skills/android-change-policy](../../../../plugins/android-engineering-ops/skills/android-change-policy)。

Android 全 component layer 强制变更策略的唯一公开入口。所有需 patch 归档的 Android 变更应用成员身份、成对作者日期标记、真实证据和历史作者保护；FrameworkLog、调试属性和资源规则只在 `layer=platform` 且 `type=framework` 时叠加。旧 Jinny 命名偏好仅是显式选择后的建议，不能放宽核心策略。

读取项目/源码或应用策略前必须通过 `android-engineering-ops` 的 target-only install-family gate；缺失、从源码目录冒充运行或旧新插件混装均停止。
