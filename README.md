# Android Framework Codex Suite

面向 Android Framework 团队的 Codex 插件套件。

这个仓库是 Android Framework 相关 Codex 能力的插件市场来源。团队成员安装 android-framework-ops 获得共享工程能力，再根据环境安装 android-wsl-ops（WSL）或 android-mac-ops（macOS）平台层插件。Jinny 团队实践和 Codex 工作区维护为可选安装。

## 插件一览

| 插件 | 定位 | 包含内容 | 推荐安装对象 |
| --- | --- | --- | --- |
| [android-framework-ops](plugins/android-framework-ops/README.md) | Android Framework 核心工程插件 | 需求分析、知识检索、远程执行、跨平台构建交付、补丁归档、incoming 上传材料 | 所有需要 Codex 处理 Android Framework 工程任务的成员 |
| [android-wsl-ops](plugins/android-wsl-ops/README.md) | WSL 平台插件 | WSL Samba/CIFS 源码接入 | 在 WSL 环境中使用 Codex 的成员 |
| [android-mac-ops](plugins/android-mac-ops/README.md) | macOS 平台插件 | macOS 原生 SMB 源码接入和 Keychain 凭据引用 | 在 macOS 环境中使用 Codex 的成员 |
| [jinny-android-practices](plugins/jinny-android-practices/README.md) | 可选团队实践插件 | Jinny 团队代码风格、FrameworkLog 规范、review、项目本地规范等有倾向性的规则入口 | 想沿用 Jinny 团队实践的成员 |
| [codex-workspace-care](plugins/codex-workspace-care/README.md) | 独立工作区维护插件 | Codex 本地聊天历史清理、修复、隐私残留检查、上下文交接 | 需要维护本地 Codex 状态或迁移会话上下文的成员 |

`codex-chat-history-cleaner` 和 `codex-chat-history-context-extractor` 不属于 Android Framework 工程链路，所以放在独立插件 `codex-workspace-care` 中。

## 设计原则

`android-framework-ops` 是中立核心插件，也是团队默认主链路。它只提供 Android Framework 专项工程能力，不强制替代成员自己的代码风格 skill、项目 `AGENTS.md`、本地规范或 review workflow。

当成员同时安装自己的 skill、项目本地规则和本仓库插件时，预期组合方式是：

1. 用户当前明确要求和项目本地规范优先。
2. 个人或团队实践 skill 负责代码风格、review 口径、项目偏好。
3. `android-framework-ops` 负责 Framework 工程闭环：知识检索、诊断修改、验收证据、补丁归档、incoming 上传材料。
4. `android-framework-ops` 使用一套跨平台远程构建和本地 adb 交付实现。
5. `android-wsl-ops` 或 `android-mac-ops` 只提供当前操作系统的源码挂载。
6. `codex-workspace-care` 只在用户明确需要处理本地 Codex 历史或交接上下文时使用。

这样做的目的很直接：核心插件可以给很多人用，但不把某个人的编码习惯绑定进所有人的工作流。

## Android Framework 工作流

一句话：`android-source-access` 负责连接服务器源码，`android-knowledge-search` 负责开工前先查知识，`android-framework-change-workflow` 负责分析和改代码并给验收结论，`android-remote-channel` 负责稳定执行服务器命令，`android-remote-build-deploy` 用一套实现完成远程编译和本地设备推送，`android-framework-patch-capture` 负责整理功能级补丁资料，`android-framework-patch-intake`、`android-daily-report-intake`、`android-weekly-report-intake` 负责按材料类型生成 incoming，`android-knowledge-intake` 承载共享内核、doctor 和版本门禁。

| 阶段 | 负责 skill | 职责 |
| --- | --- | --- |
| 源码接入 / 路径映射 | `android-source-access` | 把服务器 Android 源码挂载到本地，并记录本地路径、远程路径、SSH 主机映射 |
| 开工前查知识库 | `android-knowledge-search` | 默认搜索知识库仓库里的可复用案例、平台实现、补丁、检索锚点和验证证据，判断是否有可复用方案 |
| 需求分析 / 代码修改 | `android-framework-change-workflow` | 分析需求或 bug，查源码，改代码，加必要调试日志，判断风险和回滚路径 |
| 远程命令执行 | `android-remote-channel` | 管理 SSH/tmux 长会话、命令日志、占用状态和锁，避免多个 Codex 会话互相踩远程环境 |
| 编译 / 产物定位 / 推送 | `android-remote-build-deploy` | 调用服务器编译 Android，定位 jar/apk 等产物，并推送到设备 |
| 功能验证 / 验收结论 | `android-framework-change-workflow` | 根据需求、日志、设备行为、风险矩阵判断任务是否完成，并决定包状态（package status） |
| 补丁资料整理 | `android-framework-patch-capture` | 把已完成、阶段性、失败或阻塞但有价值的 Framework 功能整理成一个功能 README、多源码仓库 patch、修改文件证据、符号事实和验证材料 |
| 补丁包上传材料 | `android-framework-patch-intake` | 生成一个完整 `framework_change` 补丁包；服务端以 `patch_package_id` 贯穿队列和主分支，并按 `request_id` 为同包补充资料 |
| 日报上传材料 | `android-daily-report-intake` | 按 Patch/App 范围生成个人日报正文、同源 UI 读模型和 `daily_trace` incoming |
| 周报上传材料 | `android-weekly-report-intake` | 按 Patch/App 范围汇总当前有效日报和上一周项目台账，由主责确认本周流转并自动校验总量、Android 剩余和 BSP 跟踪，生成个人周报、同源 UI 读模型和 `weekly_trace` incoming |
| 共享内核 / 配置诊断 | `android-knowledge-intake` | 提供成员配置、doctor、插件更新、版本门禁、会话缓存门禁和 manifest 协议 |

