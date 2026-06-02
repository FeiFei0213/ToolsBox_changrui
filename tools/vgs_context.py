from __future__ import annotations

import json
import logging
import string
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

TOOLBOX_DIR = Path.home() / ".toolbox"
SETTINGS_FILE = TOOLBOX_DIR / "settings.json"

_LEGACY_TXT_YAML_SETTINGS = TOOLBOX_DIR / "txt_yaml_settings.json"
_LEGACY_LOG_VIEWER_SETTINGS = TOOLBOX_DIR / "log_viewer_settings.json"

_SCAN_SUBPATHS = [
    "project/code/vgs",
    "projects/code/vgs",
    "code/vgs",
    "dev/vgs",
    "vgs",
    "work/vgs",
    "workspace/vgs",
]


def _load_settings() -> dict:
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_settings(settings: dict) -> None:
    try:
        TOOLBOX_DIR.mkdir(parents=True, exist_ok=True)
        SETTINGS_FILE.write_text(
            json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception as exc:
        logger.warning("save toolbox settings: %s", exc)


def is_vgs_root(path: str | Path) -> bool:
    root = Path(path)
    return root.is_dir() and (root / "config" / "device").is_dir()


def set_vgs_root(path: str | Path) -> Path:
    root = Path(path)
    settings = _load_settings()
    settings["vgs_root"] = str(root)
    _save_settings(settings)
    return root


def _legacy_vgs_root() -> Path | None:
    try:
        data = json.loads(_LEGACY_TXT_YAML_SETTINGS.read_text(encoding="utf-8"))
        root = Path(data.get("vgs_root", ""))
        if is_vgs_root(root):
            return root
    except Exception:
        pass

    try:
        data = json.loads(_LEGACY_LOG_VIEWER_SETTINGS.read_text(encoding="utf-8"))
        log_dir = Path(data.get("log_dir", ""))
        candidate = log_dir.parent if log_dir.name.lower() == "logs" else log_dir
        if is_vgs_root(candidate):
            return candidate
    except Exception:
        pass

    return None


def auto_detect_vgs_root() -> Path | None:
    drives = [Path(f"{d}:\\") for d in string.ascii_uppercase if Path(f"{d}:\\").exists()]
    for drive in drives:
        for subpath in _SCAN_SUBPATHS:
            candidate = drive / subpath
            if is_vgs_root(candidate):
                return candidate
    return None


def get_vgs_root(auto_detect: bool = True) -> Path | None:
    settings = _load_settings()
    saved = settings.get("vgs_root")
    if saved and is_vgs_root(saved):
        return Path(saved)

    legacy = _legacy_vgs_root()
    if legacy:
        set_vgs_root(legacy)
        return legacy

    if auto_detect:
        detected = auto_detect_vgs_root()
        if detected:
            set_vgs_root(detected)
            return detected

    return None


def get_vgs_logs_dir(auto_detect: bool = True) -> Path | None:
    settings = _load_settings()
    saved = settings.get("vgs_logs_dir")
    if saved and Path(saved).is_dir():
        return Path(saved)

    try:
        data = json.loads(_LEGACY_LOG_VIEWER_SETTINGS.read_text(encoding="utf-8"))
        log_dir = Path(data.get("log_dir", ""))
        if log_dir.is_dir():
            return log_dir
    except Exception:
        pass

    root = get_vgs_root(auto_detect=auto_detect)
    if not root:
        return None
    return root / "logs"


def set_vgs_logs_dir(path: str | Path) -> Path:
    log_dir = Path(path)
    if log_dir.name.lower() == "logs" and is_vgs_root(log_dir.parent):
        set_vgs_root(log_dir.parent)

    settings = _load_settings()
    settings["vgs_logs_dir"] = str(log_dir)
    _save_settings(settings)
    return log_dir


def resolve_vgs_relative_path(path: str | Path) -> Path | None:
    raw = str(path).replace("\\\\", "\\").replace("/", "\\")
    candidate = Path(raw)
    if candidate.is_absolute():
        return candidate
    if raw.startswith(".\\"):
        raw = raw[2:]
    root = get_vgs_root(auto_detect=True)
    return root / raw if root else None


def packaged_resource_path(*parts: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base.joinpath(*parts)
