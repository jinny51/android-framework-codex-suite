from __future__ import annotations

import re
from pathlib import Path
from typing import Any


USB_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9])usb(?![A-Za-z0-9])", re.I)
USB_CAMEL_PATH_RE = re.compile(r"(?:^|[/_.-])Usb(?=[A-Z0-9])")
AUTHOR_DATE_RE = re.compile(r"//[A-Za-z0-9_]+\s+\d{8}@")
BANNED_LOG_PATTERNS = (
    "Log.v(",
    "Log.d(",
    "Log.i(",
    "Log.w(",
    "Log.e(",
    "Slog.v(",
    "Slog.d(",
    "Slog.i(",
    "Slog.w(",
    "Slog.e(",
    "Slog.wtf(",
)
XML_RESOURCE_NAME_RE = re.compile(
    r"<(?:string|string-array|array|plurals|bool|integer|color|dimen|style)\b[^>]*\bname=[\"']([^\"']+)[\"']"
)


def patch_modified_files(path: Path) -> list[str]:
    files: list[str] = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.startswith("diff --git "):
            continue
        parts = line.split()
        if len(parts) < 4:
            continue
        item = parts[3]
        if item.startswith("b/"):
            item = item[2:]
        if item not in files:
            files.append(item)
    return files


def patch_added_lines(text: str) -> list[str]:
    return [line[1:] for line in text.splitlines() if line.startswith("+") and not line.startswith("+++")]


def patch_changed_lines(text: str) -> list[str]:
    return [
        line[1:]
        for line in text.splitlines()
        if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))
    ]


def resource_keys_from_patch_text(text: str) -> list[str]:
    keys = {
        *re.findall(r"R\.string\.([A-Za-z0-9_]+)", text),
        *re.findall(r"@string/([A-Za-z0-9_]+)", text),
        *XML_RESOURCE_NAME_RE.findall(text),
    }
    return sorted(key for key in keys if key)


def has_usb_semantic_anchor(text: str) -> bool:
    return "ueventd" in text.lower() or bool(USB_TOKEN_RE.search(text) or USB_CAMEL_PATH_RE.search(text))


def patch_modules_from_files(files: list[str]) -> list[str]:
    modules: list[str] = []
    for path in files:
        lower = path.lower()
        if "/com/android/server/wm/" in lower or "windowstate" in lower:
            modules.append("WindowManager")
        if "activitytaskmanager" in lower or "activityrecord" in lower:
            modules.append("ActivityTaskManager")
        if "phonewindowmanager" in lower or "/com/android/server/policy/" in lower:
            modules.append("Policy")
        if "packagemanager" in lower or "/com/android/server/pm/" in lower:
            modules.append("PackageManager")
        if "systemui" in lower or "/com/android/systemui/" in lower:
            modules.append("SystemUI")
        if "launcher" in lower or "quickstep" in lower or "recentsview" in lower:
            modules.append("Launcher")
        if "/input/" in lower or "inputflinger" in lower:
            modules.append("Input")
        if "frameworks/base/core/res/" in lower:
            modules.append("FrameworkResources")
        if "/com/android/server/audio/" in lower or "audioservice" in lower or "audioflinger" in lower or "mediafocuscontrol" in lower:
            modules.append("Audio")
        if "cameraservice" in lower or "camera2" in lower:
            modules.append("Camera")
        if "vold" in lower or "volumemanager" in lower or "publicvolume" in lower or "obbvolume" in lower or "externalstorage" in lower:
            modules.append("Storage")
        if "wifiservice" in lower or "/wifi/" in lower:
            modules.append("Wifi")
        if has_usb_semantic_anchor(path):
            modules.append("USB")
        if any(name in lower for name in ("rockchip_apps.mk", "apps.mk", "boardconfig.mk", "device.mk")):
            modules.append("ProductConfig")
    if not modules and files:
        parts = files[0].split("/")
        modules.append("-".join(parts[:2]) if len(parts) >= 2 else parts[0])
    return sorted(set(modules))


