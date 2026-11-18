"""Open an existing COMSOL .mph, list or change its parameters, and optionally solve.

The original file is only loaded. A changed model is saved under comsol/runs.
"""

from __future__ import annotations

import re
from pathlib import Path

from comsol_plugin.batch import run_java

_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def inspect_mph(project: str | Path, *, runner=None, runs_root: str | Path | None = None) -> dict:
    path = _mph_file(project)
    if isinstance(path, dict):
        return path
    java = _write_java(path, {}, study=None, solve=False, runs_root=runs_root)
    result = _batch(java, runner=runner, runs_root=runs_root)
    return _shape(result, solved=False)


def set_mph(
    project: str | Path,
    parameters: dict | None = None,
    *,
    study: str | None = None,
    solve: bool = False,
    runner=None,
    runs_root: str | Path | None = None,
) -> dict:
    path = _mph_file(project)
    if isinstance(path, dict):
        return path
    values = _parameter_values(parameters or {})
    if isinstance(values, dict) and values.get("ok") is False:
        return values
    if solve and (not isinstance(study, str) or not _NAME.match(study)):
        return {
            "ok": False,
            "launched_solver": False,
            "solved": False,
            "stage": "spec",
            "error": "求解已有工程需要 spec.study，值为 COMSOL 的研究标签，例如 std1。",
        }
    java = _write_java(path, values, study=study, solve=solve, runs_root=runs_root)
    result = _batch(java, runner=runner, runs_root=runs_root)
    return _shape(result, solved=solve)


def _mph_file(project: str | Path) -> Path | dict:
    path = Path(project)
    if not path.is_file():
        return {"ok": False, "launched_solver": False, "solved": False, "error": f"找不到工程：{path}"}
    if path.suffix.lower() != ".mph":
        return {"ok": False, "launched_solver": False, "solved": False, "error": "COMSOL 已有工程需要是 .mph 文件。"}
    return path.resolve()


def _parameter_values(parameters: dict) -> dict:
    if not isinstance(parameters, dict):
        return {"ok": False, "launched_solver": False, "solved": False, "stage": "spec", "error": "parameters 需要是对象。"}
    values: dict[str, str] = {}
    for name, raw in parameters.items():
        if not isinstance(name, str) or not _NAME.match(name):
            return {
                "ok": False,
                "launched_solver": False,
                "solved": False,
                "stage": "spec",
                "error": f"参数名 {name} 需要是 COMSOL 标识符。",
            }
        if isinstance(raw, dict):
            raw = raw.get("value")
        if not isinstance(raw, str) or not raw.strip() or '"' in raw:
            return {
                "ok": False,
                "launched_solver": False,
                "solved": False,
                "stage": "spec",
                "error": f"参数 {name} 的值需要是不含双引号的字符串，例如 2[mm]。",
            }
        values[name] = raw.strip()
    return values


def _runs(runs_root) -> Path:
    if runs_root is not None:
        return Path(runs_root)
    return Path(__file__).resolve().parents[2] / "runs"


def _write_java(project: Path, parameters: dict[str, str], *, study: str | None, solve: bool, runs_root) -> Path:
    folder = _runs(runs_root) / "_java"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "ExistingMph.java"
    path.write_text(_source(project, parameters, study, solve), encoding="utf-8")
    return path


def _source(project: Path, parameters: dict[str, str], study: str | None, solve: bool) -> str:
    loaded = _java_string(project.as_posix())
    sets = "\n".join(f'            model.param().set("{name}", "{value}");' for name, value in parameters.items())
    solve_lines = ""
    if solve and study:
        solve_lines = f'\n            model.study("{study}").run();'
    return f"""import com.comsol.model.*;
import com.comsol.model.util.ModelUtil;

public class ExistingMph {{
    public static void main(String[] args) {{
        ModelUtil.initStandalone(false);
        try {{
            Model model = ModelUtil.load("{loaded}");
{sets}{solve_lines}
            System.out.println("===RESULT===");
            for (String name : model.param().varnames()) {{
                System.out.println("param." + name + "=" + model.param().get(name));
            }}
            for (String tag : model.study().tags()) {{
                System.out.println("study." + tag + "=" + model.study(tag).label());
            }}
            model.save("ExistingMph.mph");
        }} catch (Exception e) {{
            System.err.println("FATAL: " + e.getMessage());
            e.printStackTrace();
            System.exit(1);
        }} finally {{
            ModelUtil.disconnect();
        }}
    }}
}}
"""


def _java_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _batch(java: Path, *, runner, runs_root) -> dict:
    kwargs = {}
    if runner is not None:
        kwargs["runner"] = runner
    if runs_root is not None:
        kwargs["runs_root"] = runs_root
    return run_java(java, **kwargs)


def _shape(result: dict, *, solved: bool) -> dict:
    body = dict(result)
    body["solved"] = bool(solved and body.get("ok"))
    parameters = {}
    studies = {}
    for name, value in (body.get("results") or {}).items():
        if name.startswith("param."):
            parameters[name[6:]] = value
        elif name.startswith("study."):
            studies[name[6:]] = value
    body["project_parameters"] = parameters
    body["studies"] = studies
    body["source_preserved"] = True
    return body
