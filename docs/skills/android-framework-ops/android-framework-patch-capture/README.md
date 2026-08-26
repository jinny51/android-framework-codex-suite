# android-framework-patch-capture

> GitHub 说明页。Runtime skill 文件位于 [../../../../plugins/android-framework-ops/skills/android-framework-patch-capture](../../../../plugins/android-framework-ops/skills/android-framework-patch-capture)；插件安装后的 skill 目录不包含本 README。文中的 `scripts/...`、`references/...` 指向该 runtime skill 目录。

Android Framework 功能级补丁资料生成 skill。

## 用途

该 skill 用于把一次已完成、阶段性、失败或阻塞但有价值的 Android Framework 功能修改整理成可审核材料：一个功能级 `README.md`、一个或多个源码仓库级 patch、修改内容记录和验证结果，供 `android-framework-patch-intake` 打包成 incoming 并发送到服务器上传入口。是否进入数据库仓库（database repository）和知识库仓库（knowledge repository）由管理端本地技能（local skill）后续判断。

它不负责分析需求、不负责改代码、不负责构建部署；这些仍由 `android-framework-change-workflow` 和构建交付类 skill 负责。

## 典型场景

- Framework 需求已经完成，需要按功能生成可以通过成员上传入口发送、供管理端本地技能后续判断的功能材料包。
- 阶段性修改需要整理成本地材料或日报上下文，但还没有达到普通上传条件；`draft/candidate`（草稿/候选）不直接进入服务器上传队列。
- 失败路径或阻塞路径有复用价值，需要作为日报上下文或本地材料保留，避免别人重复踩坑；除非后续另行设计仅归档入口，否则不作为普通补丁包上传。
- 管理员或成员端 Codex 想把一个高价值补丁提交给 `android-framework-patch-intake`。
- 需要给服务器提供 patch 内容 `sha1`，让后续 incoming 合并时按内容去重，而不是按文件名或 run id 去重。

## 常用命令

当前 Codex 工作流不在本机挂载树执行 Git。先通过 remote-channel v2
生成并传输不可变 snapshot；一个功能跨多个 Git 仓库时重复
`--repo-path`：

```bash
python3 "scripts/capture_remote_snapshot.py" \
  --ssh-host "$SSH_HOST" \
  --remote-root "$REMOTE_ROOT" \
  --repo-path frameworks/base \
  --repo-path packages/apps/Settings \
  --command-id "$PATCH_SNAPSHOT_COMMAND_ID"
```

再使用该命令返回的 snapshot 路径、SHA、workspace/command 身份和远端根：

```bash
python3 "scripts/capture_framework_patch.py" \
  --remote-snapshot "$SNAPSHOT" \
  --snapshot-sha256 "$SNAPSHOT_SHA256" \
  --snapshot-workspace-id "$WORKSPACE_ID" \
  --snapshot-command-id "$COMMAND_ID" \
  --remote-source-root "$REMOTE_ROOT" \
  --platform rk14 \
  --feature display-policy-settings-entry \
  --summary "调整显示策略和设置入口" \
  --problem-summary "显示策略缺少目标产品要求的配置入口和运行时行为" \
  --solution-summary "调整 Framework 显示策略并补齐 Settings 配置入口，再验证配置生效" \
  --implementation-origin codex \
  --workflow-contract current_codex_skill \
  --status candidate \
  --verification "framework 编译通过" \
  --build-result /path/to/build-result.json \
  --related-report-run-id 20260601-210000-daily
```

`--implementation-origin` 记录谁写了代码；`--workflow-contract` 记录补丁如何进入 AKBS。两个事实相互独立：成员手写代码也可以由当前 Codex + Skill 流程处理，此时仍使用 `current_codex_skill`；只有真实的既有代码导入才使用 `manual_import` 或 `historical_import`。补丁采集只记录来源、工作流和规范检查结果，不做沉淀结论（curation decision）。

真实既有代码导入使用显式 immutable patch，不借用 snapshot 身份：

```bash
python3 "scripts/capture_framework_patch.py" \
  --workflow-contract manual_import \
  --implementation-origin manual \
  --patch-artifact /path/to/frameworks-base.patch \
  --patch-repo-path frameworks/base \
  --platform rk14 \
  --feature existing-feature \
  --summary "既有功能补丁导入"
```

如果 `--project` 未提供，或只提供了 `android16`、`Camera2`、`mtk android16 Camera2` 这类非公司项目标签，脚本会继续从 remote snapshot 的源码根、repo 路径、Git 分支/remote、平台无关 source-access registry 和补丁内容中识别 `TVD`/`TVE`/`TVA`/`TVI` 项目号；识别不到时写入 `unknown`。

结构化项目字段只写入符合公司命名规范的项目型号。分支后缀、客户后缀、构建分支、业务标签、模块标签、中文描述和其他规范外尾随内容只能保留在 `project_inference` 证据里，不能写进 `manifest.project`。例如 `TVE1067M1_H031` 规范化为 `TVE1067M1`，`TVE1086U_MAIN_HANGYAN` 规范化为 `TVE1086U`，`TVE1091U福建移动高清` 规范化为 `TVE1091U`。

