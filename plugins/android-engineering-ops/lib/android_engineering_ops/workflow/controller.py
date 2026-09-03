"""Dependency-free controller runtime for the packaged workflow contracts.

This module seals and validates records.  It deliberately does not create an
isolated worker, execute a command, grant authority, or accept a Gate; those are
controller actions outside the Phase 2 materialization boundary.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from android_engineering_ops.practices.schema import (
    ContractValidationError,
    validate_document,
)


PLUGIN_ROOT = Path(__file__).resolve().parents[3]
CONTRACT_ROOT = PLUGIN_ROOT / "contracts/android-change-workflow/v1"
STAGE_SCHEMA = CONTRACT_ROOT / "stage-snapshot.schema.json"
ASSIGNMENT_SCHEMA = CONTRACT_ROOT / "worker-assignment.schema.json"
RESULT_SCHEMA = CONTRACT_ROOT / "worker-result.schema.json"

_NO_WORKER_PERMISSIONS = {
    "may_acquire_authority": False,
    "may_expand_scope": False,
    "may_upload": False,
    "may_accept_gate": False,
    "may_final_accept": False,
}
_CONSTRAINT_DEFAULTS = {
    "max_automatic_escalations": 1,
    "environment_failure_escalates_model": False,
}


class ControllerValidationError(ValueError):
    """A workflow record is malformed, replayed, or outside its assignment."""


def _canonical_domain(value: Any, *, path: str = "$") -> None:
    if value is None or isinstance(value, (bool, str, int)):
        return
    if isinstance(value, float):
        raise ControllerValidationError(
            f"canonical workflow JSON forbids floating-point numbers: {path}"
        )
    if isinstance(value, list):
        for index, item in enumerate(value):
            _canonical_domain(item, path=f"{path}/{index}")
        return
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise ControllerValidationError(
                f"canonical workflow JSON requires text object keys: {path}"
            )
        for key, item in value.items():
            _canonical_domain(item, path=f"{path}/{key}")
        return
    raise ControllerValidationError(
        f"unsupported canonical workflow JSON value at {path}"
    )


def canonical_json_sha256(value: Any) -> str:
    """Hash one record using the packaged canonical JSON v1 representation."""
    _canonical_domain(value)
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _mapping(value: Any, *, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise ControllerValidationError(f"{label} must be an object")
    return copy.deepcopy(dict(value))


def _validate_schema(value: Mapping[str, Any], path: Path, *, label: str) -> None:
    try:
        validate_document(value, path)
    except (ContractValidationError, OSError) as exc:
        raise ControllerValidationError(f"{label} violates packaged schema: {exc}") from exc


def _reject_fixed(payload: Mapping[str, Any], fixed: Sequence[str], *, label: str) -> None:
    supplied = sorted(set(payload) & set(fixed))
    if supplied:
        raise ControllerValidationError(
            f"{label} payload cannot set controller-owned fields: {', '.join(supplied)}"
        )


def generate_stage_snapshot(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Seal a snapshot payload that omits schema and controller."""
    body = _mapping(payload, label="stage snapshot")
    _reject_fixed(body, ("schema", "controller"), label="stage snapshot")
    value = {
        "schema": "stage-snapshot-v1",
        **body,
        "controller": {
            "id": "android-change-workflow",
            "authority": "stage_gate_and_requirement_acceptance",
        },
    }
    _validate_stage_semantics(value)
    return value


