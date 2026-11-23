"""Find a local Ansys Electronics Desktop install without launching it."""

import os
import string
import sys
from pathlib import Path


class Install(object):
    def __init__(self, win64, version):
        self.win64 = Path(win64)
        self.version = version
        self.version_code = version_code(version)
        self.executable = _executable(self.win64)

    def as_dict(self):
        return {
            "version": self.version,
            "version_code": self.version_code,
            "win64": str(self.win64),
            "executable": str(self.executable) if self.executable else None,
            "env": "ANSYSEM_ROOT%s" % self.version_code,
        }


def version_code(version):
    year, release = str(version).split(".", 1)
    return "%02d%s" % (int(year) % 100, release)


def version_from_code(code):
    return "20%s.%s" % (code[:2], code[2:])


def version_from_folder(name):
    if name.lower().startswith("v") and name[1:].isdigit() and len(name) >= 4:
        return version_from_code(name[1:])
    return None


def _executable(win64):
    for name in ("ansysedt.exe", "ansysedt"):
        path = Path(win64) / name
        if path.is_file():
            return path
    return None


def normalize_root(path):
    path = Path(path).expanduser()
    if _executable(path):
        return path.resolve(), _version_near(path)
    for sub in ("Win64", "Linux64"):
        candidate = path / sub
        if _executable(candidate):
            return candidate.resolve(), _version_near(candidate)
    raise FileNotFoundError("AEDT executable not found under %s" % path)


def _version_near(win64):
    code = win64.parent.name
    if code.lower().startswith("v"):
        parsed = version_from_folder(code)
        if parsed:
            return parsed
    env_code = os.environ.get("ANSYSEM_ROOT")
    return "2024.2"


def runs_dir(spec=None):
    if spec and spec.get("run_root"):
        return Path(spec["run_root"])
    env = os.environ.get("HFSS_AEDT_RUNS")
    if env:
        return Path(env)
    return Path.cwd() / "runs"


def candidate_win64():
    found = []
    prefixes = []
    if os.name == "nt":
        for letter in string.ascii_uppercase:
            drive = Path("%s:\\" % letter)
            if drive.exists():
                prefixes.append(drive / "Program Files")
    else:
        prefixes.extend([Path("/opt"), Path("/usr/local"), Path.home()])
    for prefix in prefixes:
        for base in (prefix / "AnsysEM", prefix / "ANSYS Inc"):
            if not base.is_dir():
                continue
            for version_dir in base.glob("v*"):
                for sub in ("Win64", "Linux64"):
                    folder = version_dir / sub
                    if _executable(folder):
                        found.append(folder)
                nested = version_dir / "AnsysEM"
                if nested.is_dir():
                    for sub in ("Win64", "Linux64"):
                        folder = nested / sub
                        if _executable(folder):
                            found.append(folder)
    return found


def _install_from_env():
    """Honor AEDT_ROOT, ANSYSEM_ROOT, and ANSYSEM_ROOT242-style variables."""
    override = os.environ.get("AEDT_ROOT") or os.environ.get("ANSYSEM_ROOT")
    if override:
        win64, version = normalize_root(override)
        return Install(win64, version)
    matches = []
    for key, value in sorted(os.environ.items()):
        if not key.startswith("ANSYSEM_ROOT") or key == "ANSYSEM_ROOT" or not value:
            continue
        try:
            win64, version = normalize_root(value)
        except FileNotFoundError:
            continue
        code = key[len("ANSYSEM_ROOT"):]
        if code.isdigit() and len(code) >= 3:
            version = version_from_code(code)
        matches.append(Install(win64, version))
    if not matches:
        return None
    matches.sort(key=lambda item: item.version, reverse=True)
    return matches[0]


def find_install(preferred_version=None):
    installed = _install_from_env()
    if installed is not None and (preferred_version is None or installed.version == preferred_version):
        return installed
    matches = []
    for folder in candidate_win64():
        version = version_from_folder(folder.parent.name)
        if version is None:
            continue
        matches.append(Install(folder.resolve(), version))
    if preferred_version:
        for install in matches:
            if install.version == preferred_version:
                return install
    if not matches:
        raise FileNotFoundError(
            "Ansys Electronics Desktop was not found. Set AEDT_ROOT to the Win64 "
            "directory that contains ansysedt.exe."
        )
    matches.sort(key=lambda item: item.version, reverse=True)
    return matches[0]


def license_server_error():
    """Return an error when ANSYSLMD_LICENSE_FILE points at a closed port."""
    import socket

    raw = os.environ.get("ANSYSLMD_LICENSE_FILE", "")
    targets = []
    for part in raw.split(";"):
        part = part.strip()
        if "@" not in part:
            continue
        port, host = part.split("@", 1)
        if port.isdigit() and host:
            targets.append((host, int(port)))
    if not targets:
        return None
    problems = []
    for host, port in targets:
        try:
            with socket.create_connection((host, port), timeout=2):
                return None
        except OSError as exc:
            problems.append("%s@%s (%s)" % (port, host, exc))
    return (
        "Cannot reach the Ansys license server: %s. Start the ANSYS License Manager "
        "before running HFSS. Opening the HFSS window does not replace that service."
        % "; ".join(problems)
    )


def apply_environment(install):
    os.environ["ANSYSEM_ROOT%s" % install.version_code] = str(install.win64)


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
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
