#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import hashlib
import io
import json
import os
import re
import shlex
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import textwrap
from pathlib import Path
from typing import Any, Callable


REPO_ROOT = Path(__file__).resolve().parents[1]
CONTRACT_ROOT = REPO_ROOT / "contracts" / "incoming" / "v1"
INTAKE_SCRIPT = (
    REPO_ROOT
    / "plugins"
    / "android-framework-ops"
    / "skills"
    / "android-knowledge-intake"
    / "scripts"
    / "android_knowledge_intake.py"
)
CAPTURE_SCRIPT = (
    REPO_ROOT
    / "plugins"
    / "android-framework-ops"
    / "skills"
    / "android-framework-patch-capture"
    / "scripts"
    / "capture_framework_patch.py"
)
RESIDUE_TABLES = (
    "packages",
    "intake_queue",
    "daily_reports",
    "weekly_reports",
    "patch_packages",
    "supplement_packages",
    "package_assets",
    "package_material_identity",
)


def run_json(command: list[str], cwd: Path, env: dict[str, str]) -> dict[str, Any]:
    result = subprocess.run(
        command,
        cwd=str(cwd),
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        errors="replace",
        check=False,
    )
    if result.returncode:
        raise AssertionError(result.stderr or result.stdout)
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise AssertionError(result.stdout + result.stderr) from exc
    if not isinstance(payload, dict):
        raise AssertionError(f"command did not return a JSON object: {command}")
    return payload


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reject_codes(server_validator: Path) -> set[str]:
    tree = ast.parse(server_validator.read_text(encoding="utf-8"))
    return {
        node.args[0].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "reject"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
    }


