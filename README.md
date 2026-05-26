# Android Framework Codex Suite

面向 Android Framework 团队的 Codex 插件套件。

这个仓库是 Android Framework 相关 Codex 能力的插件市场来源。团队成员可以只安装 Android Framework 工程核心能力，也可以额外安装 Jinny 团队实践规则，或者单独安装 Codex 本地工作区维护工具。

## 插件一览

| 插件 | 定位 | 包含内容 | 推荐安装对象 |
| --- | --- | --- | --- |
| [android-framework-ops](plugins/android-framework-ops/README.md) | Android Framework 工程核心插件 | 源码接入、知识检索、需求分析、远程执行、构建推送、验收、补丁归档、知识入库 | 所有需要 Codex 处理 Android Framework 工程任务的成员 |
| [jinny-android-practices](plugins/jinny-android-practices/README.md) | 可选团队实践插件 | Jinny 团队代码风格、review、项目本地规范等有倾向性的规则入口 | 想沿用 Jinny 团队实践的成员 |
| [codex-workspace-care](plugins/codex-workspace-care/README.md) | 独立工作区维护插件 | Codex 本地聊天历史清理、修复、隐私残留检查、上下文交接 | 需要维护本地 Codex 状态或迁移会话上下文的成员 |

`codex-chat-history-cleaner` 和 `codex-chat-history-context-extractor` 不属于 Android Framework 工程链路，所以放在独立插件 `codex-workspace-care` 中。

## 设计原则

`android-framework-ops` 是中立核心插件。它只提供 Android Framework 专项工程能力，不强制替代成员自己的代码风格 skill、项目 `AGENTS.md`、本地规范或 review workflow。

当成员同时安装自己的 skill、项目本地规则和本仓库插件时，预期组合方式是：

1. 用户当前明确要求和项目本地规范优先。
2. 个人或团队实践 skill 负责代码风格、review 口径、项目偏好。
3. `android-framework-ops` 负责 Framework 工程闭环：源码接入、历史检索、诊断修改、远程构建、设备推送、验收证据、补丁归档、知识入库。
4. `codex-workspace-care` 只在用户明确需要处理本地 Codex 历史或交接上下文时使用。

这样做的目的很直接：核心插件可以给很多人用，但不把某个人的编码习惯绑定进所有人的工作流。

## Android Framework 工作流

一句话：`source-access` 负责连接服务器源码，`android-knowledge-search` 负责开工前先查知识库，`android-framework-change-workflow` 负责分析和改代码并给验收结论，`android-remote-channel` 负责稳定执行服务器命令，`remote-build-deploy` 负责编译和推送设备，`android-framework-patch-capture` 与 `android-knowledge-intake` 负责把结果沉淀回知识库。

| 阶段 | 负责 skill | 职责 |
| --- | --- | --- |
| 源码接入 / 路径映射 | `android-wsl-source-access` / `android-windows-source-access` | 把服务器 Android 源码连接到当前 Codex 环境，并记录本地路径、远程路径、SSH 主机映射 |
| 开工前查知识库 | `android-knowledge-search` | 搜索历史日报、周报、补丁、代码标识、验证证据，判断是否有可复用方案 |
| 需求分析 / 代码修改 | `android-framework-change-workflow` | 分析需求或 bug，查源码，改代码，加必要调试日志，判断风险和回滚路径 |
| 远程命令执行 | `android-remote-channel` | 管理 SSH/tmux 长会话、命令日志、占用状态和锁，避免多个 Codex 会话互相踩远程环境 |
| 编译 / 产物定位 / 推送 | `android-wsl-remote-build-deploy` / `android-windows-remote-build-deploy` | 调用服务器编译 Android，定位 jar/apk 等产物，并推送到设备 |
| 功能验证 / 验收结论 | `android-framework-change-workflow` | 根据需求、日志、设备行为、风险矩阵判断任务是否完成 |
| 补丁资料整理 | `android-framework-patch-capture` | 把已完成或阶段性 Framework 修改整理成 patch、说明、修改文件证据、符号事实和验证材料 |
| 知识入库 | `android-knowledge-intake` | 把日报、周报或补丁包提交到团队知识库 incoming 协议 |

`remote-build-deploy` 只证明产物是否编出、是否推上设备；最终能不能算需求完成，由 `android-framework-change-workflow` 结合需求和验证证据判断。

