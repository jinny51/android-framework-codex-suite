# Member upload token migration

This release removes the predictable `member_alias` upload-token fallback. It does not rotate or revoke production credentials.

Migrate one member at a time:

1. An administrator creates a second token without rotating or revoking the old token.
2. Deliver the new value through the existing protected credential channel and inject it as `CODEX_REPORT_AKBS_ENDPOINT_SUBMISSION_API_TOKEN`; never store it in TOML, Git, command arguments, logs, test snapshots, JSON, Markdown, or chat.
3. Update that member to the token-only plugin release.
4. Run `doctor --strict --check-remote`; require `upload_token.status=configured`, `source=protected_environment`, and `migration_readiness=ready`.
5. Perform one real upload and confirm it is accepted.
6. The administrator confirms the new token has a non-empty `last_used_at`.
7. Only then revoke the old token.

Rollback to the still-active old token configuration when the upload is rejected, the new token has no `last_used_at`, or service health is not HTTP 200. Never revoke the old token before the new token is proven, and never claim production rotation is complete based only on installing this plugin release.
