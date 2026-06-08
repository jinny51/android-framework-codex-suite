# jinny-framework-coding-standards

> GitHub 说明页。Runtime skill 文件位于 [../../../../plugins/jinny-android-practices/skills/jinny-framework-coding-standards](../../../../plugins/jinny-android-practices/skills/jinny-framework-coding-standards)；插件安装后的 skill 目录不包含本 README。

Jinny 团队 Android Framework 编码规范 skill。它用于在实现需求前约束补丁写法，并在评审、打包或接手手写代码时做防漏检查。

## 适用场景

- 用 Codex 实现 Jinny 团队 Android Framework 需求，需要前置遵循补丁开发规范和日志管理规范。
- 检查成员手写、历史迁移或外部来源的 Framework 补丁是否满足团队规范。
- 需要确认 `FrameworkLog`、作者日期备注、字符串国际化、动态配置和功能级 README 是否完整。

## 关键口径

- 编码规范必须在开发阶段执行，不应等到补丁采集阶段再补。
- 一个功能可以涉及多个 repo 管理的源码仓库；资料按功能组织，一个功能 README 对多个仓库级 patch。
- 补丁采集只做校验和证据保存，不能把不合规代码描述成合规代码。

## 文件入口

- [SKILL.md](../../../../plugins/jinny-android-practices/skills/jinny-framework-coding-standards/SKILL.md)：给 Codex 自动加载的执行说明。
- [references/android-framework-coding-standards.md](../../../../plugins/jinny-android-practices/skills/jinny-framework-coding-standards/references/android-framework-coding-standards.md)：团队补丁开发和日志管理规范摘要。
