---
name: android-knowledge-search
description: "Deprecated compatibility wrapper for akbs-knowledge-search. Use only when an existing invocation still names android-knowledge-search."
---

# Android Knowledge Search Compatibility

Forward the unchanged arguments and exit status from
`scripts/android_knowledge_search.py` to the canonical `akbs-knowledge-search` CLI.
Tell the user that `$akbs-knowledge-search` is the replacement. Keep all search,
server-fallback, merge-confirmation, and usage-record logic in the canonical owner.
