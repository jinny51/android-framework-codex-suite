# android-remote-channel

> GitHub 说明页。Runtime Skill 位于 [../../../../plugins/android-engineering-ops/skills/android-remote-channel](../../../../plugins/android-engineering-ops/skills/android-remote-channel)。

为 registered remote Android tree 提供稳定 SSH/tmux command channel、workspace identity、读写锁、命令恢复和结果回读。它是远端源码读取、修改、Git、构建和 snapshot 的唯一执行通道；source-access 的 direct SSH 仅用于接入基础设施。

任何 SSH、远端读取、状态、锁或命令分发前必须通过 target-only install-family gate；旧新插件混装不能用 direct SSH 绕过。