## 服务器源码树命令边界

这里的命令只指在远程 Android 源码树 `REMOTE_ROOT` 里执行的命令。

| Skill | 会在服务器源码树上执行的典型命令 |
| --- | --- |
| `android-knowledge-search` | 通常不在服务器源码树执行命令，只读取知识库 `index/knowledge.sqlite` 或 `index/*.jsonl` |
| `android-framework-change-workflow` | `rg`, `sed`, `git diff`, `git status`，以及必要的源码修改或调试日志/监控 |
| `android-framework-patch-capture` | `git status`, `git diff HEAD`，读取变更并生成 patch、说明和 evidence 文件 |
| `android-wsl-remote-build-deploy` | `git status`, `repo status`, `.codex/build-push.sh plan/build`, `.codex/build-session.sh` 中的构建封装 |
| `android-windows-remote-build-deploy` | `git status`, `repo status`, `.codex/build-push.sh plan/build`，通过 SMB/UNC 取产物并用本地 `adb.exe` 推送 |
| `android-remote-channel` | `tmux`, `cd <REMOTE_ROOT>`, `tail`, `cat`, `mkdir`, `rm`, `flock` |
| `android-wsl-source-access` / `android-windows-source-access` | 通常不执行开发命令，只做 `test -d`, `ls`, `find` 这类源码识别命令 |

## 目录结构

```text
android-framework-codex-suite/
├── .agents/plugins/marketplace.json        # Codex 本地 marketplace 入口
├── plugins/
│   ├── android-framework-ops/              # Android Framework 核心工程插件
│   ├── jinny-android-practices/            # 可选团队实践插件
│   └── codex-workspace-care/               # 独立工作区维护插件
├── manifests/                              # 每个插件包含的 skill 白名单
├── docs/                                   # 设计文档和实施计划
└── scripts/                                # 插件校验脚本
```

每个插件必须保留 `.codex-plugin/plugin.json`。插件可安装入口由 `.agents/plugins/marketplace.json` 管理。

## 安装

### WSL / Linux

```bash
repo="$HOME/Documents/Codex/plugins/android-framework-codex-suite"
git clone https://github.com/jinny51/android-framework-codex-suite.git "$repo"
```

然后在支持本地 marketplace 的 Codex 环境中选择：

```text
$HOME/Documents/Codex/plugins/android-framework-codex-suite/.agents/plugins/marketplace.json
```

### Windows PowerShell

```powershell
$repo = Join-Path $HOME "Documents\Codex\plugins\android-framework-codex-suite"
git clone https://github.com/jinny51/android-framework-codex-suite.git $repo
```

然后在 Codex 中选择：

```text
%USERPROFILE%\Documents\Codex\plugins\android-framework-codex-suite\.agents\plugins\marketplace.json
```

推荐安装顺序：

1. 需要 Android Framework 工程能力：安装 `android-framework-ops`。
2. 需要 Jinny 团队代码风格和 review 规则：额外安装 `jinny-android-practices`。
3. 需要处理 Codex 本地历史或交接上下文：额外安装 `codex-workspace-care`。

## 配置

成员个人配置不提交到本仓库。

常见配置位置：

```text
$CODEX_HOME/report/config.toml
$CODEX_HOME/<skill-name>.toml
<project>/.codex/report.toml
```

知识库和产物目录建议放在 Codex 工作区数据目录，而不是旧的 `$CODEX_HOME/report/knowledge-*` 或 `$CODEX_HOME/android-knowledge-intake/out`：

```text
<Codex documents>/worktrees/knowledge-<member_alias>
<Codex documents>/artifacts/android-knowledge-intake
```

当前维护者本机使用的迁移后路径是：

```text
/mnt/c/Users/jinny/Documents/Codex/worktrees/knowledge-jinny
/mnt/c/Users/jinny/Documents/Codex/worktrees/knowledge-test
/mnt/c/Users/jinny/Documents/Codex/artifacts/android-knowledge-intake
/mnt/c/Users/jinny/.codex/report/config.toml
```

这些路径是维护者配置，不是插件对所有成员的硬编码要求。团队成员应在自己的 `config.toml` profile 中设置实际路径。

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

Windows PowerShell：

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
