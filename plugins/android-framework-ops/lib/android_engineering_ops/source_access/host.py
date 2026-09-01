"""Detect the local host before selecting a source-access platform adapter."""

from __future__ import annotations

import os
import platform
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


SUPPORTED_HOSTS = ("wsl", "macos")


class UnsupportedSourceAccessHost(RuntimeError):
    """No source-access adapter is valid for the current host."""


@dataclass(frozen=True)
class SourceAccessHost:
    host: str
    system: str
    release: str
    version: str
    evidence: tuple[str, ...]


def detect_source_access_host(
    *,
    system: str | None = None,
    release: str | None = None,
    version: str | None = None,
    environ: Mapping[str, str] | None = None,
) -> SourceAccessHost:
    actual_system = (system if system is not None else platform.system()).strip()
    actual_release = (release if release is not None else platform.release()).strip()
    actual_version = (version if version is not None else platform.version()).strip()
    environment = os.environ if environ is None else environ

    if actual_system == "Darwin":
        return SourceAccessHost(
            host="macos",
            system=actual_system,
            release=actual_release,
            version=actual_version,
            evidence=("platform.system=Darwin",),
        )

    if actual_system == "Linux":
        evidence: list[str] = []
        if environment.get("WSL_INTEROP"):
            evidence.append("env.WSL_INTEROP")
        if environment.get("WSL_DISTRO_NAME"):
            evidence.append("env.WSL_DISTRO_NAME")
        kernel_text = f"{actual_release}\n{actual_version}".lower()
        if "microsoft" in kernel_text or "wsl" in kernel_text:
            evidence.append("linux-kernel-wsl-marker")
        if evidence:
            return SourceAccessHost(
                host="wsl",
                system=actual_system,
                release=actual_release,
                version=actual_version,
                evidence=tuple(evidence),
            )

    raise UnsupportedSourceAccessHost(
        "android-source-access supports WSL and macOS only; "
        f"detected system={actual_system or '<empty>'} release={actual_release or '<empty>'}"
    )


def adapter_root(plugin_root: Path, host: str) -> Path:
    if host not in SUPPORTED_HOSTS:
        raise UnsupportedSourceAccessHost(f"unsupported source-access host: {host}")
    root = plugin_root / "adapters" / "source-access" / host
    if not root.is_dir():
        raise UnsupportedSourceAccessHost(
            f"source-access adapter is missing for host {host}: {root}"
        )
    return root
