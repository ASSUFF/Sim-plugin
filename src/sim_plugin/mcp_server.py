"""MCP entry for Cursor, Codex, Claude, and DeepSeek Harness."""

from __future__ import annotations

import json

from comsol_plugin.advise import advise
from comsol_plugin.batch import run_java
from comsol_plugin.discover import doctor
from comsol_plugin.search import search_features
from comsol_plugin.project import inspect_mph, set_mph
from comsol_plugin.study import run_optimize, run_sweep
from comsol_plugin.validate import validate_job
from hfss_plugin.backend import doctor as hfss_doctor_payload
from hfss_plugin.backend import prepare as hfss_prepare_payload
from hfss_plugin.backend import inspect as hfss_inspect_payload
from hfss_plugin.backend import run as hfss_run_payload
from hfss_plugin.backend import set_project as hfss_set_payload
from hfss_plugin.advise import advise as hfss_advise_payload
from hfss_plugin.backend import sweep as hfss_sweep_payload
from hfss_plugin.backend import validate as hfss_validate_payload
from hfss_plugin.optimize import optimize as hfss_optimize_payload
from fdtd_plugin.advise import advise as fdtd_advise_payload
from fdtd_plugin.backend import doctor as fdtd_doctor_payload
from fdtd_plugin.backend import prepare as fdtd_prepare_payload
from fdtd_plugin.backend import inspect as fdtd_inspect_payload
from fdtd_plugin.backend import run as fdtd_run_payload
from fdtd_plugin.backend import set_project as fdtd_set_payload
from fdtd_plugin.backend import sweep as fdtd_sweep_payload
from fdtd_plugin.backend import validate as fdtd_validate_payload
from fdtd_plugin.optimize import optimize as fdtd_optimize_payload
from sim_plugin.confirm import confirm as confirm_spec

try:
    from mcp.server.mcpserver import MCPServer as Server
except ImportError:
    from mcp.server.fastmcp import FastMCP as Server

mcp = Server("sim-plugin")


def _json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)


@mcp.tool()
def comsol_doctor() -> str:
    """Report the local COMSOL install. Does not launch COMSOL."""
    return _json(doctor())


@mcp.tool()
def comsol_search(keyword: str, limit: int = 20) -> str:
    """Find Java create() type names in the local COMSOL completion files."""
    return _json(search_features(keyword, limit=limit))


@mcp.tool()
def comsol_validate(java: str, spec: str = "") -> str:
    """Check a COMSOL Java model and optional JSON spec without compiling."""
    return _json(validate_job(java, spec or None))


@mcp.tool()
def comsol_inspect(project: str) -> str:
    """List parameters in an existing .mph file. Opens COMSOL but does not solve."""
    return _json(inspect_mph(project))


@mcp.tool()
def comsol_set(project: str, spec_json: str) -> str:
    """Change parameters in a copy of an existing .mph. Does not solve."""
    spec = _load_object(spec_json)
    if spec.get("ok") is False:
        return _json(spec)
    return _json(set_mph(project, spec.get("parameters") or {}, study=spec.get("study"), solve=False))


@mcp.tool()
def comsol_run(java: str, spec: str = "", stoptime: int = 600) -> str:
    """Compile and batch-run a COMSOL Java model. This launches COMSOL."""
    return _json(run_java(java, spec or None, stoptime_s=stoptime, check_confirmation=True))


@mcp.tool()
def comsol_confirm(spec_json: str) -> str:
    """Check a COMSOL checklist and return the spec run accepts. Does not launch COMSOL."""
    spec = _load_object(spec_json)
    if spec.get("ok") is False and "confirmation" not in spec:
        return _json(spec)
    return _json(confirm_spec(spec))


@mcp.tool()
def comsol_sweep(java: str, spec: str, stoptime: int = 600) -> str:
    """Run every combination in spec.sweep, at most 8 COMSOL solves."""
    return _json(run_sweep(java, spec, stoptime_s=stoptime))


@mcp.tool()
def comsol_optimize(java: str, spec: str, stoptime: int = 600) -> str:
    """Coarse-to-fine search of one parameter, at most 8 COMSOL solves."""
    return _json(run_optimize(java, spec, stoptime_s=stoptime))


@mcp.tool()
def comsol_advise(report: str) -> str:
    """List facts from a run report. Does not launch COMSOL or write the advice."""
    return _json(advise(report))


@mcp.tool()
def hfss_doctor() -> str:
    """Report the local HFSS install. Does not launch Electronics Desktop."""
    return _json(hfss_doctor_payload())


@mcp.tool()
def hfss_validate(spec_json: str) -> str:
    """Validate an HFSS JSON spec. Lengths are metres and frequency is hertz."""
    try:
        spec = json.loads(spec_json)
    except json.JSONDecodeError as exc:
        return _json({"ok": False, "launched_solver": False, "error": str(exc)})
    return _json(hfss_validate_payload(spec))


@mcp.tool()
def hfss_prepare(spec_json: str) -> str:
    """Fill missing HFSS settings and list assumptions. Does not launch HFSS."""
    try:
        spec = json.loads(spec_json)
    except json.JSONDecodeError as exc:
        return _json({"ok": False, "launched_solver": False, "error": str(exc)})
    return _json(hfss_prepare_payload(spec))


@mcp.tool()
def hfss_inspect(project: str) -> str:
    """List objects and setups in a copy of an existing .aedt. Does not solve."""
    return _json(hfss_inspect_payload(project))


