# android-knowledge-search

> GitHub 说明页。Runtime skill 文件位于 [../../../../plugins/android-framework-ops/skills/android-knowledge-search](../../../../plugins/android-framework-ops/skills/android-knowledge-search)；插件安装后的 skill 目录不包含本 README。文中的 `scripts/...`、`references/...` 指向该 runtime skill 目录。

团队知识库检索 skill。

## 用途

该 skill 默认优先调用 AKBS 成员只读搜索接口，搜索知识库里的案例、平台实现、补丁、修改文件、检索锚点（文件/类名/属性/资源 key）和可复用验证证据。服务端不可用、未授权、超时或合同不兼容时，会回退到本地知识库 JSONL 搜索，并明确标注 `source=local_jsonl_fallback`。

它的价值是让成员或其他 skill 在重新分析、重新开发之前，先查团队是否已经保存过类似功能、补丁或问题处理记录。

如果某个旧案例已经被本地知识沉淀技能标记为过期或存在反证，搜索结果会显示推荐替代案例。成员侧 Codex 应优先检查替代案例，再判断是直接复用、适配复用、仅作参考、不适用还是未命中。

日报、周报、incoming 事件、原始来源和工作过程证据属于人看归档。它们保留显式查询能力，但不进入默认 AI 复用检索结果。

## 典型场景

- 新需求来了，先查有没有类似 Framework 修改或既有补丁。
- 看到一个类名、属性、Settings key、资源 key，想知道以前哪个补丁改过。
- 管理员需要追溯日报、周报、incoming 事件或原始来源时，使用显式 `--type report`、`--type event` 或 `--type evidence`。
- 想确认某个 incoming 是否留下了可复用验证证据。
- 成员收到“等待确认合并”时，让 Codex 读取目标知识、合并依据和 compare 结果，生成是否需要提出异议的分析摘要。
- `android-framework-change-workflow` 在进入源码分析前，先查知识库作为参考材料。

## 常用命令

```bash
python3 "scripts/android_knowledge_search.py" \
  "电源键 frameworks/base" \
  --limit 8
```

默认 `--source auto` 会优先使用服务端搜索；请求只带 `X-AKBS-User=<member_alias>` 和内容协商头，服务器按固定来源 IP 验证身份。普通成员配置不需要写 `test35`、服务器路径或数据库仓库路径，endpoint 由 AKBS endpoint resolver 默认值提供；管理员/测试 override 可使用受控 `CODEX_REPORT_AKBS_ENDPOINT_*` 环境变量。

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

只搜归档记录或证据：

```bash
python3 "scripts/android_knowledge_search.py" \
  "电源键 rk3576" \
  --type event

python3 "scripts/android_knowledge_search.py" \
  "真机验证 services.jar" \
  --type evidence
```

默认 `--type all` 是 AI 复用视图，不返回 report/event，也不返回 `source`、`work_findings`、`report_context`、`package_check` 这类人看归档证据。默认搜索还会过滤已撤销（retracted）的案例、变体、补丁、符号和证据，并清理普通搜索证据负载里残留的已撤销对象引用，例如已废弃的 `search_before_change.results`。需要追溯来源或撤销证据时必须显式指定类型。

指定知识库仓库路径：

```bash
python3 "scripts/android_knowledge_search.py" \
  "WindowManager display" \
  --root /path/to/knowledge
```

离线强制本地 JSONL 搜索：

```bash
python3 "scripts/android_knowledge_search.py" \
  "WindowManager display" \
  --source local \
  --root /path/to/knowledge
```

本地 fallback 或显式 `--source local` 时，脚本会优先使用 `--root`、`CODEX_KNOWLEDGE_ROOT`、`CODEX_KNOWLEDGE_REPO_WORKTREE`、报告配置里的当前 profile `knowledge_repo_worktree`，再尝试当前目录父级和通用 `worktrees/knowledge` 路径。成员端应通过自己的 `config.toml` 或环境变量指向知识库仓库副本，不依赖维护者本机路径。

它不会自动读取数据库仓库或成员 incoming 工作区。管理员要排查数据库仓库内部数据时，必须显式传 `--root`。

服务端结果原样显示返回的 `search_mode`，并按 `reuse_grade` 展示：`reusable` 显示“可复用候选”，`reference_only` 显示“仅参考”，`insufficient_evidence` 显示“证据不足”，`different_function` 显示“功能不同”，`duplicate_source` 显示“重复来源线索”。本地 fallback 会提示“本地文本搜索，未经过服务端复用分级”，不能直接当作服务端可复用结论。

查看合并确认和依据：

```bash
python3 "scripts/android_knowledge_search.py" \
  --merge-confirmation list

python3 "scripts/android_knowledge_search.py" \
  --merge-confirmation analyze \
  --merge-confirmation-id review-20260703-member-patch
```

`list`、`detail`、`target`、`compare` 和 `analyze` 都是只读动作。`analyze` 会区分人看摘要和 Codex 分析证据；服务端不可用时会明确失败，不会伪造合并依据。只有成员明确要求发送异议时，才使用：

```bash
python3 "scripts/android_knowledge_search.py" \
  --merge-confirmation dispute \
  --merge-confirmation-id review-20260703-member-patch \
  --send-dispute \
  --dispute-reason "目标知识没有覆盖当前补丁的功能目标"
```

## 搜索使用证据

默认搜索会写入搜索使用证据（search usage evidence）到成员本地输出目录：

```text
$CODEX_HOME/artifacts/android-knowledge-intake/search-usage/<YYYYMMDD>/*.json
```

如果报告配置里设置了 `out_dir`，会写入该目录下的 `search-usage/`。日报包（daily report package）和补丁包（patch package）会读取这些记录，并生成 `materials/evidence/search_before_change.json`。

搜索使用证据会记录 `source`、`search_mode`、`reuse_grade`、`matched_channels`、`matched_anchors`，fallback 时还会记录 `fallback_reason`。

明确记录使用决策：

```bash
python3 "scripts/android_knowledge_search.py" \
  "电源键 rk3576" \
  --reuse-decision adapt \
  --reuse-target case-power-key \
  --reuse-reason "同类策略可参考，当前项目需适配"
```

取值包括 `reuse`、`adapt`、`reference_only`、`not_applicable`、`not_found` 和 `unknown`。这些只是成员侧开发证据，不是沉淀结论（curation decision）。

## 和其他 skill 的关系

```text
android-daily-report-intake / android-weekly-report-intake / android-framework-patch-intake
  负责按材料类型把日报、周报、补丁包打包成 incoming 并发送到服务器上传入口

android-framework-patch-capture
  负责把 Framework 修改整理成标准补丁资料

android-knowledge-intake
  提供共享脚本、当前配置诊断和插件更新检查

android-knowledge-search
  负责把知识库仓库里已有经验、补丁和验证结果搜出来

android-framework-change-workflow
  处理需求前先搜索；搜不到或参考材料不足，再进入分析、修改、验证流程
```

## 文件入口

- [SKILL.md](../../../../plugins/android-framework-ops/skills/android-knowledge-search/SKILL.md)：给 Codex 自动加载的执行说明。
- [references/search-contract.md](../../../../plugins/android-framework-ops/skills/android-knowledge-search/references/search-contract.md)：知识库检索输入、输出和判断边界。
- [scripts/android_knowledge_search.py](../../../../plugins/android-framework-ops/skills/android-knowledge-search/scripts/android_knowledge_search.py)：本地检索脚本。
