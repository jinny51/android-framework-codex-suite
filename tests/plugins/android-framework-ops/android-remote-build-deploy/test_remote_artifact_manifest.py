from __future__ import annotations

import hashlib
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest


REPO_ROOT = Path(__file__).resolve().parents[4]
LIB_ROOT = REPO_ROOT / "plugins" / "android-framework-ops" / "lib"
if str(LIB_ROOT) not in sys.path:
    sys.path.insert(0, str(LIB_ROOT))

from android_framework_ops.remote_artifact_manifest import (  # noqa: E402
    REMOTE_ARTIFACT_MANIFEST_SCHEMA,
    REMOTE_ARTIFACT_MANIFEST_VERSION,
    RemoteArtifactManifestError,
    create_remote_artifact_manifest,
    validate_remote_artifact_manifest,
    verify_mounted_artifact,
)


class RemoteArtifactManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name).resolve()
        self.remote_root = self.root / "remote-workspace"
        self.mounted_root = self.root / "mounted-workspace"
        self.relative_path = Path(
            "out/target/product/test/system/framework/services.jar"
        )
        self.remote_artifact = self.remote_root / self.relative_path
        self.mounted_artifact = self.mounted_root / self.relative_path
        self.remote_artifact.parent.mkdir(parents=True)
        self.mounted_artifact.parent.mkdir(parents=True)
        self.content = b"remote-services-artifact-v1\n"
        self.remote_artifact.write_bytes(self.content)
        self.mounted_artifact.write_bytes(self.content)

        now = time.time_ns()
        self.build_started_ns = now - 3_000_000_000
        self.artifact_mtime_ns = now - 2_000_000_000
        self.build_finished_ns = now - 1_000_000_000
        os.utime(
            self.remote_artifact,
            ns=(self.artifact_mtime_ns, self.artifact_mtime_ns),
        )
        self.context = {
            "module": "services",
            "profile": "framework-services",
            "workspace_id": "workspace-a91f5c2d",
            "command_id": "build-20260826-001",
        }
        self.manifest = create_remote_artifact_manifest(
            self.remote_artifact,
            remote_root=self.remote_root,
            **self.context,
            build_started_ns=self.build_started_ns,
            build_finished_ns=self.build_finished_ns,
        )

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def validate(self, payload: dict[str, object] | None = None, **overrides: object):
        arguments: dict[str, object] = {
            "expected_module": self.context["module"],
            "expected_profile": self.context["profile"],
            "expected_workspace_id": self.context["workspace_id"],
            "expected_command_id": self.context["command_id"],
            "expected_remote_root": self.remote_root.as_posix(),
        }
        arguments.update(overrides)
        return validate_remote_artifact_manifest(payload or self.manifest, **arguments)

    def verify(self, payload: dict[str, object] | None = None, **overrides: object) -> Path:
        arguments: dict[str, object] = {
            "mounted_root": self.mounted_root,
            "remote_root": self.remote_root.as_posix(),
            "expected_module": self.context["module"],
            "expected_profile": self.context["profile"],
            "expected_workspace_id": self.context["workspace_id"],
            "expected_command_id": self.context["command_id"],
        }
        arguments.update(overrides)
        return verify_mounted_artifact(payload or self.manifest, **arguments)

    def test_remote_generation_computes_canonical_file_facts(self) -> None:
        self.assertEqual(
            self.manifest,
            {
                "schema": REMOTE_ARTIFACT_MANIFEST_SCHEMA,
                "version": REMOTE_ARTIFACT_MANIFEST_VERSION,
                "remote_path": self.remote_artifact.resolve().as_posix(),
                **self.context,
                "build_started_ns": self.build_started_ns,
                "build_finished_ns": self.build_finished_ns,
                "size": len(self.content),
                "mtime_ns": self.artifact_mtime_ns,
                "sha256": hashlib.sha256(self.content).hexdigest(),
            },
        )
        parsed = self.validate()
        self.assertEqual(parsed.to_dict(), self.manifest)

    def test_mounted_verification_derives_path_and_rehashes_file(self) -> None:
        verified = self.verify()
        self.assertEqual(verified, self.mounted_artifact.resolve())

    def test_manifest_requires_exact_closed_schema(self) -> None:
        for field in tuple(self.manifest):
            with self.subTest(missing=field):
                incomplete = dict(self.manifest)
                incomplete.pop(field)
                with self.assertRaisesRegex(RemoteArtifactManifestError, "missing required fields"):
                    self.validate(incomplete)

        forged_local_path = {**self.manifest, "local_path": "/tmp/caller-selected.jar"}
        with self.assertRaisesRegex(RemoteArtifactManifestError, "unsupported fields"):
            self.validate(forged_local_path)

        non_string_field = {**self.manifest, 7: "ambiguous"}
        with self.assertRaisesRegex(RemoteArtifactManifestError, "field names must be strings"):
            self.validate(non_string_field)

    def test_context_fields_are_bound_to_trusted_transaction(self) -> None:
        expected_names = {
            "module": "expected_module",
            "profile": "expected_profile",
            "workspace_id": "expected_workspace_id",
            "command_id": "expected_command_id",
        }
        for field, expected_name in expected_names.items():
            with self.subTest(field=field):
                forged = dict(self.manifest)
                forged[field] = f"forged-{field}"
                with self.assertRaisesRegex(RemoteArtifactManifestError, "active build context"):
                    self.validate(forged)

                with self.assertRaisesRegex(RemoteArtifactManifestError, "active build context"):
                    self.validate(self.manifest, **{expected_name: f"other-{field}"})

    def test_generation_rejects_artifact_outside_bound_workspace(self) -> None:
        outside = self.root / "outside.jar"
        outside.write_bytes(self.content)
        os.utime(outside, ns=(self.artifact_mtime_ns, self.artifact_mtime_ns))
        with self.assertRaisesRegex(RemoteArtifactManifestError, "outside"):
            create_remote_artifact_manifest(
                outside,
                remote_root=self.remote_root,
                **self.context,
                build_started_ns=self.build_started_ns,
                build_finished_ns=self.build_finished_ns,
            )

    def test_generation_rejects_empty_artifact(self) -> None:
        empty = self.remote_root / "out/empty.jar"
        empty.parent.mkdir(parents=True, exist_ok=True)
        empty.touch()
        os.utime(empty, ns=(self.artifact_mtime_ns, self.artifact_mtime_ns))
        with self.assertRaisesRegex(RemoteArtifactManifestError, "size"):
            create_remote_artifact_manifest(
                empty,
                remote_root=self.remote_root,
                **self.context,
                build_started_ns=self.build_started_ns,
                build_finished_ns=self.build_finished_ns,
            )

    def test_remote_path_must_be_canonical_and_inside_workspace(self) -> None:
        cases = (
            "/tmp/outside/services.jar",
            f"{self.remote_root.as_posix()}/out/../services.jar",
            "relative/services.jar",
            f"//{self.remote_root.name}/services.jar",
            f"{self.remote_root.as_posix()}/out\\services.jar",
            f"{self.remote_root.as_posix()}/out/services.jar\rforged",
        )
        for path in cases:
            with self.subTest(path=path):
                forged = {**self.manifest, "remote_path": path}
                with self.assertRaises(RemoteArtifactManifestError):
                    self.validate(forged)

    def test_generation_and_validation_reject_stale_time_windows(self) -> None:
        os.utime(
            self.remote_artifact,
            ns=(self.build_started_ns - 1, self.build_started_ns - 1),
        )
        with self.assertRaisesRegex(RemoteArtifactManifestError, "stale"):
            create_remote_artifact_manifest(
                self.remote_artifact,
                remote_root=self.remote_root,
                **self.context,
                build_started_ns=self.build_started_ns,
                build_finished_ns=self.build_finished_ns,
            )

        stale = {**self.manifest, "mtime_ns": self.build_started_ns - 1}
        with self.assertRaisesRegex(RemoteArtifactManifestError, "stale"):
            self.validate(stale)

        after_finish = {**self.manifest, "mtime_ns": self.build_finished_ns + 1}
        with self.assertRaisesRegex(RemoteArtifactManifestError, "later than"):
            self.validate(after_finish)

        reversed_window = {
            **self.manifest,
            "build_started_ns": self.build_finished_ns + 1,
        }
        with self.assertRaisesRegex(RemoteArtifactManifestError, "finish precedes"):
            self.validate(reversed_window)

    def test_age_and_future_checks_reject_stale_handoffs(self) -> None:
        with self.assertRaisesRegex(RemoteArtifactManifestError, "older than"):
            self.validate(
                now_ns=self.build_finished_ns + 10_000,
                max_build_age_ns=9_999,
            )
        with self.assertRaisesRegex(RemoteArtifactManifestError, "future"):
            self.validate(now_ns=self.build_finished_ns - 1)
        with self.assertRaisesRegex(RemoteArtifactManifestError, "requires now_ns"):
            self.validate(max_build_age_ns=1)

    def test_mounted_file_rejects_size_and_sha256_mismatches(self) -> None:
        self.mounted_artifact.write_bytes(b"short")
        with self.assertRaisesRegex(RemoteArtifactManifestError, "size does not match"):
            self.verify()

        same_size_forgery = b"x" * len(self.content)
        self.mounted_artifact.write_bytes(same_size_forgery)
        with self.assertRaisesRegex(RemoteArtifactManifestError, "sha256 does not match"):
            self.verify()

    def test_caller_supplied_file_facts_are_recomputed_locally(self) -> None:
        forged_size = {**self.manifest, "size": self.manifest["size"] + 1}
        with self.assertRaisesRegex(RemoteArtifactManifestError, "size does not match"):
            self.verify(forged_size)

        forged_hash = {**self.manifest, "sha256": "0" * 64}
        with self.assertRaisesRegex(RemoteArtifactManifestError, "sha256 does not match"):
            self.verify(forged_hash)

    def test_mounted_path_escape_is_rejected_before_hashing(self) -> None:
        outside = self.root / "outside-services.jar"
        outside.write_bytes(self.content)
        self.mounted_artifact.unlink()
        self.mounted_artifact.symlink_to(outside)
        with self.assertRaisesRegex(RemoteArtifactManifestError, "escapes or is missing"):
            self.verify()

    def test_invalid_schema_version_hash_and_types_fail_closed(self) -> None:
        cases = (
            {**self.manifest, "schema": "caller-schema-v1"},
            {**self.manifest, "version": 2},
            {**self.manifest, "version": True},
            {**self.manifest, "sha256": "ABC" * 21 + "A"},
            {**self.manifest, "size": True},
            {**self.manifest, "command_id": "contains/a/slash"},
        )
        for payload in cases:
            with self.subTest(payload=payload):
                with self.assertRaises(RemoteArtifactManifestError):
                    self.validate(payload)


if __name__ == "__main__":
    unittest.main()
