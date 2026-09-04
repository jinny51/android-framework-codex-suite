# Jinny Android Practices

Jinny Android Practices 是可选偏好层，不是 Android 强制规范的第二份来源。

核心 `android-change-policy` 统一负责成员身份、成对补丁标记、历史作者保护、证据合同和 Framework 安全规则。本插件只在用户明确要求时叠加 Jinny helper/Utils 命名、review 或项目偏好；所有别名都从当前成员 profile 获取，不能硬编码示例人物。

## 包含的 Skill

| Skill | 职责 |
| --- | --- |
| [jinny-framework-coding-standards](https://github.com/jinny51/android-framework-codex-suite/tree/main/docs/skills/jinny-android-practices/jinny-framework-coding-standards) | 在 `android-change-policy` 之上叠加用户明确要求的 Jinny 可选偏好 |

本插件不是 `android-framework-ops` 的硬依赖，也不复制强制规则。

## 验证

```bash
scripts/validate_plugins.sh
```
