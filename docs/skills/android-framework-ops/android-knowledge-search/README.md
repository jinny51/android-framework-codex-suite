# android-knowledge-search

> GitHub 说明页。Runtime skill 文件位于 [../../../../plugins/android-framework-ops/skills/android-knowledge-search](../../../../plugins/android-framework-ops/skills/android-knowledge-search)；插件安装后的 skill 目录不包含本 README。文中的 `scripts/...`、`references/...` 指向该 runtime skill 目录。

团队知识库检索 skill。

## 用途

该 skill 用于搜索团队知识库里的日报、周报、补丁、修改文件、检索锚点（文件/类名/属性/资源 key）、归档记录和验证证据。

它的价值是让成员或其他 skill 在重新分析、重新开发之前，先查团队是否已经保存过类似功能、补丁或问题处理记录。

## 典型场景

- 新需求来了，先查有没有类似 Framework 修改或历史补丁。
- 看到一个类名、属性、Settings key、资源 key，想知道以前哪个补丁改过。
- 想从日报/周报里找某个项目、问题、成员的历史处理记录。
- 想确认某个 incoming 是否留下了可复用归档记录和验证证据。
- `android-framework-change-workflow` 在进入源码分析前，先查知识库作为参考材料。

## 常用命令

```bash
python3 "scripts/android_knowledge_search.py" \
  "电源键 frameworks/base" \
  --limit 8
```

只搜补丁：

```bash
python3 "scripts/android_knowledge_search.py" \
  "persist.sys launcher" \
  --type patch
```

只搜主案例或平台实现：

```bash
python3 "scripts/android_knowledge_search.py" \
  "通知音量 SystemUI" \
  --type case

python3 "scripts/android_knowledge_search.py" \
  "TVE8402M VolumeDialogImpl" \
  --type variant
```

只搜归档记录或验证证据：

```bash
python3 "scripts/android_knowledge_search.py" \
  "电源键 rk3576" \
  --type event

python3 "scripts/android_knowledge_search.py" \
  "真机验证 services.jar" \
  --type evidence
```

指定知识库路径：

```bash
python3 "scripts/android_knowledge_search.py" \
  "WindowManager display" \
  --root /path/to/knowledge/worktree
```

未显式指定 `--root` 时，脚本会优先使用 `CODEX_KNOWLEDGE_ROOT`、报告配置里的当前 profile `repo_worktree`，再尝试当前目录父级和通用 `worktrees/knowledge` 路径。成员端应通过自己的 `config.toml` 或环境变量指向知识库副本，不依赖维护者本机路径。

## 和其他 skill 的关系

```text
android-knowledge-intake
  负责把日报、周报、补丁提交到知识库

android-framework-patch-capture
  负责把 Framework 修改整理成标准补丁资料

android-knowledge-search
  负责把知识库里已有经验、补丁和验证结果搜出来

android-framework-change-workflow
  处理需求前先搜索；搜不到或参考材料不足，再进入分析、修改、验证流程
```

## 文件入口

- [SKILL.md](../../../../plugins/android-framework-ops/skills/android-knowledge-search/SKILL.md)：给 Codex 自动加载的执行说明。
- [references/search-contract.md](../../../../plugins/android-framework-ops/skills/android-knowledge-search/references/search-contract.md)：知识库检索输入、输出和判断边界。
- [scripts/android_knowledge_search.py](../../../../plugins/android-framework-ops/skills/android-knowledge-search/scripts/android_knowledge_search.py)：本地检索脚本。
