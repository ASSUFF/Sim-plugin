"""Look at a run folder before a solver is started.

The check does not launch COMSOL, HFSS, or FDTD. A note here is a warning.
HFSS already moves a non-ASCII project path to a temporary ASCII folder.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def inspect_path(path: str | Path) -> dict:
    text = str(path)
    notes: list[str] = []
    non_ascii = any(ord(ch) > 127 for ch in text)
    if non_ascii:
        notes.append(
            "运行目录含非 ASCII 字符。HFSS 会改到临时 ASCII 目录求解再拷回。COMSOL 和 FDTD 直接使用这个目录。"
        )
    onedrive = _under_onedrive(text)
    if onedrive:
        notes.append(
            "运行目录在 OneDrive 里。同步锁会让求解器保存失败。下一步：把 run_root 指到本机磁盘上不参与同步的目录。"
        )
    network = _on_network(text)
    if network:
        notes.append("运行目录在网络盘上。下一步：把 run_root 改到本机磁盘。")
    temp_dir = Path(tempfile.gettempdir())
    writable = _can_write(temp_dir)
    if not writable:
        notes.append("临时目录不可写：%s。HFSS 的 ASCII 中转依赖它。" % temp_dir)
    return {
        "path": text,
        "non_ascii": non_ascii,
        "onedrive": onedrive,
        "network": network,
        "temp_dir": str(temp_dir),
        "temp_writable": writable,
        "notes": notes,
    }


def attach(payload: dict, path: str | Path) -> dict:
    report = inspect_path(path)
    payload["path_check"] = report
    if report["notes"]:
        warnings = list(payload.get("warnings") or [])
        warnings.extend(report["notes"])
        payload["warnings"] = warnings
    return payload


def _under_onedrive(text: str) -> bool:
    folded = text.replace("/", "\\").lower()
    if "\\onedrive" in folded or folded.startswith("onedrive"):
        return True
    for key, value in os.environ.items():
        if not value or not key.lower().startswith("onedrive"):
            continue
        root = str(Path(value)).replace("/", "\\").lower().rstrip("\\")
        if root and (folded == root or folded.startswith(root + "\\")):
            return True
    return False


def _on_network(text: str) -> bool:
    if text.startswith("\\\\") or text.startswith("//"):
        return True
    if os.name != "nt" or len(text) < 2 or text[1] != ":":
        return False
    try:
        import ctypes

        kind = ctypes.windll.kernel32.GetDriveTypeW(text[:2] + "\\")
    except Exception:
        return False
    return kind == 4


def _can_write(folder: Path) -> bool:
    try:
        folder.mkdir(parents=True, exist_ok=True)
        probe = folder / ".sim_plugin_pathcheck"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError:
        return False
    return True
