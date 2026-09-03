# akbs-patch-submit

成员侧 Android change 入口，按精确合同分成三条不会互相降级的路径：

读取、检查、prepare、capture preflight、归档或服务端请求前，必须先运行
`akbs_member_setup.py preflight-install-family` 并取得 `status=PASS`。只有真正的
parser `--help` 可以跳过；`--` 后面的字面 `--help` 仍是业务输入。

- `knowledge-incoming-package/1/framework_change`：永久兼容读取，并继续通过 incoming v1 真实提交。
- `akbs-android-change-package-v2/2/android_change`：覆盖 application、platform、native、HAL、kernel、device、build，当前只开放本地 read/check/prepare。
- `android-patch-capture-package-v2/2.0/android_change_capture`：保留零网络、零写的兼容 preflight；不能把 capture 目录直接交给 `prepare`。
- `android-patch-capture-package-v2/2.1/android_change_capture`：作为 Phase 4 的离线 materializer 输入，按 hash-pinned 37 组 qualification 合同生成 canonical v2；首轮只启用 application/platform，其余层返回 `layer_not_enabled`。

v2 的本地 PASS 只代表 `client_semantic_coherence_valid`。客户端 adapter outputs 仍是 untrusted input，服务端必须重新计算资格；当前证据 profile 明确将 writer 设为 blocked，所以 submit 在任何更新检查网络、tar、HTTP、receipt 或 v1 fallback 前返回 `android_change_v2_writer_off`。

所有 v2 真实动作先以 `codex plugin list --json` 证明 target-only active family，并严格绑定唯一 target 条目的 `pluginId`、version、absolute marketplace `source.path` 与当前进程的精确 versioned cache；两边 direct manifest 字节和完整发布内容及 regular-file executable-bit 的规范化树 hash 必须一致（只排除 `__pycache__`/`.pyc`）。命令失败、JSON/version 畸形、symlink、路径/身份/内容不符、混装或目标插件未激活时均 fail closed，`--help` 不受业务 gate 影响。组件只接受合同中的 canonical `layer`、`type`、`partition`、`ownership`；v1 的 `change_domain` 不会被用来推导这些 facet。

```bash
python3 "scripts/akbs_patch_submit.py" android-change-v2 read /path/to/package
python3 "scripts/akbs_patch_submit.py" android-change-v2 check /path/to/package
python3 "scripts/akbs_patch_submit.py" android-change-v2 prepare /path/to/package
python3 "scripts/akbs_patch_submit.py" android-change-v2 submit /path/to/package
python3 "scripts/akbs_patch_submit.py" android-change-v2 adapt-capture /path/to/capture
```

对于 2.0，`adapt-capture` 先按插件内 hash-pinned Draft 2020-12 capture
schema 严格校验，再检查 identity/结构、validated
状态链、local-only authority、除 manifest 自身外的全量 regular-file
SHA-256 inventory、patch SHA-1、`components[]`、`primary_component_id`、每个
repository/patch 的 `component_ids[]`、evidence 与 qualification bindings。
检查成功仍返回非零的结构化 `BLOCKED`，且不创建 canonical 包、
client-adapter outputs、receipt 或伪 PASS。

对于 2.1，同一命令按 component 精确校验证据，并通过 machine-validated
versioned adapter input schema 生成确定性的 hash-bound canonical v2 包；
重复执行复用同一结果，原 capture 不改写。
client adapter 输出仍是 untrusted input，`server_qualified=false`，不发
HTTP，也不进入 v1 fallback。v2 server writer 继续关闭。

`prepare` 不生成或补写 adapter PASS，只在完整 schema、profile SHA、qualification hash、组件/证据绑定及目录 bytes 全部通过后，把输入原样保存到：

```text
$CODEX_HOME/artifacts/akbs-member-ops/android-change-v2/pending/<member_alias>/<run_id>/
```

legacy Framework v1-compatible capture 用法保持：

```bash
python3 "scripts/akbs_patch_submit.py" --profile <member_alias> --prepare \
  --patch-package /path/to/capture --project TVE8402M \
  --platform rk --android-version 14 --summary "功能补丁摘要" --status validated
python3 "scripts/akbs_patch_submit.py" --profile <member_alias> --submit-latest
```

需要修改源码或重新抓取补丁时使用 `$android-patch-capture`，随后显式运行
`adapt-capture`；不得把该 capture 直接 `prepare`。旧
`$android-framework-patch-intake` 与 umbrella CLI 仅作 v1 迁移薄转发；不能把
v2 或 `android_change_capture` 静默改写为 `framework_change`。