def generate_worker_assignment(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Seal an assignment without allowing the caller to widen authority."""
    body = _mapping(payload, label="worker assignment")
    _reject_fixed(
        body,
        ("schema", "controller", "permissions", "result_schema"),
        label="worker assignment",
    )
    constraints = _mapping(body.get("constraints"), label="assignment constraints")
    for key, expected in _CONSTRAINT_DEFAULTS.items():
        if key in constraints and constraints[key] != expected:
            raise ControllerValidationError(
                f"assignment cannot override controller constraint {key}"
            )
        constraints[key] = expected
    body["constraints"] = constraints
    value = {
        "schema": "worker-assignment-v1",
        **body,
        "controller": "android-change-workflow",
        "permissions": dict(_NO_WORKER_PERMISSIONS),
        "result_schema": "worker-result-v1",
    }
    _validate_assignment_semantics(value)
    return value


def generate_worker_result(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Seal a worker report payload; validity against an assignment is separate."""
    body = _mapping(payload, label="worker result")
    _reject_fixed(body, ("schema",), label="worker result")
    value = {"schema": "worker-result-v1", **body}
    _validate_schema(value, RESULT_SCHEMA, label="worker result")
    return value


def _stage_context(value: Mapping[str, Any]) -> dict[str, Any]:
    """Return the immutable context a controller must obtain independently."""
    return {
        "run_id": value.get("run_id"),
        "stage": value.get("stage"),
        "input_bindings": value.get("input_bindings"),
        "provider_resolution": value.get("provider_resolution"),
        "workspace_bindings": value.get("workspace_bindings"),
        "event": value.get("event"),
    }


def stage_context_sha256(value: Mapping[str, Any]) -> str:
    return canonical_json_sha256(_stage_context(value))


def _validate_stage_semantics(snapshot: Mapping[str, Any]) -> None:
    _validate_schema(snapshot, STAGE_SCHEMA, label="stage snapshot")
    sequence = snapshot.get("sequence")
    previous = snapshot.get("previous_snapshot_sha256")
    if sequence == 1 and previous is not None:
        raise ControllerValidationError("first stage snapshot cannot have a previous hash")
    if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 1:
        raise ControllerValidationError("stage snapshot sequence is invalid")
    if sequence > 1 and not previous:
        raise ControllerValidationError("stage snapshot hash chain is incomplete")
    reason = snapshot.get("snapshot_reason")
    event = snapshot.get("event") or {}
    stage = snapshot.get("stage") or {}
    disposition = snapshot.get("requirement_disposition")
    if reason == "delegating_worker" and (
        event.get("type") != "assignment_planned"
        or not event.get("planned_assignment_id")
        or not event.get("planned_worker_task_id")
    ):
        raise ControllerValidationError("delegating snapshot lacks planned assignment")
    if reason == "gate_transition" and event.get("type") != "gate_changed":
        raise ControllerValidationError("gate-transition snapshot event differs")
    if disposition is not None and reason != "gate_transition":
        raise ControllerValidationError(
            "requirement disposition belongs only to a gate transition"
        )
    if (
        disposition in {"accepted", "rejected"} and stage.get("state") != "completed"
    ) or (disposition == "blocked" and stage.get("state") != "blocked"):
        raise ControllerValidationError("requirement disposition and stage state differ")
    if reason == "entering_high_risk_mutation" and (
        stage.get("risk_level") != "high"
        or not snapshot.get("workspace_bindings")
        or event.get("type") != "mutation_authority_bound"
    ):
        raise ControllerValidationError(
            "high-risk mutation snapshot lacks authority bindings"
        )
    if reason == "cross_session_handoff" and event.get("type") != "handoff":
        raise ControllerValidationError("cross-session handoff event differs")
    if reason == "pause_resume" and (event.get("type"), stage.get("state")) not in {
        ("paused", "paused"),
        ("resumed", "active"),
    }:
        raise ControllerValidationError("pause/resume snapshot state differs")
    resolution = snapshot.get("provider_resolution") or {}
    mode = resolution.get("selection_mode")
    for capability in ("coding", "execution"):
        selected = resolution.get(capability) or {}
        source, why = selected.get("source"), selected.get("reason")
        if source == "provider" and why != "provider_capability":
            raise ControllerValidationError("provider capability resolution reason differs")
        if source == "core" and why not in {
            "mode_none", "capability_absent", "applicability_miss",
        }:
            raise ControllerValidationError("core capability resolution reason differs")
    identity = (
        resolution.get("provider_id"),
        resolution.get("provider_version"),
        resolution.get("provider_manifest_sha256"),
    )
    if mode == "none":
        if any(identity) or any(
            resolution.get(item) != {"source": "core", "reason": "mode_none"}
            for item in ("coding", "execution")
        ):
            raise ControllerValidationError("mode none cannot resolve a provider")
    elif mode in {"jinny", "custom"}:
        if not all(identity):
            raise ControllerValidationError("selected provider identity is incomplete")
        if mode == "jinny" and identity[0] != "jinny-android-practices":
            raise ControllerValidationError("jinny mode must bind the Jinny provider")
        if mode == "custom" and identity[0] == "jinny-android-practices":
            raise ControllerValidationError("custom mode cannot impersonate Jinny")
    else:
        raise ControllerValidationError("provider selection mode is invalid")


def validate_stage_snapshot(
    snapshot: Mapping[str, Any],
    *,
    expected_run_id: str,
    expected_stage_id: str,
    expected_context_sha256: str,
    expected_provider_resolution: Mapping[str, Any],
) -> None:
    """Validate a snapshot against controller-owned live expectations."""
    _validate_stage_semantics(snapshot)
    if snapshot.get("run_id") != expected_run_id:
        raise ControllerValidationError("stage snapshot run_id differs from controller")
    if (snapshot.get("stage") or {}).get("stage_id") != expected_stage_id:
        raise ControllerValidationError("stage snapshot stage_id differs from controller")
    if stage_context_sha256(snapshot) != expected_context_sha256:
        raise ControllerValidationError("stage snapshot context differs from controller")
    if snapshot.get("provider_resolution") != dict(expected_provider_resolution):
        raise ControllerValidationError("stage snapshot provider resolution differs")


def _scope_by_repository(assignment: Mapping[str, Any]) -> dict[str, set[tuple[str, str]]]:
    scope = assignment.get("scope") or {}
    repositories = scope.get("repositories") or []
    paths = scope.get("paths") or []
    if not repositories or not paths:
        raise ControllerValidationError("worker assignment scope must be non-empty")
    result = {repository: set() for repository in repositories}
    for item in paths:
        repository = item.get("repository_id")
        if repository not in result:
            raise ControllerValidationError(
                "worker assignment path repository differs from scope"
            )
        result[repository].add((str(item.get("kind")), str(item.get("path"))))
    if any(not selected for selected in result.values()):
        raise ControllerValidationError(
            "every assignment repository requires at least one path"
        )
    return result


def _validate_assignment_semantics(assignment: Mapping[str, Any]) -> None:
    _validate_schema(assignment, ASSIGNMENT_SCHEMA, label="worker assignment")
    if assignment.get("permissions") != _NO_WORKER_PERMISSIONS:
        raise ControllerValidationError("worker assignment permissions exceed authority")
    constraints = assignment.get("constraints") or {}
    if any(constraints.get(key) != expected for key, expected in _CONSTRAINT_DEFAULTS.items()):
        raise ControllerValidationError("worker assignment escalation contract differs")
    scope = _scope_by_repository(assignment)
    effect = assignment.get("effect")
    if effect == "read_only":
        if any(
            key in constraints
            for key in ("authority_ref", "workspace_bindings", "controlled_operation")
        ):
            raise ControllerValidationError("read-only assignment contains mutation authority")
    elif effect == "workspace_mutation":
        bindings = constraints.get("workspace_bindings") or []
        if not constraints.get("authority_ref") or not bindings:
            raise ControllerValidationError("mutation assignment lacks authority bindings")
        repositories = [item.get("repository_id") for item in bindings]
        if len(repositories) != len(set(repositories)) or set(repositories) != set(scope):
            raise ControllerValidationError(
                "mutation workspace repositories differ from scope"
            )
        for binding in bindings:
            repository = binding.get("repository_id")
            binding_scope = set()
            for item in binding.get("paths") or []:
                if item.get("repository_id") != repository:
                    raise ControllerValidationError(
                        "mutation workspace path belongs to another repository"
                    )
                binding_scope.add((str(item.get("kind")), str(item.get("path"))))
            if (
                binding.get("authority_ref") != constraints.get("authority_ref")
                or binding_scope != scope[repository]
            ):
                raise ControllerValidationError(
                    "mutation workspace authority or path scope differs"
                )
    elif effect == "controlled_operation":
        operation = constraints.get("controlled_operation")
        if not constraints.get("authority_ref") or not operation:
            raise ControllerValidationError(
                "controlled operation lacks frozen authority bindings"
            )
        request_sha = (assignment.get("input_bindings") or {}).get(
            "command_request_sha256"
        )
        if not request_sha:
            raise ControllerValidationError(
                "controlled operation lacks command_request_sha256 input binding"
            )
    else:  # schema already rejects this; retained as a stable runtime error.
        raise ControllerValidationError("worker assignment effect is invalid")


def _snapshot_workspace_bindings(snapshot: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    rows = snapshot.get("workspace_bindings") or []
    result = {str(item.get("repository_id")): item for item in rows}
    if len(result) != len(rows):
        raise ControllerValidationError("stage snapshot repeats a workspace repository")
    return result


def validate_worker_assignment(
    assignment: Mapping[str, Any],
    *,
    source_snapshot: Mapping[str, Any],
    expected_run_id: str,
    expected_stage_id: str,
    expected_context_sha256: str,
    expected_provider_resolution: Mapping[str, Any],
    expected_worker_task_id: str | None = None,
) -> None:
    """Validate an assignment and its complete snapshot/context chain."""
    validate_stage_snapshot(
        source_snapshot,
        expected_run_id=expected_run_id,
        expected_stage_id=expected_stage_id,
        expected_context_sha256=expected_context_sha256,
        expected_provider_resolution=expected_provider_resolution,
    )
    _validate_assignment_semantics(assignment)
    if not isinstance(expected_worker_task_id, str) or not expected_worker_task_id:
        raise ControllerValidationError(
            "controller expected worker_task_id is required"
        )
    if assignment.get("run_id") != expected_run_id:
        raise ControllerValidationError("worker assignment run_id differs from controller")
    if assignment.get("source_snapshot_sha256") != canonical_json_sha256(source_snapshot):
        raise ControllerValidationError("worker assignment source snapshot hash differs")
    event = source_snapshot.get("event") or {}
    if (
        source_snapshot.get("snapshot_reason") != "delegating_worker"
        or event.get("planned_assignment_id") != assignment.get("assignment_id")
        or event.get("planned_worker_task_id") != expected_worker_task_id
        or assignment.get("worker_task_id") != expected_worker_task_id
    ):
        raise ControllerValidationError(
            "worker assignment/task was not planned by its snapshot and controller"
        )
    if (assignment.get("input_bindings") or {}).get(
        "context_sha256"
    ) != expected_context_sha256:
        raise ControllerValidationError("worker assignment context binding differs")

    resolution = source_snapshot.get("provider_resolution") or {}
    execution = resolution.get("execution") or {}
    assignee = assignment.get("assignee") or {}
    if execution.get("source") == "provider":
        expected_assignee = {
            "provider_id": resolution.get("provider_id"),
            "provider_version": resolution.get("provider_version"),
            "provider_manifest_sha256": resolution.get("provider_manifest_sha256"),
        }
        if assignee.get("profile_source") != "provider" or any(
            assignee.get(key) != value for key, value in expected_assignee.items()
        ):
            raise ControllerValidationError("worker assignment provider binding differs")
    elif assignee.get("profile_source") != "core":
        raise ControllerValidationError("core execution resolution cannot assign provider profile")

    if assignment.get("effect") == "workspace_mutation":
        snapshot_bindings = _snapshot_workspace_bindings(source_snapshot)
        assignment_bindings = {
            str(item.get("repository_id")): item
            for item in (assignment.get("constraints") or {}).get("workspace_bindings") or []
        }
        if set(snapshot_bindings) != set(assignment_bindings):
            raise ControllerValidationError(
                "assignment workspace repositories differ from stage snapshot"
            )
        for repository, assigned in assignment_bindings.items():
            frozen = snapshot_bindings[repository]
            for key in (
                "workspace_id", "base_revision", "target_expected_head", "authority_ref",
            ):
                if assigned.get(key) != frozen.get(key):
                    raise ControllerValidationError(
                        f"assignment workspace {key} differs from stage snapshot"
                    )
            if {item.get("path") for item in assigned.get("paths") or []} != set(
                frozen.get("scope") or []
            ):
                raise ControllerValidationError(
                    "assignment workspace paths differ from stage snapshot"
                )


def _allowed_path(scopes: Sequence[Mapping[str, Any]], repository: str, path: str) -> bool:
    for item in scopes:
        if item.get("repository_id") != repository:
            continue
        selected = str(item.get("path") or "")
        if item.get("kind") == "file" and path == selected:
            return True
        if item.get("kind") == "tree" and (
            path == selected or path.startswith(selected + "/")
        ):
            return True
    return False


def _unique_rows(rows: Sequence[Mapping[str, Any]], key: str, *, label: str) -> None:
    values = [row.get(key) for row in rows]
    if len(values) != len(set(values)):
        raise ControllerValidationError(f"worker result repeats {label}")


def _indexed_rows(
    rows: Sequence[Mapping[str, Any]] | None,
    key: str,
    *,
    label: str,
) -> dict[str, dict[str, Any]]:
    if rows is None or isinstance(rows, (str, bytes)):
        raise ControllerValidationError(f"controller expected {label} is required")
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise ControllerValidationError(f"controller expected {label} contains a non-object")
        identifier = row.get(key)
        if not isinstance(identifier, str) or not identifier or identifier in result:
            raise ControllerValidationError(f"controller expected {label} has an invalid/repeated {key}")
        result[identifier] = copy.deepcopy(dict(row))
    return result


def _indexed_changes(
    rows: Sequence[Mapping[str, Any]] | None,
) -> dict[tuple[str, str, str, str], dict[str, Any]]:
    if rows is None or isinstance(rows, (str, bytes)):
        raise ControllerValidationError("controller expected change readback is required")
    result: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise ControllerValidationError(
                "controller expected change readback contains a non-object"
            )
        key = (
            str(row.get("repository_id") or ""),
            str(row.get("operation") or ""),
            str(row.get("path") or ""),
            str(row.get("rename_from") or ""),
        )
        if not all(key[:3]) or key in result:
            raise ControllerValidationError(
                "controller expected change readback has an invalid/repeated identity"
            )
        result[key] = copy.deepcopy(dict(row))
    return result


def validate_worker_result(
    result: Mapping[str, Any],
    *,
    assignment: Mapping[str, Any],
    source_snapshot: Mapping[str, Any],
    expected_run_id: str,
    expected_stage_id: str,
    expected_context_sha256: str,
    expected_provider_resolution: Mapping[str, Any],
    expected_worker_task_id: str | None = None,
    expected_end_heads: Mapping[str, str] | None = None,
    expected_changes: Sequence[Mapping[str, Any]] | None = None,
    expected_evidence: Sequence[Mapping[str, Any]] | None = None,
    expected_checks: Sequence[Mapping[str, Any]] | None = None,
    expected_commands: Sequence[Mapping[str, Any]] | None = None,
) -> None:
    """Validate a worker result against external state and its sealed chain."""
    validate_worker_assignment(
        assignment,
        source_snapshot=source_snapshot,
        expected_run_id=expected_run_id,
        expected_stage_id=expected_stage_id,
        expected_context_sha256=expected_context_sha256,
        expected_provider_resolution=expected_provider_resolution,
        expected_worker_task_id=expected_worker_task_id,
    )
    _validate_schema(result, RESULT_SCHEMA, label="worker result")
    if (
        result.get("assignment_id") != assignment.get("assignment_id")
        or result.get("assignment_sha256") != canonical_json_sha256(assignment)
        or result.get("run_id") != expected_run_id
        or result.get("attempt") != assignment.get("attempt")
        or (result.get("worker_binding") or {}).get("worker_profile_id")
        != (assignment.get("assignee") or {}).get("worker_profile_id")
        or (result.get("worker_binding") or {}).get("worker_task_id")
        != expected_worker_task_id
    ):
        raise ControllerValidationError("worker result does not bind the exact assignment")
    if result.get("reported_scope_deviations"):
        raise ControllerValidationError("worker result reports a scope deviation")

    evidence = result.get("evidence") or []
    commands = result.get("commands") or []
    checks = result.get("checks") or []
    changes = result.get("reported_changes") or []
    _unique_rows(evidence, "evidence_id", label="evidence ID")
    _unique_rows(commands, "command_id", label="command ID")
    _unique_rows(checks, "check_id", label="check ID")
    actual_evidence = _indexed_rows(evidence, "evidence_id", label="evidence readback")
    controller_evidence = _indexed_rows(
        expected_evidence, "evidence_id", label="evidence readback"
    )
    if actual_evidence != controller_evidence:
        raise ControllerValidationError(
            "worker result evidence bytes/hash/size differ from controller readback"
        )
    actual_checks = _indexed_rows(checks, "check_id", label="check receipts")
    controller_checks = _indexed_rows(
        expected_checks, "check_id", label="check receipts"
    )
    if actual_checks != controller_checks:
        raise ControllerValidationError(
            "worker result check status/receipt differs from controller readback"
        )
    actual_commands = _indexed_rows(commands, "command_id", label="command receipts")
    controller_commands = _indexed_rows(
        expected_commands, "command_id", label="command receipts"
    )
    if actual_commands != controller_commands:
        raise ControllerValidationError(
            "worker result command request/receipt/exit differs from controller readback"
        )
    actual_changes = _indexed_changes(changes)
    controller_changes = _indexed_changes(expected_changes)
    if actual_changes != controller_changes:
        raise ControllerValidationError(
            "worker result path/hash changes differ from controller readback"
        )
    required = set(assignment.get("required_evidence") or [])
    if not required.issubset({item.get("kind") for item in evidence}):
        raise ControllerValidationError("worker result lacks assignment-required evidence")
    if result.get("outcome") == "completed" and (not checks or not evidence):
        raise ControllerValidationError("completed result lacks checks or evidence")
    for check in checks:
        if (check.get("status") == "not_run") != (check.get("receipt_sha256") is None):
            raise ControllerValidationError("worker result check receipt semantics differ")

    effect = assignment.get("effect")
    observed_rows = result.get("observed_workspaces") or []
    _unique_rows(observed_rows, "repository_id", label="workspace repository")
    actual_end_heads = {
        str(item.get("repository_id")): str(item.get("end_head"))
        for item in observed_rows
    }
    if expected_end_heads is None:
        raise ControllerValidationError("controller expected end-head readback is required")
    if actual_end_heads != dict(expected_end_heads):
        raise ControllerValidationError("worker result end heads differ from controller readback")
    if effect == "read_only":
        if changes or any(
            item.get("start_head") != item.get("end_head") for item in observed_rows
        ):
            raise ControllerValidationError("read-only result reports repository mutation")
    if effect == "workspace_mutation":
        bindings = {
            item["repository_id"]: item
            for item in (assignment.get("constraints") or {}).get("workspace_bindings") or []
        }
        observed = {item.get("repository_id"): item for item in observed_rows}
        if not observed or not changes or set(observed) != set(bindings):
            raise ControllerValidationError(
                "mutation result lacks exact workspace or change facts"
            )
        end_heads: dict[str, str] = {}
        for repository, frozen in bindings.items():
            actual = observed[repository]
            if any(
                actual.get(key) != frozen.get(key)
                for key in ("workspace_id", "base_revision")
            ) or actual.get("start_head") != frozen.get("base_revision"):
                raise ControllerValidationError("worker result workspace/base binding differs")
            if actual.get("end_head") != frozen.get("target_expected_head"):
                raise ControllerValidationError(
                    "worker result end head differs from target expected head"
                )
            end_heads[repository] = str(actual.get("end_head"))
        if end_heads != dict(expected_end_heads):
            raise ControllerValidationError("worker result end heads differ from controller")
        scopes = assignment.get("scope", {}).get("paths") or []
        for change in changes:
            repository = str(change.get("repository_id") or "")
            if not _allowed_path(scopes, repository, str(change.get("path") or "")):
                raise ControllerValidationError("worker result change escapes assignment scope")
            rename_from = change.get("rename_from")
            if rename_from and not _allowed_path(scopes, repository, str(rename_from)):
                raise ControllerValidationError(
                    "worker result rename source escapes assignment scope"
                )
    if effect == "controlled_operation":
        operation = (assignment.get("constraints") or {}).get("controlled_operation") or {}
        expected_command = operation.get("command_id")
        if [item.get("command_id") for item in commands] != [expected_command]:
            raise ControllerValidationError(
                "controlled operation command receipt differs from assignment"
            )
        request_sha = (assignment.get("input_bindings") or {}).get(
            "command_request_sha256"
        )
        if commands[0].get("request_sha256") != request_sha:
            raise ControllerValidationError(
                "controlled operation command request hash differs"
            )
