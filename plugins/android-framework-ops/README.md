# Android Framework Ops

Android Framework Ops 是共享 Android 工程核心。它负责 Framework、SystemApp、App、HAL、native、vendor、kernel、driver、device 和 build 的领域选择、知识检索、诊断修改、远程执行、本地补丁材料和能力门禁；生产 incoming v1 仍只开放 Framework。

这个插件内置可机器验证的核心工程不变量：patch 归档身份、真实证据和 Framework 专属安全规则。它不强行接管个人代码风格、项目本地规范或 review workflow；这些规则可以叠加，但不能改写核心身份和证据合同。

源码接入实现只在本核心插件保留一套，并在任何副作用前自动识别 WSL 或 macOS。成员从 `android-wsl-ops` 或 `android-mac-ops` 的 `android-source-access` 入口调用；平台插件只提供命令路径和薄转发，不复制 CIFS/SMB、Keychain、registry 或识别实现。远程构建、产物定位和本地 adb 交付同样只在本核心插件保留一套实现。

## 包含的 skill

每个 skill 的详细说明放在 GitHub 源仓库的 `docs/skills/android-framework-ops/` 下。插件安装后的 runtime skill 目录只保留 Codex 执行需要的文件，不放 `README.md`。

| 分类 | Skill | 职责 |
| --- | --- | --- |
| 工程规范 | [android-change-policy](https://github.com/jinny51/android-framework-codex-suite/tree/main/docs/skills/android-framework-ops/android-change-policy) | 统一 Android patch 成员溯源和领域规则；Framework 规则不污染 App/HAL/内核 |
| Android 工作流 | [android-framework-change-workflow](https://github.com/jinny51/android-framework-codex-suite/tree/main/docs/skills/android-framework-ops/android-framework-change-workflow) | 统筹全领域 domain、需求、修改、风险、构建和验收 |
| Android 工作流 | [android-framework-patch-capture](https://github.com/jinny51/android-framework-codex-suite/tree/main/docs/skills/android-framework-ops/android-framework-patch-capture) | 按 change_domain 整理本地 README、多仓库 patch 和验证材料；仅 Framework 可继续提交 v1 |
| 知识系统 | [android-knowledge-search](https://github.com/jinny51/android-framework-codex-suite/tree/main/docs/skills/android-framework-ops/android-knowledge-search) | 默认搜索 AI 可复用案例、平台实现、补丁、检索锚点和验证记录；归档记录需显式查询 |
| 知识系统 | [android-knowledge-merge-review](https://github.com/jinny51/android-framework-codex-suite/tree/main/docs/skills/android-framework-ops/android-knowledge-merge-review) | 按 `confirmation_id` 查看合并依据、比较证据，并仅在成员明确授权时提交异议 |
| 知识系统 | [android-framework-patch-intake](https://github.com/jinny51/android-framework-codex-suite/tree/main/docs/skills/android-framework-ops/android-framework-patch-intake) | 生成一个完整补丁包，以 `patch_package_id` 贯穿队列和主分支，并按 `request_id` 完成同包资料补充 |
| 知识系统 | [android-daily-report-intake](https://github.com/jinny51/android-framework-codex-suite/tree/main/docs/skills/android-framework-ops/android-daily-report-intake) | 按 Patch/App/GMS/Doc/Other 范围生成含重点说明和依赖/需协调的个人日报正文、同源 `report_view.json` 和 `daily_trace` incoming |
| 知识系统 | [android-weekly-report-intake](https://github.com/jinny51/android-framework-codex-suite/tree/main/docs/skills/android-framework-ops/android-weekly-report-intake) | 汇总当前有效日报中的重点说明和依赖候选、上一周项目台账及文档进展，由成员确认依赖、主责确认项目流转并硬校验跨周总量，生成个人周报、同源 `report_view.json` 和 `weekly_trace` incoming |
| 知识系统 | [android-knowledge-intake](https://github.com/jinny51/android-framework-codex-suite/tree/main/docs/skills/android-framework-ops/android-knowledge-intake) | 兼容 CLI 和 daily/weekly/patch 共用的 incoming v1 内核；旧 doctor 继续可用 |
| 成员设置 | [android-member-setup](https://github.com/jinny51/android-framework-codex-suite/tree/main/docs/skills/android-framework-ops/android-member-setup) | 成员首次启用、profile 指引、doctor、插件版本和会话缓存诊断；旧 intake doctor 继续兼容 |
| 远程执行 | [android-remote-channel](https://github.com/jinny51/android-framework-codex-suite/tree/main/docs/skills/android-framework-ops/android-remote-channel) | 统一管理 Android 构建服务器 SSH/tmux 长会话、命令日志、占用状态和锁 |
| 远程执行 | [android-remote-build-deploy](https://github.com/jinny51/android-framework-codex-suite/tree/main/docs/skills/android-framework-ops/android-remote-build-deploy) | WSL/macOS 共用受支持的 AOSP/Soong/Make 与显式 vendor 构建、产物校验和本地 adb 交付 |

日报和周报中的 GMS 以“项目 + 客户 + 送测类别 + 目标版本”为范围身份；送测类别使用 IR/MR/SMR/ESMR/EMR/LR。自测轮次和正式送测次数分别累计，送测前最新自测必须通过，送测退回后回到自测；发现的问题和修复继续作为普通工作项记录，不另建处理周期或问题子系统。明日计划只声明 GMS 送测类别、目标版本和计划事项，不伪造尚未发生的阶段、轮次或送测次数。

## 推荐工作流

1. 注册的远程 Android 树先由对应系统平台插件的 `android-source-access` 确认源码路径和远程映射；真实本地项目不调用它。
2. `android-knowledge-search` 在正式分析前检索知识库仓库里的既有方案、补丁和验证证据。
3. `android-change-policy` 在修改前确定成员身份、patch 标记和领域规则。
4. `android-framework-change-workflow` 负责需求分析、源码修改、调试日志、风险判断和验收口径。
5. `android-remote-channel` 提供稳定远程会话，远程树的源码操作和项目自有 Gradle/Kbuild 等构建入口都通过它执行。
6. 受支持的 AOSP/Soong/Make 模块或显式 vendor 全量构建使用 `android-remote-build-deploy`；真实本地项目使用自己的本地构建入口。
7. `android-framework-change-workflow` 根据需求和设备证据给最终验收结论，并决定 `validated`、`candidate`、`draft`、`failed` 或 `blocked` 包状态（package status）。
8. `android-framework-patch-capture` 把已完成、阶段性、失败或阻塞但有价值的 Android 修改整理成一个功能 README、多个源码仓库 patch 和 evidence；只有验证通过的 Framework capture 可继续提交 incoming v1。
9. 成员按材料类型选择入口：`android-framework-patch-intake` 生成一个完整补丁包或按资料请求事件 `request_id` 补充同一个包，`android-daily-report-intake` 生成日报包，`android-weekly-report-intake` 生成周报包；三者共用上传协议、版本门禁、会话缓存门禁和本地预校验。日报、周报在没有旧报告时才可能构成补交，已有有效报告后的再次提交统一作为修订并保留旧版历史。补丁包在队列和主分支始终使用同一个 `patch_package_id`，`package_key` 只标识上传来源。补丁文件不可通过队列补充修改；需要改补丁时重新采集。后续新建知识或计划合并由本机 `akbs-curation-maintainer` 和 AI 知识闭环决定。周报包只做进度归档。

默认原则：成员端能自动保存材料就先保存材料，再按包状态（package status）排序和作为复用提示（reuse hint）。缺少显式确认不等于丢弃证据；只有敏感信息、混杂无关 diff、高风险误导或身份/配置不可用时才停止上传，并在最终报告中说明。是否沉淀进知识库仓库由管理端本地技能决定。

成员端补丁采集与上传预检共用插件规则模块：项目规范化、平台和 Android 版本解析、共同功能目标判断、开发前知识搜索、搜索使用决策、补丁资产污染和完整性门禁都从同一份规则进入。AKBS 服务端不加载成员 Codex 插件，而是按公开包合同做最终安全复核和事务写入。新建知识、计划合并和知识有效度只属于管理端 AI 知识闭环。

公司项目型号必须写入规范项目名，例如 `TVE1213M` 或 `TVI3315A`。如果来源材料只写 7 位短型号，例如 `TVE1213`，插件规则模块（plugin rules module）只有在同一推断流程已经拿到可信平台证据时才会补齐第八位平台字母：`mtk -> M`、`rk -> R`、`unisoc -> U`。没有可信平台证据时，短型号不能自动写入结构化项目字段；补齐后的候选值仍必须通过公司项目型号规则。`TVI` 使用工控产品专门命名规则，需要从通用平台位补齐规则里单独处理：已有第八位时保持原样，`A` 和 `X` 都是合法 TVI 字段；缺第八位时优先按 TVI 芯片字段补 `A/X`，不能按 AKBS 平台（platform）补成 `R/M/U`。平台仍单独记录为 `rk`、`mtk` 或 `unisoc`。

## 和其他 skill 的组合方式

如果用户或项目同时提供了自己的 skill，应按组合方式使用：

- 个人代码风格、项目本地规范、review 口径由用户提供的 skill 或项目 `AGENTS.md` 负责。
- 本插件负责核心工程不变量、Android 全领域证据链和知识系统。
- 平台插件提供对应系统的 source-access 公开入口；源码接入和构建交付实现在本插件中各保留一套。
- 当个人规范和本插件流程都适用时，Codex 应同时满足个人规范，并保留本插件的源码证据、构建证据、设备验证证据和风险说明。
- `jinny-framework-coding-standards` 只在用户明确要求时叠加可选偏好；规范权威始终是本插件的 `android-change-policy`。

## 配置入口

成员个人配置不提交到插件仓库。常见配置位置：

```text
$CODEX_HOME/report/config.toml
$CODEX_HOME/<skill-name>.toml
<project>/.codex/report.toml
```

普通成员 TOML 只写身份和本地路径。服务器上传入口由 AKBS endpoint resolver 提供并默认指向 AKBS HTTP API；上传、搜索和合并确认只发送 member alias，服务端按固定工作站来源 IP 验证身份。缺 alias 时会在打包、HTTP 之前停止。成员不需要理解 SSH、服务器路径或 API 地址。知识库仓库工作树只作为可选离线搜索兜底，产物目录建议使用：

```text
<Codex documents>/worktrees/knowledge
<Codex documents>/artifacts/android-knowledge-intake
```

成员端通过私有配置指定 `out_dir`；如需要离线搜索兜底，可指定 `knowledge_repo_worktree`。成员端不需要数据库仓库工作区，也不需要填写服务器名、submit 脚本路径或知识库远端 URL。

## 验证

从仓库根目录执行：

```bash
scripts/validate_plugins.sh
```

修改本插件中的 Python 脚本后，额外执行：

```bash
python3 -m pytest --capture=no \
  tests/plugins/android-framework-ops/android-framework-patch-capture \
  tests/plugins/android-framework-ops/android-knowledge-intake \
  tests/plugins/android-framework-ops/android-knowledge-search
```

规则归属合同见 `plugins/android-framework-ops/skills/android-knowledge-intake/references/deterministic-rules-contract.md`。

## 维护边界

核心身份、补丁溯源、真实证据和领域安全规则必须由 `android-change-policy` 统一管理。个人代码风格、review 偏好和项目约定可以放在扩展或项目本地规则中，但不能覆盖核心合同。

不要提交真实配置、凭据、私钥、构建输出、日志、知识库 worktree 或 Codex 本地历史数据库。
