# Jinny Android Practices

Jinny Android Practices 是可选实践插件，用于放置 Jinny 团队的 Android Framework 代码风格、review 口径和项目工作流规则。

这个插件可以和 `android-framework-ops` 一起安装，但核心插件不依赖它。团队成员可以只安装核心插件，也可以选择额外安装本实践插件。

## 当前状态

当前包含的实践 skill：

| Skill | 职责 |
| --- | --- |
| [jinny-framework-coding-standards](https://github.com/jinny51/android-framework-codex-suite/tree/main/docs/skills/jinny-android-practices/jinny-framework-coding-standards) | 在 Android Framework 需求实现、评审和补丁打包前应用 Jinny 团队补丁开发规范与 FrameworkLog 日志规范 |

保留这个插件边界是为了避免把个人或小团队偏好混进 `android-framework-ops`。后续如果要加入更多代码风格、review、项目规范、提交规范或验收偏好，应放在这里，而不是放进核心工程插件。

新增实践 skill 后，对应的人类说明放在 GitHub 源仓库的 `docs/skills/jinny-android-practices/<skill-name>/README.md`。插件安装后的 runtime skill 目录只保留 Codex 执行需要的文件，不放 `README.md`。

## 适合放进这里的内容

| 类型 | 示例 |
| --- | --- |
| 代码风格 | Framework 修改范围控制、命名偏好、日志写法、资源命名、注释尺度 |
| Review 规则 | patch 自检清单、风险分级、回滚说明、验证证据要求 |
| 项目规范 | 特定平台、特定客户、特定源码树的本地工作约定 |
| 团队协作 | 日报/周报口径、patch 说明口径、知识库沉淀偏好 |

## 和核心工作流配合

当 `jinny-framework-coding-standards` 与 `android-framework-change-workflow` 同时适用时，应在代码修改前加载团队规范。补丁采集阶段只做校验和证据保存，不应作为事后补规范的主要环节。

## 不适合放进这里的内容

- Android Framework 通用源码接入、构建、推送和验收流程；这些属于 `android-framework-ops`。
- Codex 本地聊天历史清理和上下文交接；这些属于 `codex-workspace-care`。
- 成员个人私有规则、真实客户配置、账号、路径、凭据或本地数据库。

## 新增实践 skill

新增 skill 时，需要同时更新：

```text
plugins/jinny-android-practices/skills/<skill-name>/
docs/skills/jinny-android-practices/<skill-name>/README.md
manifests/jinny-android-practices.toml
plugins/jinny-android-practices/README.md
README.md
```

实践 skill 应写清楚触发边界，避免和成员自己的 skill 互相覆盖。推荐表达方式是“当用户明确要求按 Jinny 团队规范处理时使用”，而不是无条件接管所有 Framework 任务。

## 验证

从仓库根目录执行：

```bash
scripts/validate_plugins.sh
```
