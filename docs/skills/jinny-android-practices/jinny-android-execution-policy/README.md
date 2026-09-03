# jinny-android-execution-policy

> GitHub 说明页。Runtime Skill 位于 [../../../../plugins/jinny-android-practices/skills/jinny-android-execution-policy](../../../../plugins/jinny-android-practices/skills/jinny-android-execution-policy)。

返回 `execution-policy-decision-v1`，但不派发或执行工作。合同声明 Sol 分析/诊断/review（read-only/max）、Terra implementation（workspace mutation ceiling）、Luna verification/bounded operation（controlled operation ceiling）；controller rollout ceiling 可进一步收紧，越界 fail closed。入口在执行共享 helper 前校验其固定 SHA-256；最终验收始终属于 `android-change-workflow`。
