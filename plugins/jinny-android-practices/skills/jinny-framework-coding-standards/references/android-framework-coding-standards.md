# Optional Jinny Naming Advisory

This file contains only optional Jinny preferences. It is not a second policy contract.

Always apply `android-change-policy` first. When the user explicitly requests the
`legacy_jinny_style` advisory:

- helper methods may use a suffix derived from the current profile's `member_alias`;
- two or more feature helpers may be grouped in a same-package `<Alias>Utils` class;
- review or project conventions must be concrete and non-conflicting.

Never hardcode an example person's alias. Mandatory identity, paired markers,
FrameworkLog, resources, evidence, and historical-author behavior come only from the
canonical policy.
