from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
PLUGIN_ROOT = REPO_ROOT / "plugins" / "android-framework-ops"
for candidate in (
    PLUGIN_ROOT / "lib",
    PLUGIN_ROOT / "skills" / "android-knowledge-intake" / "scripts",
):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from akbs_intake.report_sessions import SessionWork, parse_sessions  # noqa: E402
from akbs_intake.patch.assets import PatchInfo  # noqa: E402
from akbs_intake.reports.session_summary import discover_patches  # noqa: E402
from akbs_intake.session_privacy import configure_report_session_consent  # noqa: E402


def write_session(codex_home: Path, date: dt.date, cwd: Path) -> None:
    session_id = "11111111-2222-3333-4444-555555555555"
    session_dir = codex_home / "sessions" / f"{date:%Y}" / f"{date:%m}" / f"{date:%d}"
    session_dir.mkdir(parents=True)
    rows = [
        {
            "timestamp": f"{date.isoformat()}T10:00:00+08:00",
            "type": "session_meta",
            "payload": {"id": session_id, "cwd": str(cwd)},
        },
        {
            "timestamp": f"{date.isoformat()}T10:01:00+08:00",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "完成 SystemUI 音量策略远端修改。"}],
            },
        },
    ]
    (session_dir / f"{session_id}.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def write_registry(registry_dir: Path, mount_root: Path) -> None:
    registry_dir.mkdir(parents=True)
    (registry_dir / "test.env").write_text(
        f"PROJECT_PATHS=( {mount_root} )\n"
        "SAMBA_PROJECT_SHARES=( //server/TVE1088U )\n"
        "REMOTE_SSH_HOSTS=( test61 )\n"
        "REMOTE_ROOTS=( /srv/android/TVE1088U )\n"
        "PLATFORMS=( unisoc )\n"
        "SDK_NAMES=( TVE1088U )\n"
        "PROJECT_IDS=( unisoc-TVE1088U )\n",
        encoding="utf-8",
    )


def test_registered_android_session_never_runs_local_git_or_retains_mount_cwd(tmp_path: Path) -> None:
    date = dt.date(2026, 8, 26)
    codex_home = tmp_path / "codex"
    mount_root = tmp_path / "human-artifact-bridge" / "TVE1088U"
    raw_cwd = mount_root / "frameworks" / "base"
    registry_dir = tmp_path / "registry"
    write_registry(registry_dir, mount_root)
    write_session(codex_home, date, raw_cwd)
    config = {
        "codex_home": str(codex_home),
        "timezone": "Asia/Shanghai",
        "source_access_registry_dir": str(registry_dir),
    }
    configure_report_session_consent(
        config,
        {date},
        granted=True,
        fields=["work_summary", "project_hint", "patch_discovery"],
    )

    sessions = parse_sessions(config, {date})

    assert len(sessions) == 1
    assert sessions[0].registered_android_mount is True
    assert sessions[0].project_id == "unisoc-TVE1088U"
    assert sessions[0].project == "TVE1088U"
    assert sessions[0].cwd == ""


def test_registered_android_patch_discovery_reads_capture_artifacts_only(tmp_path: Path) -> None:
    date = dt.date.today()
    mount_root = tmp_path / "mounted" / "TVE1088U"
    mount_root.mkdir(parents=True)
    (mount_root / "must-not-be-read.patch").write_text("mounted source", encoding="utf-8")
    artifacts = tmp_path / "artifacts"
    capture = artifacts / "android-framework-patch-capture" / "capture-1"
    patch_path = capture / "patches" / "unisoc16-systemui@volume-policy.patch"
    patch_path.parent.mkdir(parents=True)
    patch_path.write_text("remote capture patch", encoding="utf-8")
    (capture / "manifest.json").write_text(
        json.dumps(
            {
                "package_type": "framework_feature_patch",
                "created_at": f"{date.isoformat()}T10:00:00+08:00",
                "project": "TVE1088U",
                "patches": [{"path": "patches/unisoc16-systemui@volume-policy.patch"}],
            }
        ),
        encoding="utf-8",
    )
    session = SessionWork(
        cwd=str(mount_root),
        project="TVE1088U",
        project_id="unisoc-TVE1088U",
        registered_android_mount=True,
    )

    patches = discover_patches(
        {"include_patches": "true", "out_dir": str(artifacts / "android-knowledge-intake")},
        [session],
        date,
        date,
        patch_info_factory=lambda path, name, project: PatchInfo(path, name, project),
    )

    assert [(item.path, item.name, item.project) for item in patches] == [
        (patch_path.resolve(), patch_path.name, "TVE1088U")
    ]


def test_non_android_session_keeps_summary_but_retires_local_patch_discovery(tmp_path: Path) -> None:
    date = dt.date.today()
    ordinary = tmp_path / "ordinary-repository"
    ordinary.mkdir()
    patch_path = ordinary / "ordinary.patch"
    patch_path.write_text("ordinary patch", encoding="utf-8")
    session = SessionWork(cwd=str(ordinary), project="ordinary", registered_android_mount=False)

    patches = discover_patches(
        {"include_patches": "true", "out_dir": str(tmp_path / "artifacts" / "android-knowledge-intake")},
        [session],
        date,
        date,
        patch_info_factory=lambda path, name, project: PatchInfo(path, name, project),
    )

    assert patches == []
    assert session.cwd == str(ordinary)
    assert session.project == "ordinary"