def validate_fixture_schema(schema: dict[str, Any], manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for field in schema.get("required", []):
        if field not in manifest:
            errors.append(f"missing required field: {field}")
    properties = schema.get("properties", {})
    for field, rules in properties.items():
        if field not in manifest or not isinstance(rules, dict):
            continue
        value = manifest[field]
        if "const" in rules and value != rules["const"]:
            errors.append(f"{field} does not match const")
        if "enum" in rules and value not in rules["enum"]:
            errors.append(f"{field} is outside enum")
        if rules.get("type") == "string" and not isinstance(value, str):
            errors.append(f"{field} is not a string")
        if rules.get("type") == "object" and not isinstance(value, dict):
            errors.append(f"{field} is not an object")
        if isinstance(value, str) and int(rules.get("minLength", 0)) > len(value):
            errors.append(f"{field} is too short")
        if isinstance(value, str) and rules.get("pattern") and re.fullmatch(str(rules["pattern"]), value) is None:
            errors.append(f"{field} does not match pattern")
    if manifest.get("package_kind") == "framework_change":
        then = schema.get("allOf", [{}])[0].get("then", {})
        for field in then.get("required", []):
            if field not in manifest:
                errors.append(f"framework_change missing required field: {field}")
        status_const = then.get("properties", {}).get("package_status", {}).get("const")
        if status_const and manifest.get("package_status") != status_const:
            errors.append("framework_change package_status does not match const")
    return errors


def verify_public_contract(system_root: Path) -> dict[str, Any]:
    pin = json.loads((CONTRACT_ROOT / "contract-pin.json").read_text(encoding="utf-8"))
    if pin.get("schema_version") != "1":
        raise AssertionError("plugin compatibility pin must remain on incoming schema version 1")
    system_contract = system_root / "contracts" / "incoming" / "v1"
    for relative, expected_digest in pin["artifacts"].items():
        plugin_path = CONTRACT_ROOT / relative
        system_path = system_contract / relative
        if not plugin_path.is_file() or not system_path.is_file():
            raise AssertionError(f"missing public incoming artifact: {relative}")
        plugin_digest = sha256(plugin_path)
        system_digest = sha256(system_path)
        if plugin_digest != expected_digest or system_digest != expected_digest:
            raise AssertionError(
                f"incoming artifact drift: {relative}: pin={expected_digest} plugin={plugin_digest} server={system_digest}"
            )

    schema = json.loads((CONTRACT_ROOT / "knowledge-incoming-package.schema.json").read_text(encoding="utf-8"))
    fixture_names = ("daily", "weekly", "patch", "supplement")
    for name in fixture_names:
        manifest = json.loads((CONTRACT_ROOT / "fixtures" / f"{name}.manifest.json").read_text(encoding="utf-8"))
        errors = validate_fixture_schema(schema, manifest)
        if errors:
            raise AssertionError(f"{name} golden manifest failed schema: {errors[0]}")

    server_validator = system_root / pin["server_validator"]
    expected_codes = {code for values in pin["reason_code_families"].values() for code in values}
    actual_codes = reject_codes(server_validator)
    if actual_codes != expected_codes:
        raise AssertionError(
            "incoming reason-code drift: "
            + json.dumps(
                {"missing": sorted(expected_codes - actual_codes), "added": sorted(actual_codes - expected_codes)},
                ensure_ascii=False,
            )
        )
    return {"artifacts": len(pin["artifacts"]), "fixtures": len(fixture_names), "reason_codes": len(actual_codes)}


def write_config(root: Path) -> dict[str, str]:
    codex_home = root / "codex-home"
    config_dir = codex_home / "report"
    config_dir.mkdir(parents=True)
    (config_dir / "config.toml").write_text(
        textwrap.dedent(
            f"""
            default_profile = "wick"
            incoming_schema_version = "1"

            [paths]
            out_dir = "{(root / 'artifacts' / 'android-knowledge-intake').as_posix()}"

            [profiles.wick]
            member_alias = "wick"
            member_name = "刘杰钊"
            role = "member"
            allowed_modes = ["daily", "weekly", "patch"]
            knowledge_repo_worktree = "{(root / 'knowledge').as_posix()}"
            git_user_name = "刘杰钊"
            git_user_email = "wick@example.invalid"
            synthetic_data = true
            synthetic_item_count = "2"
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["CODEX_HOME"] = str(codex_home)
    env["CODEX_REPORT_SKIP_PLUGIN_UPDATE_CHECK"] = "1"
    return env


def init_framework_source(root: Path) -> Path:
    source_root = root / "android-source"
    source = source_root / "frameworks/base/packages/SystemUI/src/com/android/systemui/volume/VolumeDialogImpl.java"
    source.parent.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(source_root)], check=True)
    subprocess.run(["git", "config", "user.email", "contract@example.invalid"], cwd=source_root, check=True)
    subprocess.run(["git", "config", "user.name", "Contract Gate"], cwd=source_root, check=True)
    source.write_text("class VolumeDialogImpl {}\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=source_root, check=True)
    subprocess.run(["git", "commit", "-m", "contract baseline"], cwd=source_root, check=True, stdout=subprocess.DEVNULL)
    source.write_text(
        "class VolumeDialogImpl {\n"
        "  //wick 20260711@ contract gate change\n"
        "  static final String KEY = \"persist.sys.contract_gate\";\n"
        "}\n",
        encoding="utf-8",
    )
    return source_root


def generate_real_packages(root: Path, env: dict[str, str]) -> dict[str, Path]:
    common = [sys.executable, str(INTAKE_SCRIPT), "--profile", "wick"]
    daily = run_json(common + ["daily", "--date", "2026-07-11", "--run-id", "20260711-090000-daily", "--prepare"], REPO_ROOT, env)
    weekly = run_json(common + ["weekly", "--date", "2026-07-11", "--run-id", "20260711-100000-weekly", "--prepare"], REPO_ROOT, env)
    source_root = init_framework_source(root)
    capture = run_json(
        [
            sys.executable,
            str(CAPTURE_SCRIPT),
            "--source-root",
            str(source_root),
            "--out-dir",
            "capture-out",
            "--run-id",
            "20260711-110000-patch",
            "--platform",
            "mtk15",
            "--feature",
            "incoming-contract-gate",
            "--summary",
            "incoming v1 跨仓合同门禁",
            "--project",
            "TVE8402M",
            "--status",
            "validated",
            "--verification",
            "SystemUI 编译通过",
            "--device",
            "TVE8402M",
            "--device-verification",
            "incoming 合同验证通过",
            "--search-query",
            "incoming v1 contract",
            "--search-result",
            "未发现可直接复用补丁",
        ],
        source_root,
        env,
    )
    patch = run_json(
        common
        + [
            "patch",
            "--date",
            "2026-07-11",
            "--run-id",
            "20260711-120000-patch",
            "--patch-package",
            capture["package"],
            "--summary",
            "incoming v1 跨仓合同门禁",
            "--status",
            "validated",
            "--prepare",
        ],
        REPO_ROOT,
        env,
    )
    supplement = run_json(
        common
        + [
            "patch",
            "--date",
            "2026-07-11",
            "--run-id",
            "20260711-130000-field-supplement",
            "--project",
            "TVE8402M",
            "--platform",
            "mtk",
            "--android-version",
            "15",
            "--summary",
            "incoming v1 字段补证",
            "--status",
            "validated",
            "--supplement-for-package-key",
            "20260711/wick/20260711-120000-patch",
            "--supplement-mode",
            "field_correction",
            "--corrected-field",
            "project=TVE8402M",
            "--correction-reason",
            "跨仓合同门禁补证",
            "--prepare",
        ],
        REPO_ROOT,
        env,
    )
    return {name: Path(payload["package"]) for name, payload in (("daily", daily), ("weekly", weekly), ("patch", patch), ("supplement", supplement))}


def tar_bytes(package_dir: Path) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for path in sorted(package_dir.rglob("*")):
            archive.add(path, arcname=path.relative_to(package_dir).as_posix(), recursive=False)
    return buffer.getvalue()


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise AssertionError(f"expected JSON object: {path}")
    return payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def mutate_package(root: Path, source: Path, name: str, mutation: Callable[[Path, dict[str, Any]], None]) -> Path:
    target = root / "mutations" / name
    shutil.copytree(source, target)
    manifest_path = target / "manifest.json"
    manifest = load_json(manifest_path)
    mutation(target, manifest)
    write_json(manifest_path, manifest)
    return target


def runtime_snapshot(db_path: Path, data_root: Path) -> tuple[dict[str, int], tuple[str, ...]]:
    with sqlite3.connect(db_path) as conn:
        counts = {table: int(conn.execute(f"select count(*) from {table}").fetchone()[0]) for table in RESIDUE_TABLES}
    uploads = data_root / "uploads"
    paths = tuple(sorted(path.relative_to(uploads).as_posix() for path in uploads.rglob("*") if path.is_file())) if uploads.exists() else ()
    return counts, paths


def expect_reject(client: Any, db_path: Path, data_root: Path, route: str, package: Path, code: str) -> None:
    before = runtime_snapshot(db_path, data_root)
    response = client.post(f"/akbs/api/member/me/uploads/{route}", content=tar_bytes(package))
    if response.status_code not in {400, 403, 409} or code not in str(response.json().get("detail", "")):
        raise AssertionError(f"{package.name}: expected {code} rejection, got {response.status_code}: {response.text}")
    after = runtime_snapshot(db_path, data_root)
    if after != before:
        raise AssertionError(f"rejected mutation left runtime residue: {code}")


def set_nested_json(package: Path, relative: str, updater: Callable[[dict[str, Any]], None]) -> None:
    path = package / relative
    payload = load_json(path)
    updater(payload)
    write_json(path, payload)


def exercise_server(system_root: Path, root: Path, packages: dict[str, Path]) -> dict[str, int]:
    sys.path.insert(0, str(system_root))
    from fastapi.testclient import TestClient
    from akbs_active.app import create_app
    from akbs_active.db import apply_migrations
    from tests.auth_helpers import login_member

    db_path = root / "runtime" / "akbs.sqlite3"
    data_root = root / "runtime" / "data"
    db_path.parent.mkdir(parents=True)
    apply_migrations(db_path)
    client = TestClient(create_app(db_path, data_root=data_root))
    login_member(client, "wick")

    accepted = 0
    rejected = 0
    for route in ("daily", "weekly"):
        response = client.post(f"/akbs/api/member/me/uploads/{route}", content=tar_bytes(packages[route]))
        if response.status_code != 200:
            raise AssertionError(f"real plugin {route} package rejected: {response.text}")
        accepted += 1

    patch = packages["patch"]
    mutation_cases: list[tuple[str, str, Callable[[Path, dict[str, Any]], None]]] = [
        ("required-field", "missing_required_field", lambda _p, m: m.pop("summary")),
        ("referenced-path", "missing_referenced_file", lambda p, m: (p / m["files"]["patches"][0]).unlink()),
        ("case-binding", "case_binding_mismatch", lambda p, m: set_nested_json(p, m["files"]["case"], lambda v: v.update(case_id="case-drift"))),
        ("variant-binding", "variant_binding_mismatch", lambda p, m: set_nested_json(p, m["files"]["variant"], lambda v: v.update(variant_id="variant-drift"))),
        ("project", "variant_trace_mismatch", lambda _p, m: m.update(project="TVE9999U")),
        ("platform", "variant_trace_mismatch", lambda _p, m: m.update(platform="rk")),
        ("android", "variant_trace_mismatch", lambda _p, m: m.update(android_version="14")),
        ("patch-asset", "invalid_patch_asset", lambda p, m: (p / m["files"]["patches"][0]).write_text("not a git diff\n", encoding="utf-8")),
        (
            "verification",
            "verification_not_pass",
            lambda p, m: set_nested_json(
                p,
                next(path for path in m["files"]["evidence"] if path.endswith("verification_result.json")),
                lambda v: v.setdefault("payload", {}).update(result="FAIL"),
            ),
        ),
    ]
    for name, code, mutation in mutation_cases:
        candidate = mutate_package(root, patch, name, mutation)
        expect_reject(client, db_path, data_root, "patch", candidate, code)
        rejected += 1
    for status in ("candidate", "draft", "failed", "blocked", "missing", "unknown"):
        def status_mutation(_p: Path, manifest: dict[str, Any], value: str = status) -> None:
            if value == "missing":
                manifest.pop("package_status", None)
            else:
                manifest["package_status"] = value

        code = "missing_required_field" if status == "missing" else "package_status_not_validated"
        candidate = mutate_package(root, patch, f"status-{status}", status_mutation)
        expect_reject(client, db_path, data_root, "patch", candidate, code)
        rejected += 1

    patch_response = client.post("/akbs/api/member/me/uploads/patch", content=tar_bytes(patch))
    if patch_response.status_code != 200:
        raise AssertionError(f"real plugin patch package rejected: {patch_response.text}")
    accepted += 1

    supplement = packages["supplement"]
    missing_target = mutate_package(
        root,
        supplement,
        "supplement-target-missing",
        lambda p, m: update_supplement_target(p, m, "20260711/wick/20260711-125959-missing"),
    )
    expect_reject(client, db_path, data_root, "supplement", missing_target, "supplement_target_not_found")
    rejected += 1

    login_member(client, "jared")
    jared_patch = mutate_package(root, patch, "jared-original", lambda p, m: retarget_member(p, m, "jared", "20260711-120001-patch"))
    jared_response = client.post("/akbs/api/member/me/uploads/patch", content=tar_bytes(jared_patch))
    if jared_response.status_code != 200:
        raise AssertionError(f"cross-member setup patch rejected: {jared_response.text}")
    accepted += 1
    login_member(client, "wick")
    cross_member = mutate_package(
        root,
        supplement,
        "supplement-cross-member",
        lambda p, m: update_supplement_target(p, m, "20260711/jared/20260711-120001-patch"),
    )
    expect_reject(client, db_path, data_root, "supplement", cross_member, "supplement_target_member_mismatch")
    rejected += 1

    supplement_response = client.post("/akbs/api/member/me/uploads/supplement", content=tar_bytes(supplement))
    if supplement_response.status_code != 200:
        raise AssertionError(f"same-member original supplement rejected: {supplement_response.text}")
    accepted += 1
    chained = mutate_package(
        root,
        supplement,
        "supplement-target-is-supplement",
        lambda p, m: (m.update(run_id="20260711-130001-field-supplement"), update_supplement_target(p, m, "20260711/wick/20260711-130000-field-supplement")),
    )
    expect_reject(client, db_path, data_root, "supplement", chained, "supplement_target_not_original")
    rejected += 1
    return {"accepted": accepted, "rejected": rejected}


def exercise_remote_server(packages: dict[str, Path], host: str, runtime_root: str, python_path: str) -> dict[str, int]:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        archive.add(Path(__file__), arcname="gate.py")
        for name, package in sorted(packages.items()):
            archive.add(package, arcname=f"packages/{name}")
    command = (
        "set -euo pipefail; "
        "tmp=$(mktemp -d /tmp/akbs-contract-gate.XXXXXX); "
        "trap 'rm -rf \"$tmp\"' EXIT; "
        "tar -xzf - -C \"$tmp\"; "
        f"PYTHONPATH={shlex.quote(python_path)} python3 \"$tmp/gate.py\" "
        f"--system-root {shlex.quote(runtime_root)} --server-packages-root \"$tmp/packages\""
    )
    result = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", host, "bash", "-lc", shlex.quote(command)],
        input=buffer.getvalue(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode:
        raise AssertionError(result.stderr.decode("utf-8", errors="replace") or result.stdout.decode("utf-8", errors="replace"))
    try:
        payload = json.loads(result.stdout.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise AssertionError(result.stdout.decode("utf-8", errors="replace") + result.stderr.decode("utf-8", errors="replace")) from exc
    if payload.get("status") != "PASS":
        raise AssertionError(f"remote server contract harness failed: {payload}")
    return {"accepted": int(payload["accepted"]), "rejected": int(payload["rejected"])}


def update_supplement_target(package: Path, manifest: dict[str, Any], target: str) -> None:
    manifest["supplement_for_package_key"] = target
    display = manifest["files"]["display"][0]
    set_nested_json(package, display, lambda value: value.setdefault("payload", {}).update(supplement_for_package_key=target))


def retarget_member(package: Path, manifest: dict[str, Any], member: str, run_id: str) -> None:
    manifest["member_alias"] = member
    manifest["member_name"] = member
    manifest["run_id"] = run_id
    display = manifest["files"]["display"][0]
    set_nested_json(package, display, lambda value: value.setdefault("payload", {}).update(member_alias=member, member_name=member))


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate plugin/server incoming v1 compatibility in an isolated runtime.")
    parser.add_argument("--system-root", type=Path, required=True, help="Read-only AKBS system repository root")
    parser.add_argument("--server-host", default="test35", help="SSH host providing the authoritative system Python runtime")
    parser.add_argument("--server-runtime-root", default="/home/test35/akbs/system", help="System repository path on the server host")
    parser.add_argument(
        "--server-python-path",
        default="/home/test35/akbs/system:/home/test35/akbs/runtime/python-vendor",
        help="Authoritative server PYTHONPATH used by the temporary harness",
    )
    parser.add_argument("--server-packages-root", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    system_root = args.system_root.resolve()
    if not (system_root / "akbs_active" / "app.py").is_file():
        raise SystemExit(f"invalid system root: {system_root}")
    if args.server_packages_root:
        package_root = args.server_packages_root.resolve()
        packages = {name: package_root / name for name in ("daily", "weekly", "patch", "supplement")}
        runtime = exercise_server(system_root, package_root.parent, packages)
        print(json.dumps({"status": "PASS", **runtime}, ensure_ascii=False, sort_keys=True))
        return 0
    public = verify_public_contract(system_root)
    with tempfile.TemporaryDirectory(prefix="akbs-contract-gate-") as temporary:
        root = Path(temporary)
        env = write_config(root)
        packages = generate_real_packages(root, env)
        runtime = exercise_remote_server(packages, args.server_host, args.server_runtime_root, args.server_python_path)
    print(json.dumps({"status": "PASS", "contract": "incoming-v1", **public, **runtime}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
