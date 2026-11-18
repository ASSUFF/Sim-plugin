"""Find a local COMSOL install without starting it.

Path layout checks follow the same places documented by COMSOL Codex MCP
(https://github.com/XiaoSe532/comsol-codex-mcp, MIT). Registry lookup is added
so an install outside Program Files, such as S:\\COMSOL, is found.
"""

from __future__ import annotations

import os
import re
from pathlib import Path


def doctor() -> dict:
    install = find_install()
    payload = install.as_dict()
    payload["launched_solver"] = False
    if not install.ok:
        payload["error"] = "没有找到 COMSOL。可设置环境变量 COMSOL_HOME 指向 Multiphysics 目录。"
    return payload


def find_install(root: Path | str | None = None) -> "ComsolInstall":
    if root is not None:
        found = _bind(Path(root), "argument")
        return found or ComsolInstall.missing("argument")

    for source, candidate in _candidate_roots():
        found = _bind(candidate, source)
        if found is not None:
            return found
    return ComsolInstall.missing("not-found")


class ComsolInstall:
    def __init__(
        self,
        root: Path | None,
        version: str | None,
        comsol: Path | None,
        comsolbatch: Path | None,
        comsolcompile: Path | None,
        completion_dir: Path | None,
        source: str,
    ) -> None:
        self.root = root
        self.version = version
        self.comsol = comsol
        self.comsolbatch = comsolbatch
        self.comsolcompile = comsolcompile
        self.completion_dir = completion_dir
        self.source = source

    @classmethod
    def missing(cls, source: str) -> "ComsolInstall":
        return cls(None, None, None, None, None, None, source)

    @property
    def ok(self) -> bool:
        return self.comsolbatch is not None and self.comsolcompile is not None

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "software": "COMSOL Multiphysics",
            "version": self.version,
            "root": _text(self.root),
            "comsol": _text(self.comsol),
            "comsolbatch": _text(self.comsolbatch),
            "comsolcompile": _text(self.comsolcompile),
            "completion_dir": _text(self.completion_dir),
            "source": self.source,
        }


def _candidate_roots() -> list[tuple[str, Path]]:
    roots: list[tuple[str, Path]] = []
    for name in ("COMSOL_HOME", "COMSOL_ROOT"):
        value = os.environ.get(name)
        if value:
            roots.append((name, Path(value)))
    roots.extend(_registry_roots())
    if os.name == "nt":
        roots.extend(
            [
                ("default-path", Path(r"C:\Program Files\COMSOL")),
                ("default-path", Path(r"E:\Program Files\COMSOL")),
                ("default-path", Path(r"S:\COMSOL")),
            ]
        )
    else:
        roots.extend(
            [
                ("default-path", Path("/usr/local/comsol")),
                ("default-path", Path("/opt/comsol")),
            ]
        )
    return roots


def _registry_roots() -> list[tuple[str, Path]]:
    if os.name != "nt":
        return []
    import winreg

    found: list[tuple[str, Path]] = []
    keys = (
        r"SOFTWARE\COMSOL\COMSOL64",
        r"SOFTWARE\WOW6432Node\COMSOL\COMSOL64",
    )
    for key_path in keys:
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
                value, _ = winreg.QueryValueEx(key, "COMSOLROOT")
        except OSError:
            continue
        found.append(("registry", Path(str(value))))
    return found


def _bind(root: Path, source: str) -> ComsolInstall | None:
    if not root.exists():
        return None
    bases = [root]
    if (root / "Multiphysics").is_dir():
        bases.append(root / "Multiphysics")
    versioned = sorted(root.glob("COMSOL*"), reverse=True)
    for child in versioned:
        if (child / "Multiphysics").is_dir():
            bases.append(child / "Multiphysics")
        bases.append(child)
    seen: set[Path] = set()
    for base in bases:
        try:
            base = base.resolve()
        except OSError:
            continue
        if base in seen:
            continue
        seen.add(base)
        batch = _exe(base, "comsolbatch")
        compile_exe = _exe(base, "comsolcompile")
        gui = _exe(base, "comsol")
        if batch is None and compile_exe is None:
            continue
        completion = base / "data" / "completion"
        return ComsolInstall(
            root=base,
            version=_read_version(base),
            comsol=gui,
            comsolbatch=batch,
            comsolcompile=compile_exe,
            completion_dir=completion if completion.is_dir() else None,
            source=source,
        )
    return None


def _exe(base: Path, name: str) -> Path | None:
    file_name = f"{name}.exe" if os.name == "nt" else name
    for relative in (
        Path("bin") / "win64" / file_name,
        Path("bin") / "glnxa64" / file_name,
        Path(file_name),
    ):
        candidate = base / relative
        if candidate.is_file():
            return candidate
    return None


def _read_version(base: Path) -> str | None:
    about = base / "about.txt"
    if not about.is_file():
        return None
    head = about.read_text(encoding="utf-8", errors="replace")[:4000]
    match = re.search(r"COMSOL\s+(\d+(?:\.\d+)*)", head)
    return match.group(1) if match else None


def _text(path: Path | None) -> str | None:
    return str(path) if path is not None else None