@mcp.tool()
def hfss_set(project: str, spec_json: str) -> str:
    """Write variables into a copy of an existing .aedt. Does not solve."""
    spec = _load_object(spec_json)
    if spec.get("ok") is False:
        return _json(spec)
    spec["project"] = project
    return _json(hfss_set_payload(spec))


@mcp.tool()
def hfss_run(spec_json: str) -> str:
    """Solve an HFSS spec. This launches Electronics Desktop in the background."""
    try:
        spec = json.loads(spec_json)
    except json.JSONDecodeError as exc:
        return _json({"ok": False, "launched_solver": False, "error": str(exc)})
    return _json(hfss_run_payload(spec))


@mcp.tool()
def hfss_sweep(study_json: str) -> str:
    """Compare 2 to 8 values of one HFSS parameter. Each value launches HFSS."""
    try:
        study = json.loads(study_json)
    except json.JSONDecodeError as exc:
        return _json({"ok": False, "launched_solver": False, "error": str(exc)})
    return _json(hfss_sweep_payload(study))


@mcp.tool()
def hfss_optimize(study_json: str) -> str:
    """Coarse-to-fine search of one HFSS parameter, at most 8 solves."""
    try:
        study = json.loads(study_json)
    except json.JSONDecodeError as exc:
        return _json({"ok": False, "launched_solver": False, "error": str(exc)})
    return _json(hfss_optimize_payload(study))


@mcp.tool()
def hfss_advise(report: str) -> str:
    """List S-parameter facts from an HFSS report. Does not launch HFSS."""
    return _json(hfss_advise_payload(report))


@mcp.tool()
def hfss_confirm(spec_json: str) -> str:
    """Check an HFSS checklist and return the spec run accepts. Does not launch HFSS."""
    spec = _load_object(spec_json)
    if spec.get("ok") is False and "confirmation" not in spec:
        return _json(spec)
    return _json(confirm_spec(spec))


def _load_object(text: str) -> dict:
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        return {"ok": False, "launched_solver": False, "solved": False, "error": str(exc)}
    if not isinstance(value, dict):
        return {"ok": False, "launched_solver": False, "solved": False, "error": "规格的顶层需要是 JSON 对象。"}
    return value


def _load(text: str) -> dict | None:
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        return {"ok": False, "launched_solver": False, "error": str(exc)}
    if not isinstance(value, dict):
        return {"ok": False, "launched_solver": False, "error": "规格的顶层需要是 JSON 对象。"}
    return value


@mcp.tool()
def fdtd_doctor() -> str:
    """Report whether local Lumerical FDTD was found. Does not launch it."""
    return _json(fdtd_doctor_payload())


@mcp.tool()
def fdtd_validate(spec_json: str) -> str:
    """Validate an FDTD spec. Lengths are metres and times are seconds."""
    spec = _load(spec_json)
    if spec.get("error") and spec.get("ok") is False and "stage" not in spec and "errors" not in spec and "spec" not in spec:
        return _json(spec)
    return _json(fdtd_validate_payload(spec))


@mcp.tool()
def fdtd_prepare(spec_json: str) -> str:
    """Fill missing FDTD settings and list assumptions. Does not launch the solver."""
    spec = _load(spec_json)
    if spec.get("ok") is False and "error" in spec and "errors" not in spec:
        return _json(spec)
    return _json(fdtd_prepare_payload(spec))


@mcp.tool()
def fdtd_inspect(project: str) -> str:
    """List objects in a copy of an existing .fsp. Does not solve."""
    return _json(fdtd_inspect_payload(project))


@mcp.tool()
def fdtd_set(project: str, spec_json: str) -> str:
    """Apply overrides to a copy of an existing .fsp. Does not solve."""
    spec = _load_object(spec_json)
    if spec.get("ok") is False:
        return _json(spec)
    spec["project"] = project
    return _json(fdtd_set_payload(spec))


@mcp.tool()
def fdtd_run(spec_json: str) -> str:
    """Run an FDTD spec when Lumerical is installed. Returns an install error otherwise."""
    spec = _load(spec_json)
    if spec.get("ok") is False and "error" in spec and "errors" not in spec:
        return _json(spec)
    return _json(fdtd_run_payload(spec))


@mcp.tool()
def fdtd_sweep(study_json: str) -> str:
    """Compare 2 to 8 values of one FDTD object property."""
    study = _load(study_json)
    if study.get("ok") is False and "error" in study and "errors" not in study:
        return _json(study)
    return _json(fdtd_sweep_payload(study))


@mcp.tool()
def fdtd_optimize(study_json: str) -> str:
    """Coarse-to-fine search of one FDTD object property, at most 8 solves."""
    study = _load(study_json)
    if study.get("ok") is False and "error" in study and "errors" not in study:
        return _json(study)
    return _json(fdtd_optimize_payload(study))


@mcp.tool()
def fdtd_advise(report: str) -> str:
    """List monitor facts from an FDTD report. Does not launch the solver."""
    return _json(fdtd_advise_payload(report))


@mcp.tool()
def fdtd_confirm(spec_json: str) -> str:
    """Check an FDTD checklist and return the spec run accepts. Does not launch Lumerical."""
    spec = _load(spec_json)
    if spec.get("ok") is False and "confirmation" not in spec and "errors" not in spec:
        return _json(spec)
    return _json(confirm_spec(spec))


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
