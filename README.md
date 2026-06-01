# Android Framework Codex Suite

面向 Android Framework 团队的 Codex 插件套件。

这个仓库是 Android Framework 相关 Codex 能力的插件市场来源。团队成员可以只安装 WSL 主链路 Android Framework 工程核心能力，也可以额外安装 Windows 原生兼容层、Jinny 团队实践规则，或者单独安装 Codex 本地工作区维护工具。

## 插件一览

| 插件 | 定位 | 包含内容 | 推荐安装对象 |
| --- | --- | --- | --- |
| [android-framework-ops](plugins/android-framework-ops/README.md) | Android Framework WSL 主链路核心插件 | WSL 源码接入、知识检索、需求分析、远程执行、构建推送、验收、补丁归档、知识入库 | 所有需要 Codex 处理 Android Framework 工程任务的成员 |
| [android-framework-windows-ops](plugins/android-framework-windows-ops/README.md) | 可选 Windows 原生兼容插件 | Windows SMB/UNC 源码映射、PowerShell/ssh.exe 远程会话、本地 adb.exe 推送 | 确实需要 Windows 原生 Codex 的成员 |
| [jinny-android-practices](plugins/jinny-android-practices/README.md) | 可选团队实践插件 | Jinny 团队代码风格、review、项目本地规范等有倾向性的规则入口 | 想沿用 Jinny 团队实践的成员 |
| [codex-workspace-care](plugins/codex-workspace-care/README.md) | 独立工作区维护插件 | Codex 本地聊天历史清理、修复、隐私残留检查、上下文交接 | 需要维护本地 Codex 状态或迁移会话上下文的成员 |

`codex-chat-history-cleaner` 和 `codex-chat-history-context-extractor` 不属于 Android Framework 工程链路，所以放在独立插件 `codex-workspace-care` 中。

## 设计原则

`android-framework-ops` 是中立核心插件，也是团队默认 WSL 主链路。它只提供 Android Framework 专项工程能力，不强制替代成员自己的代码风格 skill、项目 `AGENTS.md`、本地规范或 review workflow。

当成员同时安装自己的 skill、项目本地规则和本仓库插件时，预期组合方式是：

1. 用户当前明确要求和项目本地规范优先。
2. 个人或团队实践 skill 负责代码风格、review 口径、项目偏好。
3. `android-framework-ops` 负责 WSL 主链路 Framework 工程闭环：源码接入、历史检索、诊断修改、远程构建、设备推送、验收证据、补丁归档、知识入库。
4. `android-framework-windows-ops` 只在 Windows 原生 Codex 场景中作为可选兼容层使用。
5. `codex-workspace-care` 只在用户明确需要处理本地 Codex 历史或交接上下文时使用。

这样做的目的很直接：核心插件可以给很多人用，但不把某个人的编码习惯绑定进所有人的工作流。

## Android Framework 工作流

一句话：`android-wsl-source-access` 负责连接服务器源码，`android-knowledge-search` 负责开工前先查知识库，`android-framework-change-workflow` 负责分析和改代码并给验收结论，`android-remote-channel` 负责稳定执行服务器命令，`android-wsl-remote-build-deploy` 负责编译和推送设备，`android-framework-patch-capture` 与 `android-knowledge-intake` 负责把结果沉淀回知识库。

| 阶段 | 负责 skill | 职责 |
| --- | --- | --- |
| 源码接入 / 路径映射 | `android-wsl-source-access` | 把服务器 Android 源码挂载或恢复到 WSL，并记录本地路径、远程路径、SSH 主机映射 |
| 开工前查知识库 | `android-knowledge-search` | 搜索历史报告、补丁、检索锚点、验证证据，判断是否有可复用方案 |
| 需求分析 / 代码修改 | `android-framework-change-workflow` | 分析需求或 bug，查源码，改代码，加必要调试日志，判断风险和回滚路径 |
| 远程命令执行 | `android-remote-channel` | 管理 SSH/tmux 长会话、命令日志、占用状态和锁，避免多个 Codex 会话互相踩远程环境 |
| 编译 / 产物定位 / 推送 | `android-wsl-remote-build-deploy` | 调用服务器编译 Android，定位 jar/apk 等产物，并推送到设备 |
| 功能验证 / 验收结论 | `android-framework-change-workflow` | 根据需求、日志、设备行为、风险矩阵判断任务是否完成，并决定知识成熟度 |
| 补丁资料整理 | `android-framework-patch-capture` | 把已完成、阶段性、失败或阻塞但有价值的 Framework 修改整理成 patch、说明、修改文件证据、符号事实和验证材料 |
| 知识入库 | `android-knowledge-intake` | 生成并提交 `daily_trace`、`weekly_trace` 或 `framework_change` incoming 包 |

`remote-build-deploy` 只证明产物是否编出、是否推上设备；最终能不能算需求完成，由 `android-framework-change-workflow` 结合需求和验证证据判断。

