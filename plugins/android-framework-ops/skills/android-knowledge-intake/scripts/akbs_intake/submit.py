from __future__ import annotations

import io
import json
import sys
import tarfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

try:
    from .config import (
        submission_api_base_url,
    )
    from .incoming_contract import server_error_reason_code, validate_success_response
    from .reports.common import ensure_report_submit_allowed, record_submitted_package
except ImportError:  # pragma: no cover - direct script import fallback
    scripts_root = Path(__file__).resolve().parents[1]
    if str(scripts_root) not in sys.path:
        sys.path.insert(0, str(scripts_root))
    from akbs_intake.config import (
        submission_api_base_url,
    )
    from akbs_intake.incoming_contract import server_error_reason_code, validate_success_response
    from akbs_intake.reports.common import ensure_report_submit_allowed, record_submitted_package


PackageValidator = Callable[[Path], dict[str, Any]]
JsonWriter = Callable[[Path, dict[str, Any]], None]
PatchGate = Callable[[dict[str, Any]], list[str]]


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
    if not member or member == "unknown":
        raise SystemExit("member_alias 不能为空或不能使用 unknown")
    if method != "http":
        raise SystemExit("AKBS 成员上传只支持 HTTP API；SSH/local 上传字段已废弃，请先更新插件并执行配置迁移。")
    payload = package_tar_gz_bytes(package_dir)
    return http_submit_package(package_dir, config, member, payload)


def submit_package(
    package_dir: Path,
    config: dict[str, str],
    *,
    validate_package_fn: PackageValidator,
    write_json_fn: JsonWriter,
    patch_upload_gate_errors_fn: PatchGate,
) -> dict[str, Any]:
    check = validate_package_fn(package_dir)
    write_json_fn(package_dir / "local-check.json", check)
    if check["status"] != "PASS":
        raise SystemExit("本地工作包校验失败，已停止提交。请查看 local-check.json。")
    manifest = read_json_file(package_dir / "manifest.json")
    ensure_report_submit_allowed(package_dir, config, manifest)
    gate_errors = patch_upload_gate_errors_fn(manifest)
    if gate_errors:
        raise SystemExit("\n".join(gate_errors))

    result = server_submit_package(package_dir, config)
    if manifest.get("package_kind") in {"daily_trace", "weekly_trace"}:
        record_submitted_package(package_dir, config, manifest)
    return result


def http_submit_package(
    package_dir: Path,
    config: dict[str, str],
    member: str,
    payload: bytes,
) -> dict[str, Any]:
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
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            stdout = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        try:
            error_payload = json.loads(body or "{}")
        except json.JSONDecodeError:
            error_payload = {}
        detail = error_payload.get("detail") if isinstance(error_payload, dict) else ""
        try:
            reason_code = server_error_reason_code(detail)
        except RuntimeError as contract_error:
            raise SystemExit(f"HTTP 上传入口合同漂移: {contract_error}") from error
        suffix = f" reason_code={reason_code}" if reason_code else ""
        raise SystemExit(f"HTTP 上传入口提交失败（认证信息已脱敏）: HTTP {error.code}{suffix}") from error
    except Exception as error:
        raise SystemExit(f"HTTP 上传入口提交失败（认证信息已脱敏）: {type(error).__name__}") from error
    try:
        result = json.loads(stdout or "{}")
    except json.JSONDecodeError:
        result = {"message": stdout.strip()}
    if not isinstance(result, dict):
        raise SystemExit("HTTP 上传入口合同漂移: server success response must be a JSON object")
    try:
        validate_success_response(result)
    except RuntimeError as error:
        raise SystemExit(f"HTTP 上传入口合同漂移: {error}") from error
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