def patch_semantic_flags(joined: str, modules: list[str]) -> dict[str, bool]:
    module_set = set(modules)
    return {
        "focus": "focus" in joined,
        "launcher": "Launcher" in module_set or "launcher" in joined or "quickstep" in joined,
        "power": "power" in joined or "Policy" in module_set,
        "package": "package" in joined or "PackageManager" in module_set,
        "input": "input" in joined or "Input" in module_set,
        "audio": "Audio" in module_set or "audio" in joined or "microphone" in joined or "volume" in joined,
        "camera": "Camera" in module_set or "camera" in joined or "qrcode" in joined or "preview" in joined,
        "storage": "Storage" in module_set or "storage" in joined or "vold" in joined or "volume" in joined or "obb" in joined,
        "wifi": "Wifi" in module_set or "wifi" in joined or "wlan" in joined,
        "usb": "USB" in module_set or has_usb_semantic_anchor(joined),
        "product_config": "ProductConfig" in module_set or "boardconfig" in joined or "device.mk" in joined or "apps.mk" in joined,
    }


def patch_semantic_keywords(flags: dict[str, bool]) -> list[str]:
    labels = {
        "audio": "音频路由/音量",
        "camera": "相机行为",
        "storage": "存储/挂载",
        "wifi": "Wi-Fi",
        "usb": "USB/设备权限",
        "product_config": "产品配置/预置应用",
    }
    return [label for flag, label in labels.items() if flags.get(flag)]


def patch_semantic_problem_solution(modules: list[str], flags: dict[str, bool]) -> tuple[str, str, str]:
    if flags["focus"] and any(module in modules for module in ("WindowManager", "ActivityTaskManager")):
        return (
            "窗口或 Activity 焦点行为需要按产品需求调整。",
            "修改 WindowManager 或 ActivityTaskManager 相关路径中的焦点处理逻辑。",
            "medium",
        )
    if flags["power"]:
        return (
            "按键、策略或电源相关行为需要按产品需求调整。",
            "修改 Framework policy 路径中的策略处理逻辑。",
            "medium",
        )
    if flags["audio"] and flags["camera"]:
        return (
            "音频录制、麦克风或相机链路可能不符合产品权限或回退策略要求。",
            "调整 Audio/Camera 相关服务或 HAL 路径，并验证录音、拍照、扫码和权限切换场景。",
            "medium",
        )
    if flags["audio"]:
        return (
            "音频路由、音量或麦克风行为可能不符合产品要求。",
            "调整 AudioService、AudioFlinger 或音量策略相关路径，并验证音量、录音和媒体播放场景。",
            "medium",
        )
    if flags["camera"]:
        return (
            "相机预览、扫码、拍照或相机权限行为可能不符合产品要求。",
            "调整 CameraService、Camera2 或相机 HAL 相关路径，并验证目标相机场景。",
            "medium",
        )
    if flags["storage"]:
        return (
            "外部存储、挂载或应用访问存储的权限行为可能不符合产品要求。",
            "调整 vold、VolumeManager 或存储访问相关路径，并验证 U 盘、OBB 和外部存储访问场景。",
            "medium",
        )
    if flags["wifi"]:
        return (
            "Wi-Fi 服务、默认配置或连接权限行为可能不符合产品要求。",
            "调整 Wi-Fi service 或产品配置路径，并验证连接、开关和权限相关场景。",
            "medium",
        )
    if flags["usb"]:
        return (
            "USB 设备节点、权限或外设识别行为可能不符合产品要求。",
            "调整 ueventd、USB 权限或设备配置路径，并验证目标外设识别和访问权限。",
            "medium",
        )
    if flags["product_config"]:
        return (
            "产品编译配置、预置应用或板级开关可能不符合项目要求。",
            "调整 BoardConfig、device makefile 或预置应用清单，并验证编译产物和首次开机状态。",
            "medium",
        )
    if modules:
        return (
            f"{'、'.join(modules)} 相关行为需要按产品需求调整。",
            "结合需求、修改文件和验证记录复核对应逻辑。",
            "low",
        )
    return (
        "补丁对应的具体问题需要结合原始需求和会话记录确认。",
        "先阅读补丁 diff、readme 和验证记录，再决定是否复用或适配。",
        "low",
    )


def patch_semantic_risk_areas(modules: list[str], flags: dict[str, bool]) -> list[str]:
    risks = sorted(
        {
            *("窗口焦点/显示层级" for _ in [0] if flags["focus"] or "WindowManager" in modules),
            *("Activity 启动/恢复" for _ in [0] if "ActivityTaskManager" in modules),
            *("按键/电源/策略行为" for _ in [0] if flags["power"]),
            *("包安装/包状态" for _ in [0] if "PackageManager" in modules),
            *("资源覆盖/配置优先级" for _ in [0] if "FrameworkResources" in modules),
            *("音频路由/音量行为" for _ in [0] if flags["audio"]),
            *("相机行为" for _ in [0] if flags["camera"]),
            *("存储/挂载管理" for _ in [0] if flags["storage"]),
            *("Wi-Fi 服务/配置" for _ in [0] if flags["wifi"]),
            *("USB/设备权限" for _ in [0] if flags["usb"]),
            *("产品配置/预置应用" for _ in [0] if flags["product_config"]),
            *("输入分发" for _ in [0] if flags["input"]),
        }
    )
    return risks or ["修改路径需要按当前项目需求重新验证"]