Framework 需求默认闭环是：开工前查知识库，开发和验证后通过 `patch-capture` 与 `knowledge-intake` 生成 incoming。验证通过的修改按 `validated`，需要复验的修改按 `candidate`，未完成但有价值的修改按 `draft`，失败或阻塞路径按 `failed` / `blocked` 保留。这样知识不会因为成员没有手动整理而只留在本机或会话里。

Windows 原生 Codex 场景不属于团队默认主链路。确实需要 SMB/UNC、PowerShell 和本地 `adb.exe` 交付时，额外安装 `android-framework-windows-ops`。

## 服务器源码树命令边界

这里的命令只指在远程 Android 源码树 `REMOTE_ROOT` 里执行的命令。

| Skill | 会在服务器源码树上执行的典型命令 |
| --- | --- |
| `android-knowledge-search` | 通常不在服务器源码树执行命令，只读取知识库 `index/knowledge.sqlite` 或 `index/*.jsonl` |
| `android-framework-change-workflow` | `rg`, `sed`, `git diff`, `git status`，以及必要的源码修改或调试日志/监控 |
| `android-framework-patch-capture` | `git status`, `git diff HEAD`，读取变更并生成 patch、说明和 evidence 文件 |
| `android-wsl-remote-build-deploy` | `git status`, `repo status`, `.codex/build-push.sh plan/build`, `.codex/build-session.sh` 中的构建封装 |
| `android-remote-channel` | `tmux`, `cd <REMOTE_ROOT>`, `tail`, `cat`, `mkdir`, `rm`, `flock` |
| `android-wsl-source-access` | 通常不执行开发命令，只做 `test -d`, `ls`, `find` 这类源码识别命令 |

## 目录结构

```text
android-framework-codex-suite/
├── .agents/plugins/marketplace.json        # Codex 本地 marketplace 入口
├── plugins/
│   ├── android-framework-ops/              # Android Framework 核心工程插件
│   ├── android-framework-windows-ops/      # 可选 Windows 原生兼容插件
│   ├── jinny-android-practices/            # 可选团队实践插件
│   └── codex-workspace-care/               # 独立工作区维护插件
├── manifests/                              # 每个插件包含的 skill 白名单
├── docs/
│   ├── skills/                             # GitHub 上给人看的每个 skill 说明
│   └── plans/                              # 设计文档和实施计划
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
2. 确实需要 Windows 原生 SMB/UNC + PowerShell 工作流：额外安装 `android-framework-windows-ops`。
3. 需要 Jinny 团队代码风格和 review 规则：额外安装 `jinny-android-practices`。
4. 需要处理 Codex 本地历史或交接上下文：额外安装 `codex-workspace-care`。

维护者本地开发插件时才需要 clone 本仓库并运行校验脚本。

## 配置

成员个人配置不提交到本仓库。

常见配置位置：

```text
$CODEX_HOME/report/config.toml
$CODEX_HOME/<skill-name>.toml
<project>/.codex/report.toml
```

知识库和产物目录建议放在 Codex 工作区数据目录：

```text
<Codex documents>/worktrees/knowledge-<member_alias>
<Codex documents>/artifacts/android-knowledge-intake
```

这些路径是模板，不是插件硬编码要求。团队成员应在自己的 `config.toml` profile 中设置实际路径；管理员本机路径也只应该存在于管理员自己的私有配置中。

## 维护

普通成员默认只需要安装和更新插件，不需要向本仓库提交。

维护者更新流程：

```bash
# 1. 在本仓库中修改插件、skill、脚本或文档
# 2. 在实际使用环境中验证相关工作流

# 3. 自检
scripts/validate_plugins.sh

# 4. 提交并推送
git add .
git commit -m "update plugins"
git push
```

Windows 原生兼容插件维护者也可以执行 PowerShell 入口：

```powershell
.\scripts\validate_plugins.ps1
git add .
git commit -m "update plugins"
git push
```

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
- 仓库没有明显的本地缓存、日志、凭据类文件。

维护时如果只想快速确认 runtime skill 目录里没有 README 残留，可以执行：

```bash
find plugins -path '*/skills/*/README.md' -print
```

没有输出就是符合当前约定。

如果修改了 Python 脚本或入库/检索逻辑，额外执行：

```bash
python3 -m pytest --capture=no \
  plugins/android-framework-ops/skills/android-framework-patch-capture/tests \
  plugins/android-framework-ops/skills/android-knowledge-intake/tests \
  plugins/android-framework-ops/skills/android-knowledge-search/tests \
  plugins/codex-workspace-care/skills/codex-chat-history-cleaner/tests
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
scripts/validate_plugins.ps1
```

实践类、代码风格类、review 类规则默认放进 `jinny-android-practices` 或其他可选插件，不放进 `android-framework-ops`。
