# Android Component Routing

The canonical selector is `component.layer`, never the legacy ten-item domain list.
Choose exactly one layer from:

```text
application | platform | native | hal | kernel | device | build
```

Always record the independent facets `component.type`, `component.partition`, and
`component.ownership`. A type or ownership name does not become a layer: Framework,
SystemApp, App, and driver are types; vendor is an ownership/partition facet. For
example:

```text
SystemUI       application / system_app / system_ext / aosp
Framework svc  platform    / framework  / system     / aosp
Vendor HAL     hal         / aidl_hal   / vendor     / vendor
Kernel driver  kernel      / driver     / boot       / vendor
```

The deprecated `--change-domain` input exists only for compatibility. `framework`,
`system_app`, `app`, `hal`, `native`, `kernel`, `driver`, `device`, and `build` provide
only frozen layer/type hints in `contracts/change-domain/v1/domain-profiles.json`.
Missing partition/ownership remain `unknown`; `vendor` has no safe layer/type hint and
therefore requires all four canonical fields. Never infer native/hal/device from a
vendor path.

Use layer-specific evidence, then refine it with the type and facets. A normal build
file touched beside an implementation does not move the change to the build layer;
choose build only when the build/release graph is itself the behavior. If one request
contains independently owned features with separate acceptance or rollback, split the
captures rather than hiding them under a broad label.

## Source Authority

Choose authority per repository, independently of the component:

- `registered_remote_tree`: registered or mounted by `android-source-access`. All
  Codex source/Git/build operations use `android-remote-channel`; the mount is not a
  local workspace.
- `local_project`: a real local Git project explicitly opened as the Codex workspace.
  A Samba/SMB/CIFS mount never qualifies.

## Build Route

Choose from real project ownership rather than a layer label:

| Route | Use when | Executor |
| --- | --- | --- |
| `remote_profile` | Registered remote AOSP Soong/Make module or configured vendor full build | `android-remote-build-deploy` |
| `remote_project_command` | Registered remote Gradle, Kbuild, Bazel, or project-owned build | documented command through `android-remote-channel` |
| `local_project_command` | Real local project with its own wrapper/build entry | local project tools |

Record exact command/profile, exit status, artifact identity, verification, delivery,
and rollback. A successful build alone never proves the requirement.