`android-remote-build-deploy` 只证明产物是否编出、是否推上设备；最终能不能算需求完成，由 `android-framework-change-workflow` 结合需求和验证证据判断。

Framework 需求默认闭环是：开工前查 AKBS，开发和验证后通过 `patch-capture` 与 `android-framework-patch-intake` 生成一个 `validated` 补丁包，并由 AKBS HTTP API 写入上传队列。服务端生成的 `patch_package_id` 是队列和主分支唯一业务身份；上传目录的 `package_key` 只标识不可变物理来源。成员 Skill 负责功能边界、项目/平台/Android 版本、不可变补丁和真实验证的主要完整性检查；管理端队列检查只作安全兜底。轻量文字、字段或非补丁附件缺口通过事件 `request_id` 补到同一个补丁包，需要改补丁或拆分功能则退回重新生成。通知、资料请求和合并确认分别继续用自身事件 ID 追溯因果，不替代 `patch_package_id`。`candidate`、`draft`、失败或阻塞路径保留在本地材料或报告上下文，不进入队列。日报和周报只归档，不进入知识沉淀候选；新建知识或计划合并由管理端沉淀流程决定。

按环境选择对应平台层插件：WSL 环境安装 `android-wsl-ops`，macOS 环境安装 `android-mac-ops`。

## 服务器源码树命令边界

这里的命令只指在远程 Android 源码树 `REMOTE_ROOT` 里执行的命令。

| Skill | 会在服务器源码树上执行的典型命令 |
| --- | --- |
| `android-knowledge-search` | 通常不在服务器源码树执行命令，只读取知识库仓库 JSONL 索引和权威对象目录 |
| `android-framework-change-workflow` | `rg`, `sed`, `git diff`, `git status`，以及必要的源码修改或调试日志/监控 |
| `android-framework-patch-capture` | `git status`, `git diff HEAD`，读取一个或多个源码仓库变更并生成一个功能 README、仓库级 patch 和 evidence 文件 |
| `android-remote-build-deploy` | `git status`, `repo status`, `.codex/build-push.sh plan/build`, `.codex/build-session.sh` 中的构建封装 |
| `android-remote-channel` | `tmux`, `cd <REMOTE_ROOT>`, `tail`, `cat`, `mkdir`, `rm`, `flock` |
| `android-source-access` | 通常不执行开发命令，只做 `test -d`, `ls`, `find` 这类源码识别命令 |

## 目录结构

```text
android-framework-codex-suite/
├── .agents/plugins/marketplace.json        # Codex 本地 marketplace 入口
├── plugins/
│   ├── android-framework-ops/              # Android Framework 核心工程插件
│   ├── android-wsl-ops/                  # WSL 平台层插件
│   ├── android-mac-ops/                  # macOS 平台层插件
│   ├── jinny-android-practices/            # 可选团队实践插件
│   └── codex-workspace-care/               # 独立工作区维护插件
├── manifests/                              # 每个插件包含的 skill 白名单
├── docs/
│   ├── skills/                             # GitHub 上给人看的每个 skill 说明
│   └── archive/                            # 历史计划归档，不作为当前结构事实
└── scripts/                                # 插件校验脚本
```

每个插件必须保留 `.codex-plugin/plugin.json`。插件可安装入口由 `.agents/plugins/marketplace.json` 管理。

`plugins/<plugin>/skills/<skill>/` 是 Codex runtime skill 目录，只放 `SKILL.md`、`agents/`、`scripts/`、`references/`、`assets/` 等执行需要的文件，不放 `README.md`。GitHub 上给人看的每个 skill 说明统一放在 `docs/skills/<plugin>/<skill>/README.md`，并从插件级 README 链过去。

## 安装

成员通过 Codex 插件市场安装和更新本仓库，不需要手工复制或同步 skill 到本地技能目录。

在 Codex 插件市场添加 marketplace：

```text
来源：jinny51/android-framework-codex-suite
Git 引用：main
稀疏路径：留空
```

