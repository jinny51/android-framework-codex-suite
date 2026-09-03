# android-change-workflow

> GitHub 说明页。Runtime Skill 位于 [../../../../plugins/android-engineering-ops/skills/android-change-workflow](../../../../plugins/android-engineering-ops/skills/android-change-workflow)。

Android 工程 controller 的唯一入口，覆盖 application、platform、native、HAL、kernel、device 和 build。它拥有 requirement contract、阶段、Gate、assignment/result 校验与最终验收；可选 practices provider 只返回 schema/hash 绑定的决策，不能 spawn、写入、取锁或宣布验收。

任何项目/源码读取、本地或远端命令、设备操作、委派和写入前，都必须先通过当前安装插件的 target-only family gate；这个要求同样适用于 `local_project` 和直接 `adb`，旧新插件混装时失败关闭。

Extension 按项目配置优先于本地配置解析；选择 provider 后只从 Codex active installed+enabled inventory 取得固定插件根，异常 fail closed，能力缺失或不适用才回 core。

Canonical layer 只有 application/platform/native/hal/kernel/device/build；type、partition、ownership 正交且不互相推断。任何 layer 的 validated 包均可进入 `akbs-patch-submit` 的 v2 本地检查/byte-preserving prepare；writer-off 时不产生网络副作用，也不回落 Framework v1。
