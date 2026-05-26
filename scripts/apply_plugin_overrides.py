#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CODEX_DOCUMENTS = "/mnt/c/Users/jinny/Documents/Codex"


def replace(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    updated = text.replace(old, new)
    if updated != text:
        path.write_text(updated, encoding="utf-8")


def insert_after(path: Path, anchor: str, block: str) -> None:
    text = path.read_text(encoding="utf-8")
    if block.strip() in text:
        return
    if anchor not in text:
        raise SystemExit(f"Anchor not found in {path}: {anchor!r}")
    updated = text.replace(anchor, anchor + "\n\n" + block, 1)
    path.write_text(updated, encoding="utf-8")


def patch_android_framework_workflow() -> None:
    path = REPO_ROOT / "plugins/android-framework-ops/skills/android-framework-change-workflow/SKILL.md"
    anchor = (
        "Use this skill as the framework engineer's operating protocol. It owns requirement "
        "specification, diagnosis, code-change discipline, risk judgment, final acceptance "
        "verification, and final reporting."
    )
    block = """## Composable Use Contract

When user-provided skills, project-local rules, or review workflows exist, preserve them. Use this skill only for Android Framework-specific source access, diagnosis, build/deploy coordination, verification, patch capture, and knowledge reuse.

If the user explicitly asks for a personal coding-style skill, project `AGENTS.md`, local engineering rule, or review skill, treat that instruction as part of the active requirement. Do not replace it with this workflow. Combine the user's rule with this workflow's Android Framework evidence and verification discipline."""
    insert_after(path, anchor, block)


def patch_knowledge_intake_code() -> None:
    for rel in [
        "plugins/android-framework-ops/skills/android-knowledge-intake/scripts/android_knowledge_intake.py",
        "plugins/android-framework-ops/skills/android-knowledge-intake/scripts/archive_automation_runs.py",
    ]:
        path = REPO_ROOT / rel
        replace(
            path,
            '''def default_codex_home() -> str:
    if os.environ.get("CODEX_HOME"):
        return os.environ["CODEX_HOME"]
    if PLUGIN_ROOT.parent.name in {"skills", "team-skills"}:
        return str(PLUGIN_ROOT.parent.parent)
    return str(Path.home() / ".codex")
''',
            '''def default_codex_home() -> str:
    if os.environ.get("CODEX_HOME"):
        return os.environ["CODEX_HOME"]
    return str(Path.home() / ".codex")
''',
        )

    intake = REPO_ROOT / "plugins/android-framework-ops/skills/android-knowledge-intake/scripts/android_knowledge_intake.py"
    replace(intake, '"source": "codex-team-skills"', '"source": "android-framework-ops"')
    replace(intake, '"repo_worktree": "$CODEX_HOME/report/knowledge"', f'"repo_worktree": "{CODEX_DOCUMENTS}/worktrees/knowledge"')
    replace(intake, '"out_dir": "$CODEX_HOME/android-knowledge-intake/out"', f'"out_dir": "{CODEX_DOCUMENTS}/artifacts/android-knowledge-intake"')
    replace(intake, "~/Documents/Codex/worktrees/knowledge", f"{CODEX_DOCUMENTS}/worktrees/knowledge")
    replace(intake, "~/Documents/Codex/artifacts/android-knowledge-intake", f"{CODEX_DOCUMENTS}/artifacts/android-knowledge-intake")


def patch_knowledge_paths() -> None:
    intake_files = [
        REPO_ROOT / "plugins/android-framework-ops/skills/android-knowledge-intake/SKILL.md",
        REPO_ROOT / "plugins/android-framework-ops/skills/android-knowledge-intake/README.md",
        REPO_ROOT / "plugins/android-framework-ops/skills/android-knowledge-intake/config.example.toml",
    ]
    for path in intake_files:
        if not path.exists():
            continue
        replace(path, "$CODEX_HOME/android-knowledge-intake/out", f"{CODEX_DOCUMENTS}/artifacts/android-knowledge-intake")
        replace(path, "$CODEX_HOME/report/knowledge-member_alias", f"{CODEX_DOCUMENTS}/worktrees/knowledge-member_alias")
        replace(path, "$CODEX_HOME/report/knowledge-jinny", f"{CODEX_DOCUMENTS}/worktrees/knowledge-jinny")
        replace(path, "$CODEX_HOME/report/knowledge", f"{CODEX_DOCUMENTS}/worktrees/knowledge")
        replace(path, "~/Documents/Codex/artifacts/android-knowledge-intake", f"{CODEX_DOCUMENTS}/artifacts/android-knowledge-intake")
        replace(path, "~/Documents/Codex/worktrees/knowledge-member_alias", f"{CODEX_DOCUMENTS}/worktrees/knowledge-member_alias")
        replace(path, "~/Documents/Codex/worktrees/knowledge-jinny", f"{CODEX_DOCUMENTS}/worktrees/knowledge-jinny")
        replace(path, "~/Documents/Codex/worktrees/knowledge", f"{CODEX_DOCUMENTS}/worktrees/knowledge")

    search_skill = REPO_ROOT / "plugins/android-framework-ops/skills/android-knowledge-search/SKILL.md"
    replace(
        search_skill,
        "4. common Codex report clones under `$CODEX_HOME/report/`\n5. common mapped server locations such as `/mnt/z/knowledge/worktree`",
        f"4. common Codex worktrees under `{CODEX_DOCUMENTS}/worktrees/`\n5. common mapped server locations such as `/mnt/z/knowledge/worktree`",
    )
    replace(search_skill, "`~/Documents/Codex/worktrees/`", f"`{CODEX_DOCUMENTS}/worktrees/`")

    search_readme = REPO_ROOT / "plugins/android-framework-ops/skills/android-knowledge-search/README.md"
    if search_readme.exists():
        replace(search_readme, "$CODEX_HOME/report/", f"{CODEX_DOCUMENTS}/worktrees/")
        replace(search_readme, "~/Documents/Codex/worktrees/", f"{CODEX_DOCUMENTS}/worktrees/")

    search_script = REPO_ROOT / "plugins/android-framework-ops/skills/android-knowledge-search/scripts/android_knowledge_search.py"
    replace(
        search_script,
        '''    home = codex_home()
    candidates.extend(
        [
            home / "report" / "knowledge-jinny",
            home / "report" / "knowledge",
            home / "report" / "knowledge-test",
            home / "knowledge",
            Path("/mnt/z/knowledge/worktree"),
            Path("/mnt/z/knowledge"),
            Path("/home/test35/work/knowledge/worktree"),
        ]
    )
''',
        '''    home = codex_home()
    documents = Path("/mnt/c/Users/jinny/Documents/Codex")
    candidates.extend(
        [
            documents / "worktrees" / "knowledge-jinny",
            documents / "worktrees" / "knowledge",
            documents / "worktrees" / "knowledge-test",
            home / "knowledge",
            Path("/mnt/z/knowledge/worktree"),
            Path("/mnt/z/knowledge"),
            Path("/home/test35/work/knowledge/worktree"),
        ]
    )
''',
    )


def patch_command_examples() -> None:
    replacements = {
        '${CODEX_HOME:-$HOME/.codex}/skills/android-knowledge-search/scripts/android_knowledge_search.py': "scripts/android_knowledge_search.py",
        "$CODEX_HOME/skills/android-knowledge-search/scripts/android_knowledge_search.py": "scripts/android_knowledge_search.py",
        '${CODEX_HOME:-$HOME/.codex}/skills/android-knowledge-intake/scripts/android_knowledge_intake.py': "scripts/android_knowledge_intake.py",
        "$CODEX_HOME/skills/android-knowledge-intake/scripts/android_knowledge_intake.py": "scripts/android_knowledge_intake.py",
        '${CODEX_HOME:-$HOME/.codex}/skills/android-framework-patch-capture/scripts/capture_framework_patch.py': "scripts/capture_framework_patch.py",
        "$CODEX_HOME/skills/android-framework-patch-capture/scripts/capture_framework_patch.py": "scripts/capture_framework_patch.py",
        '${CODEX_HOME:-$HOME/.codex}/skills/android-wsl-source-access': "<path-to-this-skill>",
        '${CODEX_HOME:-$HOME/.codex}/skills/android-wsl-remote-build-deploy': "<path-to-this-skill>",
        '${CODEX_HOME:-$HOME/.codex}/skills/android-remote-channel': "<path-to-this-skill>",
    }
    for path in (REPO_ROOT / "plugins").rglob("*.md"):
        for old, new in replacements.items():
            replace(path, old, new)

    patch_capture_skill = REPO_ROOT / "plugins/android-framework-ops/skills/android-framework-patch-capture/SKILL.md"
    replace(
        patch_capture_skill,
        "scripts/android_knowledge_intake.py",
        "../android-knowledge-intake/scripts/android_knowledge_intake.py",
    )


def main() -> None:
    patch_android_framework_workflow()
    patch_knowledge_intake_code()
    patch_knowledge_paths()
    patch_command_examples()
    print("Plugin overrides applied")


if __name__ == "__main__":
    main()
