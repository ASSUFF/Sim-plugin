"""MCP server. The model calls these tools; this process does not call a model."""

import json
import os
import subprocess
import sys
from pathlib import Path

from lumerical_fdtd.discover import find_install, runs_dir
from lumerical_fdtd.study import prepare_spec
from lumerical_fdtd.validate import validate_spec

try:
    from mcp.server.mcpserver import MCPServer as Server
except ImportError:  # mcp 1.x
    from mcp.server.fastmcp import FastMCP as Server

ENGINE = Path(__file__).resolve().with_name("engine.py")
mcp = Server("lumerical-fdtd")


def _interpreter():
    install = find_install()
    if install.python is not None:
        return install.python
    return Path(sys.executable)


def call_engine(args):
    try:
        program = _interpreter()
    except FileNotFoundError as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)
    env = os.environ.copy()
    src = str(Path(__file__).resolve().parents[1])
    env["PYTHONPATH"] = src + os.pathsep + env.get("PYTHONPATH", "")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    proc = subprocess.run(
        [str(program), str(ENGINE), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    stdout = proc.stdout or ""
    marker = "FDTD_RESULT "
    index = stdout.rfind(marker)
    stderr = (proc.stderr or "")[-4000:]
    if index < 0:
        return json.dumps(
            {
                "ok": False,
                "returncode": proc.returncode,
                "stdout": stdout[-4000:],
                "stderr": stderr,
            },
            ensure_ascii=False,
        )
    line = stdout[index + len(marker) :].strip().splitlines()[0]
    if proc.returncode == 0:
        return line
    try:
        body = json.loads(line)
    except json.JSONDecodeError:
        body = {"raw": line}
    body["returncode"] = proc.returncode
    if stderr:
        body["stderr"] = stderr
    return json.dumps(body, ensure_ascii=False)


@mcp.tool()
def fdtd_doctor() -> str:
    """Report the discovered Lumerical install, interpreter, and runs directory. Does not launch the solver."""
    try:
        install = find_install()
    except FileNotFoundError as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)
    payload = install.as_dict()
    payload["ok"] = True
    payload["runs_dir"] = str(runs_dir())
    payload["interpreter"] = str(install.python or Path(sys.executable))
    return json.dumps(payload, ensure_ascii=False)


@mcp.tool()
def fdtd_validate(spec_json: str) -> str:
    """Validate a simulation spec without a Lumerical license. Units are metres and seconds."""
    try:
        spec = json.loads(spec_json)
    except json.JSONDecodeError as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)
    errors, warnings = validate_spec(spec)
    return json.dumps({"ok": not errors, "errors": errors, "warnings": warnings}, ensure_ascii=False)


@mcp.tool()
def fdtd_inspect(project_path: str) -> str:
    """Open a Lumerical .fsp, list objects and solver settings, then close without running."""
    return call_engine(["inspect", "--project", project_path])


@mcp.tool()
def fdtd_run(spec_json: str) -> str:
    """Run local Lumerical FDTD from a JSON spec and return monitor results.

    Units are metres and seconds. The GUI stays hidden unless hide_gui is false.
    A source .fsp is copied into the runs directory and is not overwritten.
    Results are saved before they are read back. transmission exports pass only
    the monitor name; with several sources the value is the fraction of total
    source power through that monitor.
    """
    try:
        spec = json.loads(spec_json)
    except json.JSONDecodeError as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)
    errors, warnings = validate_spec(spec)
    if errors:
        return json.dumps({"ok": False, "errors": errors, "warnings": warnings}, ensure_ascii=False)
    script_file = spec.get("script_file")
    if script_file:
        script_path = Path(script_file)
        if not script_path.is_file():
            return json.dumps(
                {
                    "ok": False,
                    "error": "script_file must be an existing file. Use an absolute path when calling fdtd_run.",
                },
                ensure_ascii=False,
            )
        spec["script_file"] = str(script_path.resolve())
        spec_json = json.dumps(spec)
    inbox = runs_dir(spec) / "_inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    spec_path = inbox / "spec.json"
    spec_path.write_text(spec_json, encoding="utf-8")
    return call_engine(["run", "--spec", str(spec_path)])


@mcp.tool()
def fdtd_prepare(spec_json: str) -> str:
    """Fill missing FDTD settings with documented assumptions. Does not run the solver."""
    try:
        spec = json.loads(spec_json)
    except json.JSONDecodeError as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)
    completed, assumptions = prepare_spec(spec)
    errors, warnings = validate_spec(completed)
    return json.dumps(
        {"ok": not errors, "spec": completed, "assumptions": assumptions, "errors": errors, "warnings": warnings},
        ensure_ascii=False,
    )


@mcp.tool()
def fdtd_sweep(study_json: str) -> str:
    """Run 2 to 8 values of one object property and return the value with the best monitor score."""
    try:
        study = json.loads(study_json)
    except json.JSONDecodeError as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)
    inbox = runs_dir(study.get("base")) / "_inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    spec_path = inbox / "study.json"
    spec_path.write_text(json.dumps(study), encoding="utf-8")
    return call_engine(["study", "--spec", str(spec_path)])


def main():
    mcp.run()


if __name__ == "__main__":
    main()
