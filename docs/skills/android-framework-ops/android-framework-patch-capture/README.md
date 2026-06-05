# android-framework-patch-capture

> GitHub 说明页。Runtime skill 文件位于 [../../../../plugins/android-framework-ops/skills/android-framework-patch-capture](../../../../plugins/android-framework-ops/skills/android-framework-patch-capture)；插件安装后的 skill 目录不包含本 README。文中的 `scripts/...`、`references/...` 指向该 runtime skill 目录。

Android Framework 补丁包生成 skill。

## 用途

该 skill 用于把一次已完成、阶段性、失败或阻塞但有价值的 Android Framework 修改整理成可审核的补丁资料：`patch`、配套 `readme`、修改内容记录和验证结果，供 `android-knowledge-intake` 打包成 incoming 并提交到数据库仓库。

它不负责分析需求、不负责改代码、不负责构建部署；这些仍由 `android-framework-change-workflow` 和构建交付类 skill 负责。

## 典型场景

- Framework 需求已经完成，需要生成可以提交到数据库仓库、等待审核后再决定是否导出到知识库仓库的补丁包。
- 阶段性修改需要作为 `draft/candidate`（草稿/候选）进入数据库仓库 incoming，但必须带清楚的验证结果和风险说明。
- 失败路径或阻塞路径有复用价值，需要作为 `failed/blocked` 证据进入数据库仓库 incoming，避免别人重复踩坑。
- 管理员或成员端 Codex 想把一个高价值补丁提交给 `android-knowledge-intake` 的 `patch` 模式。
- 需要给服务器提供 patch 内容 `sha1`，让后续 incoming 合并时按内容去重，而不是按文件名或 run id 去重。

## 常用命令

在 Android 源码 git 仓库中执行：

```bash
python3 "scripts/capture_framework_patch.py" \
  --platform rk14 \
  --feature allow-powerkey-to-user \
  --summary "允许用户态控制电源键行为" \
  --status candidate \
  --verification "framework 编译通过" \
  --build-result /path/to/build-result.json \
  --related-report-run-id 20260601-210000-daily
```

如果 `--project` 未提供，或只提供了 `android16`、`Camera2`、`mtk android16 Camera2` 这类非公司项目标签，脚本会继续从 `source_root`、git 分支/remote、WSL source-access registry 和补丁内容中识别 `TVE`/`TVA`/`TVI` 项目号；识别不到时写入 `unknown`。

输出目录：

```text
.codex/patch-packages/<run-id>/
├── manifest.json
├── patches/
└── evidence/
    ├── build-result.json
    ├── verification-result.json
    └── search-before-change.json
```

## 文件入口

- [SKILL.md](../../../../plugins/android-framework-ops/skills/android-framework-patch-capture/SKILL.md)：给 Codex 自动加载的执行说明。
- [references/package-contract.md](../../../../plugins/android-framework-ops/skills/android-framework-patch-capture/references/package-contract.md)：补丁包结构和修改内容字段约定。
- [scripts/capture_framework_patch.py](../../../../plugins/android-framework-ops/skills/android-framework-patch-capture/scripts/capture_framework_patch.py)：补丁包生成脚本。
