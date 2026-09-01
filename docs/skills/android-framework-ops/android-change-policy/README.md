# android-change-policy

> GitHub 说明页。Runtime skill 文件位于
> [../../../../plugins/android-framework-ops/skills/android-change-policy](../../../../plugins/android-framework-ops/skills/android-change-policy)。

Android 变更规范的公开入口。它不复制规则正文，而是绑定核心插件中的唯一机器合同
`android-change-policy/v1`。

该规范分三层：

- 所有采用 patch 归档的 Android 变更都执行成员身份、作者日期、真实证据和历史作者保护规则；
- FrameworkLog、Framework 调试属性、资源和功能材料规则只用于 Framework 领域；
- 旧 Jinny helper/Utils 命名偏好仅在用户明确要求时作为兼容建议，不是全域强制规则。

新 Codex 代码从已选择 profile 的 `member_alias` 生成成对标记。Git author、示例人名或临时编造的事项号都不是身份来源。旧补丁保留原作者，不改写成当前提交人。

`//` 形式只用于支持该注释语法的源码；XML、Shell 等文件在存在正式 comment adapter 前不会被盲目插入标记。
