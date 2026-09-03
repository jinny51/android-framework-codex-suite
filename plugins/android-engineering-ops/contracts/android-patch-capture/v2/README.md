# Android patch capture package v2

`capture-package.schema.json` is the installed, standalone structural contract for a
local `android_change_capture` manifest for one coherent Android change. The capture runtime validates this
schema plus cross-reference, authority, status, and full-file-inventory semantics
before an atomic local publish. It grants no AKBS adapter, upload, server ID, or
knowledge-materialization authority.
