from __future__ import annotations

import io
import json
import sys
import tarfile
import urllib.request
from pathlib import Path
from typing import Any

try:
    from .config import (
        submission_api_base_url,
        submission_api_token,
        submission_session_cookie,
    )
except ImportError:  # pragma: no cover - direct script import fallback
    scripts_root = Path(__file__).resolve().parents[1]
    if str(scripts_root) not in sys.path:
        sys.path.insert(0, str(scripts_root))
    from akbs_intake.config import (
        submission_api_base_url,
        submission_api_token,
        submission_session_cookie,
    )


def read_json_file(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"读取 JSON 失败: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise SystemExit(f"JSON 必须是对象: {path}")
    return payload


def package_tar_gz_bytes(package_dir: Path) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for path in sorted(package_dir.rglob("*")):
            archive.add(path, arcname=path.relative_to(package_dir).as_posix(), recursive=False)
    return buffer.getvalue()


def server_submit_package(package_dir: Path, config: dict[str, str], method: str = "http") -> dict[str, Any]:
    member = config.get("member_alias", "").strip()
    if not member:
        raise SystemExit("member_alias 不能为空")
    if method != "http":
        raise SystemExit("AKBS 成员上传只支持 HTTP API；SSH/local 上传字段已废弃，请先更新插件并执行配置迁移。")
    payload = package_tar_gz_bytes(package_dir)
    return http_submit_package(package_dir, config, member, payload)


def http_submit_package(package_dir: Path, config: dict[str, str], member: str, payload: bytes) -> dict[str, Any]:
    base_url = submission_api_base_url(config).rstrip("/")
    if not base_url:
        raise SystemExit("submission_api_base_url 不能为空")
    manifest = read_json_file(package_dir / "manifest.json")
    upload_type = upload_type_for_manifest(manifest)
    url = f"{base_url}/member/me/uploads/{upload_type}"
    request = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/gzip",
            "X-AKBS-User": member,
        },
    )
    cookie = submission_session_cookie(config)
    if cookie:
        request.add_header("Cookie", cookie)
    token = submission_api_token(config) or member
    request.add_header("X-AKBS-Token", token)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            stdout = response.read().decode("utf-8", errors="replace")
    except Exception as error:
        raise SystemExit(f"HTTP 上传入口提交失败: {error}") from error
    try:
        result = json.loads(stdout or "{}")
    except json.JSONDecodeError:
        result = {"message": stdout.strip()}
    result.setdefault("submitted", True)
    result.setdefault("method", "http")
    result.setdefault("package", str(package_dir))
    result.setdefault("upload_url", url)
    return result


def upload_type_for_manifest(manifest: dict[str, Any]) -> str:
    package_kind = str(manifest.get("package_kind") or "").strip()
    if package_kind == "daily_trace":
        return "daily"
    if package_kind == "weekly_trace":
        return "weekly"
    if package_kind == "framework_change":
        if str(manifest.get("supplement_for_package_key") or "").strip():
            return "supplement"
        return "patch"
    raise SystemExit(f"无法根据 package_kind 判断上传类型: {package_kind}")
