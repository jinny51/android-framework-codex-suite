# Android Domain Routing

`change_domain` is the primary operational label for ownership, build, deployment, risk,
and verification. It is not a directory taxonomy. A feature may list multiple touched
components while keeping one primary domain.

Choose from explicit product intent and authoritative source/build ownership:

- Use `system_app` for privileged platform applications; use `framework` when the
  changed authority is the platform API or system service itself.
- Use `hal` for a versioned hardware interface/service contract; use `native` for a
  native service or library without that HAL contract.
- Use `vendor` for BSP/proprietary/product integration crossing vendor ownership; do
  not use it merely because a path contains `vendor`.
- Use `kernel` for core/subsystem changes; use `driver` when probe, bind, firmware,
  device I/O, or hardware lifecycle is the primary behavior.
- Use `device` for board/product/DTS/DTBO/overlay/boot integration when no kernel or
  driver implementation is the principal change.
- Use `build` when the build or release graph itself is the product behavior; a normal
  module build file edited alongside implementation stays a component of that domain.

If one requirement intentionally spans independently owned deliverables with separate
acceptance and rollback, split captures by coherent feature/package boundary. Do not
use a broad domain to hide unrelated changes.

## Source Authority

Choose authority per affected repository, independently of `change_domain`:

- `registered_remote_tree`: an Android tree registered or mounted by
  `android-source-access`. All Codex source/Git/build operations run through
  `android-remote-channel`; the mount is not a local workspace.
- `local_project`: a real local Git project explicitly opened as the Codex workspace.
  Use its local project rules and tools. A Samba/SMB/CIFS mount can never qualify.

A feature may combine authorities, but its plan and evidence must identify each
repository separately.

## Build Route

Choose by the project's real build owner, not by domain name alone:

| Route | Use when | Executor |
| --- | --- | --- |
| `remote_profile` | Registered remote AOSP Soong/Make module or configured vendor full build | `android-remote-build-deploy` |
| `remote_project_command` | Registered remote Gradle, Kbuild/kernel, external driver, Bazel, or another project-owned build | documented command through `android-remote-channel` |
| `local_project_command` | Real local project with its own wrapper or build entry | local project tools |

The route must return the exact command/profile, exit status, artifact identity,
verification, delivery method, and rollback. A successful build alone never proves the
requirement.
