"""Find a local Ansys Lumerical install without importing lumapi."""

import os
import string
import sys
from pathlib import Path


class Install(object):
    def __init__(self, root, python_path):
        self.root = Path(root)
        self.api_dir = self.root / "api" / "python"
        self.lumapi = self.api_dir / "lumapi.py"
        self.bin_dir = self.root / "bin"
        self.python = Path(python_path) if python_path else None

    def solver_path(self):
        for name in ("fdtd-solutions.exe", "fdtd-solutions"):
            candidate = self.bin_dir / name
            if candidate.is_file():
                return candidate
        return None

    def as_dict(self):
        solver = self.solver_path()
        return {
            "root": str(self.root),
            "api_dir": str(self.api_dir),
            "bin_dir": str(self.bin_dir),
            "lumapi": str(self.lumapi),
            "python": str(self.python) if self.python else None,
            "solver": str(solver) if solver else None,
        }


def runs_dir(spec=None):
    if spec and spec.get("run_root"):
        return Path(spec["run_root"])
    env = os.environ.get("LUMERICAL_FDTD_RUNS")
    if env:
        return Path(env)
    return Path.cwd() / "runs"


def _has_lumapi(root):
    return (Path(root) / "api" / "python" / "lumapi.py").is_file()


def normalize_root(path):
    path = Path(path).expanduser()
    if _has_lumapi(path):
        return path.resolve()
    if path.name.lower() == "bin" and _has_lumapi(path.parent):
        return path.parent.resolve()
    return path.resolve()


def find_python(root):
    override = os.environ.get("LUMERICAL_PYTHON")
    if override:
        path = Path(override).expanduser()
        if path.is_file():
            return path
        raise FileNotFoundError("LUMERICAL_PYTHON is not a file: %s" % path)
    patterns = (
        "python-*-embed-amd64/python.exe",
        "python-*-embed-*/python.exe",
        "python-*-embed-amd64/python",
        "python*/python.exe",
        "python*/bin/python",
        "bin/python.exe",
        "bin/python3",
        "bin/python",
    )
    found = []
    for pattern in patterns:
        found.extend(root.glob(pattern))
    files = [path for path in found if path.is_file()]
    if not files:
        return None
    files.sort(key=lambda path: (0 if "embed" in path.as_posix() else 1, str(path)))
    return files[0]


def _version_dirs(base):
    if not base.is_dir():
        return []
    versions = [path for path in base.glob("v*") if path.is_dir()]
    versions.sort(key=lambda path: path.name, reverse=True)
    return versions


def candidate_roots():
    roots = []
    if os.name == "nt":
        for letter in string.ascii_uppercase:
            drive = Path("%s:\\" % letter)
            if not drive.exists():
                continue
            program = drive / "Program Files"
            roots.extend(_version_dirs(program / "Lumerical"))
            roots.extend(_version_dirs(program / "ANSYS Inc" / "Lumerical"))
            roots.append(program / "Lumerical")
    else:
        for base in (Path("/opt/lumerical"), Path("/usr/local/lumerical"), Path.home() / "lumerical"):
            roots.extend(_version_dirs(base))
            roots.append(base)
    return roots


def find_install():
    override = os.environ.get("LUMERICAL_ROOT")
    if override:
        root = normalize_root(override)
        if not _has_lumapi(root):
            raise FileNotFoundError(
                "LUMERICAL_ROOT does not contain api/python/lumapi.py: %s" % root
            )
        return Install(root, find_python(root))
    seen = set()
    for candidate in candidate_roots():
        root = normalize_root(candidate)
        key = str(root).lower()
        if key in seen:
            continue
        seen.add(key)
        if _has_lumapi(root):
            return Install(root, find_python(root))
    raise FileNotFoundError(
        "Ansys Lumerical was not found. Set LUMERICAL_ROOT to the version "
        "directory that contains api/python/lumapi.py."
    )


def main(argv=None):
    import json

    try:
        install = find_install()
    except FileNotFoundError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1
    payload = install.as_dict()
    payload["ok"] = True
    payload["runs_dir"] = str(runs_dir())
    payload["interpreter"] = str(install.python or Path(sys.executable))
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