def patch_symbols_from_text(text: str) -> list[str]:
    symbols: list[str] = []
    current_class = ""
    for raw in text.splitlines():
        if raw.startswith("+++ "):
            path = raw.removeprefix("+++ ").strip()
            if path.startswith("b/"):
                path = path[2:]
            current_class = Path(path).stem if path and path != "/dev/null" else ""
            continue
        if not raw.startswith("@@") or not current_class:
            continue
        match = re.match(r"^@@ .* @@\s*(.*)$", raw)
        context = match.group(1).strip() if match else ""
        methods = re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(", context)
        method = next((item for item in reversed(methods) if item not in {"if", "for", "while", "switch"}), "")
        if method:
            symbols.append(f"{current_class}.{method}")
    return sorted(set(symbols))


def patch_facts_from_text(text: str) -> dict[str, Any]:
    files = []
    for match in re.finditer(r"^diff --git a/(.+?) b/(.+)$", text, re.M):
        path = match.group(2)
        if path != "/dev/null" and path not in files:
            files.append(path)
    added = "\n".join(patch_added_lines(text))
    changed = "\n".join(patch_changed_lines(text))
    return {
        "modified_files": files,
        "symbols": patch_symbols_from_text(text),
        "system_properties": sorted(set(re.findall(r"\b(?:persist|ro|sys|debug|vendor)\.[A-Za-z0-9_.-]+", changed))),
        "settings_keys": sorted(set(re.findall(r"Settings\.(?:System|Secure|Global)\.([A-Za-z0-9_.-]+)", changed))),
        "resource_keys": resource_keys_from_patch_text(changed),
        "framework_log_keys": sorted(set(re.findall(r"FrameworkLog\.([A-Za-z0-9_]+)", changed))),
        "modules": patch_modules_from_files(files),
        "banned_log_hits": sorted(pattern for pattern in BANNED_LOG_PATTERNS if pattern in added),
        "author_date_marker_present": bool(AUTHOR_DATE_RE.search(text)),
    }


def patch_problem_and_risk_payloads(patch_id: str, source_patch: str, summary: str, facts: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    files = facts.get("modified_files") or []
    modules = facts.get("modules") or patch_modules_from_files(files)
    joined = " ".join([summary, " ".join(files), " ".join(modules)]).lower()
    flags = patch_semantic_flags(joined, modules)
    keywords = sorted(
        {
            *modules,
            *[Path(path).stem for path in files],
            *patch_semantic_keywords(flags),
            *[item for item in ["focus", "launcher", "power", "policy", "package", "input"] if item in joined],
        }
    )
    basis = [f"补丁修改文件: {path}" for path in files]
    basis.extend(f"根据路径归属到模块: {module}" for module in modules)
    basis.extend(f"根据 diff hunk 识别符号: {symbol}" for symbol in facts.get("symbols", []))
    if summary:
        basis.append("提交时提供了补丁摘要")
    if not basis:
        basis = ["补丁文件存在，但缺少可解析的 diff 路径"]

    problem, solution, confidence = patch_semantic_problem_solution(modules, flags)
    risks = patch_semantic_risk_areas(modules, flags)

    limits = [
        "补丁内容不能单独证明原始需求文字",
        "补丁内容不能单独证明设备验证结果",
        "补丁内容不能单独证明发布状态",
    ]
    problem_payload = {
        "kind": "patch_problem_summary",
        "patch_id": patch_id,
        "source_patch": source_patch,
        "confidence": confidence,
        "problem_summary": problem,
        "solution_summary": solution,
        "keywords": keywords,
        "basis": basis,
        "limits": limits,
    }
    risk_payload = {
        "kind": "risk_surface",
        "patch_id": patch_id,
        "source_patch": source_patch,
        "confidence": confidence,
        "risk_areas": risks,
        "basis": basis,
        "limits": limits,
    }
    return problem_payload, risk_payload
