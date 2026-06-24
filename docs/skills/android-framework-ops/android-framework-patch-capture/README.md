# android-framework-patch-capture

> GitHub 说明页。Runtime skill 文件位于 [../../../../plugins/android-framework-ops/skills/android-framework-patch-capture](../../../../plugins/android-framework-ops/skills/android-framework-patch-capture)；插件安装后的 skill 目录不包含本 README。文中的 `scripts/...`、`references/...` 指向该 runtime skill 目录。

Android Framework 功能级补丁资料生成 skill。

## 用途

该 skill 用于把一次已完成、阶段性、失败或阻塞但有价值的 Android Framework 功能修改整理成可审核材料：一个功能级 `README.md`、一个或多个源码仓库级 patch、修改内容记录和验证结果，供 `android-knowledge-intake` 打包成 incoming 并提交到数据库仓库。是否沉淀进知识库仓库（knowledge repository）由管理端本地技能（local skill）后续判断。

它不负责分析需求、不负责改代码、不负责构建部署；这些仍由 `android-framework-change-workflow` 和构建交付类 skill 负责。

## 典型场景

- Framework 需求已经完成，需要按功能生成可以提交到数据库仓库、供管理端本地技能后续判断的功能材料包。
- 阶段性修改需要作为 `draft/candidate`（草稿/候选）进入数据库仓库 incoming，但必须带清楚的验证结果和风险说明。
- 失败路径或阻塞路径有复用价值，需要作为 `failed/blocked` 证据进入数据库仓库 incoming，避免别人重复踩坑。
- 管理员或成员端 Codex 想把一个高价值补丁提交给 `android-knowledge-intake` 的 `patch` 模式。
- 需要给服务器提供 patch 内容 `sha1`，让后续 incoming 合并时按内容去重，而不是按文件名或 run id 去重。

## 常用命令

在涉及的 Android 源码 git 仓库中执行；一个功能跨多个 repo 管理的 Git 仓库时，重复传 `--source-root`：

```bash
python3 "scripts/capture_framework_patch.py" \
  --source-root /work/android/frameworks/base \
  --source-root /work/android/packages/apps/Settings \
  --platform rk14 \
  --feature display-policy-settings-entry \
  --summary "调整显示策略和设置入口" \
  --implementation-origin codex \
  --status candidate \
  --verification "framework 编译通过" \
  --build-result /path/to/build-result.json \
  --related-report-run-id 20260601-210000-daily
```

如果代码不是 Codex 实现，而是成员手写、外部补丁或历史代码，传 `--implementation-origin manual`、`external`、`historical`、`mixed` 或 `unknown`。补丁采集只记录来源和规范检查结果，不做沉淀结论（curation decision）。

如果 `--project` 未提供，或只提供了 `android16`、`Camera2`、`mtk android16 Camera2` 这类非公司项目标签，脚本会继续从 `source_root`、repo 路径、git 分支/remote、WSL source-access registry 和补丁内容中识别 `TVE`/`TVA`/`TVI` 项目号；识别不到时写入 `unknown`。

如果命令参数、源码路径、git 信息、WSL source-access registry、功能摘要或 diff 同时暴露多个不同项目（project）候选，脚本写入 `project=unknown`，并在 `project_inference.candidates` 和 `project_inference.limits` 中记录冲突。不要为了让界面字段完整而选择第一个命中的项目。

`--platform` 只接受受控平台令牌：`mtk<Android版本>`、`rk<Android版本>`、`unisoc<Android版本>`，历史 `sprd`/`u` 别名会规范化为 `unisoc`。`android14`、`app15` 这类泛化令牌会被拒绝，因为它们不能证明平台（platform）。

如果构建交付流程已经由 `android-wsl-remote-build-deploy/scripts/push-artifacts.sh` 写出 `<source-root>/.codex/evidence/latest-build-delivery.json`，补丁采集会自动读取远端构建和本机 adb 证据，并合并进 `verification-result.json`。手工 `--remote-build-*` 和 `--adb-*` 参数只用于历史材料或异常路径补录。

补丁采集会过滤只有文件模式元数据的 diff 段，例如 `old mode 100755` / `new mode 100644`。这类变化通常是 checkout 或 chmod 噪声，不会单独生成补丁包；如果同一仓库还有真实代码改动，会保留代码改动并剔除纯权限段。只有当可执行权限本身是功能的一部分，并且有内容修改、风险说明和验证证据时，才应作为功能补丁保留。

补丁资料包必须按功能生成，不能按日期生成“今日补丁合集”。这个规则不设补丁数量例外。一个功能跨多个 repo 管理的 Git 仓库时，可以在一个补丁包（patch package）里保留多个仓库级 patch；多个独立功能必须拆成多个补丁包（patch package）。成员即使是手写代码，也应先用补丁采集技能把改动包装成功能级材料，再交给成员上传技能（android-knowledge-intake）。

Codex 正常开发流程必须记录开发前知识搜索（pre-change knowledge search）证据。如果 Codex 实现的补丁包（patch package）状态是已验证（validated），`search_before_change.searched` 必须为 `true`；没有找到可用知识时，也要通过 `--reuse-decision not_found` 记录未命中（not_found），不能省略搜索证据。如果搜索结果命中了候选知识，就不能继续保留未知（unknown）；必须通过 `--reuse-decision reuse|adapt|reference_only|not_applicable|not_found` 闭合为直接复用（reuse）、适配复用（adapt）、仅作参考（reference_only）、不适用（not_applicable）或未命中（not_found）。如果代码来源是手动实现（manual implementation）、外部实现、历史材料、混合实现或未知来源，不能事后伪造开发前搜索；应如实记录 `searched=false` 或未发生搜索，后续由管理端本地技能执行沉淀前重叠检索（post-change overlap check）。这些只是开发证据，不是沉淀结论（curation decision）。

输出目录：

```text
.codex/patch-packages/<run-id>/
├── manifest.json
├── README.md
├── patches/
└── evidence/
    ├── coding-standard-check.json
    ├── patch-diff-facts.json
    ├── build-result.json
    ├── verification-result.json
    └── search-before-change.json
```

## 文件入口

- [SKILL.md](../../../../plugins/android-framework-ops/skills/android-framework-patch-capture/SKILL.md)：给 Codex 自动加载的执行说明。
- [references/package-contract.md](../../../../plugins/android-framework-ops/skills/android-framework-patch-capture/references/package-contract.md)：功能级补丁资料包结构和修改内容字段约定。
- [scripts/capture_framework_patch.py](../../../../plugins/android-framework-ops/skills/android-framework-patch-capture/scripts/capture_framework_patch.py)：功能级补丁资料包生成脚本。
