---
name: jinny-android-execution-policy
description: "Use only when android-change-workflow explicitly resolved the Jinny execution capability. Return a rollout-bounded execution-policy-decision-v1 for analysis, diagnosis, implementation, review, verification, or a bounded operation; never dispatch or perform the work."
---

# Jinny Android Execution Policy

This Skill is a decision-only provider. It may recommend one declared worker profile,
return `core_direct`, or return `blocked`. It never creates an assignment,
spawns a task, grants a workspace or lock, runs a command, changes source, uploads, or
accepts a workflow Gate.

Use `scripts/jinny_execution_policy.py` with controller-supplied run/stage/context facts
and `--rollout-effect-ceiling`. The manifest declares these durable capabilities:

- Sol: architecture/high-risk analysis or diagnosis and final `review`; `read_only`;
  reasoning `max`.
- Terra: source exploration, log diagnosis, ordinary solution work, and
  `implementation`; `workspace_mutation` ceiling.
- Luna: explicit/repeated narrow extraction plus `verification` and
  `bounded_operation`; `controlled_operation` ceiling.

The controller supplies `--shape`, `--ambiguity`, `--risk-level`,
`--code-judgment`, and `--requested-effect`. A low-ambiguity, no-code-judgment,
narrow read routes to Luna; ordinary exploration/diagnosis routes to Terra;
architecture, high-risk, high-ambiguity, or final-review work routes to Sol.
Verification and bounded controlled operations route to Luna. Requested effect is
the explicit side-effect dimension; the provider never performs that effect.

The Phase 2 CLI default rollout ceiling is still `read_only`. A requested effect beyond
either the chosen profile or the active rollout ceiling returns `blocked`. This rollout
limit does not rewrite or permanently narrow provider capabilities. An environment
failure never changes the model choice.

The controller must validate the decision against its packaged
`execution-policy-decision-v1` schema, the exact provider manifest SHA-256, the declared
profile/task/effect ceiling, and the active rollout ceiling before creating any
assignment.

The controller, never Sol or another worker, remains the only owner of escalation,
result validation, Gate transitions, and final requirement acceptance.

This user-installed Skill is trusted code/instruction, not an OS sandbox. Core can bind
and verify its exact manifest, Skill, agent metadata, decision entrypoint, and output,
and can refuse to grant controller authority. It cannot prove that arbitrary custom
provider code has no process-level side effects.