安装后，Android Framework 相关 skill 来自 Codex 插件缓存。成员不需要额外维护手工同步链路。

推荐安装顺序：

1. 需要 Android Framework 工程能力：安装 `android-framework-ops`。
2. WSL 环境：安装 `android-wsl-ops`。
3. macOS 环境：安装 `android-mac-ops`。
4. 需要 Jinny 团队代码风格、补丁开发规范和 FrameworkLog 日志规范：额外安装 `jinny-android-practices`，使用 `jinny-framework-coding-standards`。
5. 需要处理 Codex 本地历史或交接上下文：额外安装 `codex-workspace-care`。

维护者本地开发插件时才需要 clone 本仓库并运行校验脚本。

## 配置

成员个人配置不提交到本仓库。

常见配置位置：

```text
$CODEX_HOME/report/config.toml
$CODEX_HOME/<skill-name>.toml
<project>/.codex/report.toml
```

普通成员 TOML 只写身份和本地路径。服务器上传入口和只读知识库入口由 AKBS endpoint resolver 提供；上传认证必须由受保护进程环境显式提供成员 token，缺失时 doctor 和上传会在打包、HTTP 之前停止，且不会再把 member alias 当作 token。知识库仓库工作树和产物目录建议按成员私有配置指定：

```text
<Codex documents>/worktrees/knowledge
<Codex documents>/artifacts/android-knowledge-intake
```

这些路径是模板，不是插件硬编码要求。团队成员应在自己的 `config.toml` profile 中设置 `knowledge_repo_worktree` 和 `out_dir`；成员端不配置服务器名、submit 脚本路径、知识库远端 URL 或数据库仓库工作树。

## 维护

普通成员默认只需要安装和更新插件，不需要向本仓库提交。

维护者更新流程：

```bash
# 1. 在本仓库中修改插件、skill、脚本或文档
# 2. 在实际使用环境中验证相关工作流

# 3. 自检
scripts/validate_plugins.sh

# 4. 只暂存本次文件，提交并推送
git add <本次修改文件>
git commit -m "update plugins"
git push

# 5. 刷新 marketplace，并重装本机实际使用的平台插件
codex plugin marketplace upgrade android-framework-codex-suite
codex plugin add android-framework-ops@android-framework-codex-suite
codex plugin add android-wsl-ops@android-framework-codex-suite  # 仅 WSL
```
macOS 只安装 `android-mac-ops`，WSL 只安装 `android-wsl-ops`。安装更新了磁盘缓存，但已经打开的会话不会因此自动替换本轮加载的 skill；受影响工作应在新会话中继续，活跃会话只做定向事实刷新。

不要提交成员个人配置、真实凭据、私钥、构建输出、日志、`__pycache__`、`.pytest_cache` 或本地历史数据库。

## 自检

提交前至少执行：

```bash
scripts/validate_plugins.sh
```

验证内容包括：

- 每个插件都有 `.codex-plugin/plugin.json`。
- marketplace 中声明的插件路径有效。
- manifest 中列出的 skill 都存在。
- skill 目录包含必要入口文件。
- macOS 源码接入脚本通过模拟回归；发布 macOS 插件前还必须通过真实 Mac SSH 回归。
- WSL 源码接入脚本在 Git 中可执行；共享构建交付在 WSL 与真实 Mac SSH 环境回归通过。
- 仓库没有明显的本地缓存、日志、凭据类文件。

维护时如果只想快速确认 runtime skill 目录里没有 README 残留，可以执行：

```bash
find plugins -path '*/skills/*/README.md' -print
```

没有输出就是符合当前约定。

如果修改了 Python 脚本或材料上传/检索逻辑，额外执行：

```bash
python3 -m pytest --capture=no \
  tests/plugins/android-framework-ops/android-framework-patch-capture \
  tests/plugins/android-framework-ops/android-knowledge-intake \
  tests/plugins/android-framework-ops/android-knowledge-search \
  tests/plugins/codex-workspace-care/codex-chat-history-cleaner
```

在 `/mnt/c` 文件系统上运行 pytest 时，默认 capture 可能受临时文件行为影响；这里固定使用 `--capture=no`。

## 新增插件或 skill

新增 skill 时，需要同时更新：

```text
plugins/<plugin-name>/skills/<skill-name>/
docs/skills/<plugin-name>/<skill-name>/README.md
manifests/<plugin-name>.toml
plugins/<plugin-name>/README.md
README.md
```

新增插件时，需要同时更新：

```text
plugins/<plugin-name>/.codex-plugin/plugin.json
.agents/plugins/marketplace.json
manifests/<plugin-name>.toml
plugins/<plugin-name>/README.md
README.md
scripts/validate_plugins.sh
```

实践类、代码风格类、review 类规则默认放进 `jinny-android-practices` 或其他可选插件，不放进 `android-framework-ops`。