如果命令参数、snapshot 源码路径、Git 信息、source-access registry、功能摘要或 diff 同时暴露多个不同项目（project）候选，脚本写入 `project=unknown`，并在 `project_inference.candidates` 和 `project_inference.limits` 中记录冲突。不要为了让界面字段完整而选择第一个命中的项目。

`--platform` 只接受受控平台令牌：`mtk<Android版本>`、`rk<Android版本>`、`unisoc<Android版本>`，历史 `sprd`/`u` 别名会规范化为 `unisoc`。`android14`、`app15` 这类泛化令牌会被拒绝，因为它们不能证明平台（platform）。

当前工作流禁止从本机挂载源码读取 `.codex` 构建证据。把 build/deploy
receipt 作为显式 `--build-result` 输入，或传入 `--remote-build-*` 和
`--adb-*` 事实。

补丁采集会过滤只有文件模式元数据的 diff 段，例如 `old mode 100755` / `new mode 100644`。这类变化通常是 checkout 或 chmod 噪声，不会单独生成补丁包；如果同一仓库还有真实代码改动，会保留代码改动并剔除纯权限段。只有当可执行权限本身是功能的一部分，并且有内容修改、风险说明和验证证据时，才应作为功能补丁保留。

补丁资料包必须按功能生成，不能按日期生成“今日补丁合集”。这个规则不设补丁数量例外。一个功能跨多个 repo 管理的 Git 仓库时，可以在一个补丁包（patch package）里保留多个仓库级 patch；多个独立功能必须拆成多个补丁包（patch package）。成员即使是手写代码，也应先用补丁采集技能把改动包装成功能级材料，再交给成员补丁入口（android-framework-patch-intake）。

功能边界说明由补丁采集技能自动生成，不由成员手写结论。生成的 README 会记录功能目标、模块范围、关键锚点，以及每个仓库级 patch 如何共同服务同一个功能目标；如果这些事实不足，成员端 Codex 应提示成员补充真实需求、目标功能或验证范围后再重新生成。

成员端 Codex 在读取真实需求、diff 和验证证据后，应同时传入 `--problem-summary` 与 `--solution-summary`。脚本负责校验这两个参数并生成 `patch-problem-summary.json`；成员不需要、也不得手改 JSON。模块模板仍是本地草稿或候选材料的兼容兜底。若兜底结果过于通用，Codex 应使用真实问题和方案重新执行采集命令，而不是因为缺少某个模块专用模板而停止提交。

补丁需要修正时，必须从干净源码工作树重新采集同一功能，并通过 `--patch-package <capture package dir>` 生成一个新的完整补丁包。不要复制既有 patch、直接 `--patch` 或手写说明伪装为修正结果；若源工作树仍混有无关 diff，先拆分或清理，再采集。

结构化问题/方案证据不能残留无关模板文本。比如功能摘要和修改文件都指向 E-Ink、显示模式或资源配置时，生成的 `case.json`、`patch_problem_summary`、`risk_surface` 不应出现 CameraService、Camera2、相机预览、拍照或扫码等相机模板内容；出现这类不一致时必须停止并重新生成。

`workflow_contract=current_codex_skill` 必须在改代码前记录开发前知识搜索（pre-change knowledge search）证据。没有找到可用知识时，也要通过 `--reuse-decision not_found` 记录未命中（not_found），不能省略搜索证据。如果搜索结果命中了候选知识，就不能继续保留未知（unknown）；必须通过 `--reuse-decision reuse|adapt|reference_only|not_applicable|not_found` 闭合为直接复用（reuse）、适配复用（adapt）、仅作参考（reference_only）、不适用（not_applicable）或未命中（not_found）。如果开发前搜索没有发生，不能为了标记已验证（validated）补造搜索，当前工作流包必须留在本地。真实的 `manual_import` 或 `historical_import` 可以保留 `searched=false`，但不获得搜索闭环加分。检索门禁由工作流合同决定，不由代码作者来源决定；这些都只是开发证据，不是沉淀结论（curation decision）。

输出目录：

```text
$CODEX_HOME/artifacts/android-framework-patch-capture/packages/<run-id>/
├── manifest.json
├── README.md
├── patches/
└── evidence/
    ├── coding-standard-check.json
    ├── remote-source-snapshot.json
    ├── patch-diff-facts.json
    ├── build-result.json
    ├── verification-result.json
    └── search-before-change.json
```

## 文件入口

- [SKILL.md](../../../../plugins/android-framework-ops/skills/android-framework-patch-capture/SKILL.md)：给 Codex 自动加载的执行说明。
- [references/package-contract.md](../../../../plugins/android-framework-ops/skills/android-framework-patch-capture/references/package-contract.md)：功能级补丁资料包结构和修改内容字段约定。
- [scripts/capture_framework_patch.py](../../../../plugins/android-framework-ops/skills/android-framework-patch-capture/scripts/capture_framework_patch.py)：功能级补丁资料包生成脚本。
- [scripts/capture_remote_snapshot.py](../../../../plugins/android-framework-ops/skills/android-framework-patch-capture/scripts/capture_remote_snapshot.py)：通过 remote-channel v2 生成、传输并验证远端 source snapshot。
