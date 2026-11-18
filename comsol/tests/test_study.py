import json
from pathlib import Path
from types import SimpleNamespace

from comsol_plugin.advise import advise
from comsol_plugin.study import run_optimize, run_sweep

JAVA = """
import com.comsol.model.*;
import com.comsol.model.util.ModelUtil;
public class Sample {
    public static void main(String[] args) {
        ModelUtil.initStandalone(false);
        Model model = ModelUtil.create("Sample");
        model.param().set("T_hot", "400[K]");
        System.out.println("===RESULT===");
        System.out.println("T_avg_K=350");
        model.save("Sample.mph");
    }
}
"""


def _install(root: Path) -> None:
    win64 = root / "bin" / "win64"
    win64.mkdir(parents=True)
    for name in ("comsolbatch.exe", "comsolcompile.exe"):
        (win64 / name).write_text("", encoding="utf-8")


def _runner_from_hot(command, **kwargs):
    if Path(command[0]).name == "comsolcompile.exe":
        Path(command[1]).with_suffix(".class").write_text("class", encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="", stderr="")
    text = Path(kwargs["cwd"], "Sample.java").read_text(encoding="utf-8")
    hot = float(text.split('set("T_hot", "')[1].split("[K]")[0])
    avg = (300 + hot) / 2
    return SimpleNamespace(
        returncode=0,
        stdout=f"===RESULT===\nT_avg_K={avg:.6f}\n",
        stderr="",
    )


def _write_case(tmp_path: Path, spec: dict) -> tuple[Path, Path, Path]:
    _install(tmp_path / "comsol")
    java = tmp_path / "Sample.java"
    java.write_text(JAVA, encoding="utf-8")
    spec_path = tmp_path / "job.json"
    spec_path.write_text(json.dumps(spec), encoding="utf-8")
    return java, spec_path, tmp_path / "comsol"


def test_sweep_picks_smaller_average(tmp_path: Path) -> None:
    java, spec, install = _write_case(
        tmp_path,
        {
            "parameters": {"T_hot": {"value": "400[K]"}},
            "sweep": {"T_hot": ["320[K]", "480[K]"]},
            "exports": ["T_avg_K"],
            "goal": {"expression": "T_avg_K", "sense": "min"},
        },
    )
    result = run_sweep(java, spec, runs_root=tmp_path / "runs", install_root=install, stoptime_s=30, runner=_runner_from_hot)
    assert result["ok"] is True
    assert result["run_count"] == 2
    assert result["best"]["parameters"] == {"T_hot": "320[K]"}
    assert result["best"]["results"]["T_avg_K"] == "310.000000"


def test_optimize_refines_and_keeps_the_low_end(tmp_path: Path) -> None:
    java, spec, install = _write_case(
        tmp_path,
        {
            "parameters": {"T_hot": {"value": "400[K]"}},
            "optimize": {"parameter": "T_hot", "min": 320, "max": 480, "unit": "K", "max_runs": 4},
            "exports": ["T_avg_K"],
            "goal": {"expression": "T_avg_K", "sense": "min"},
        },
    )
    result = run_optimize(java, spec, runs_root=tmp_path / "runs", install_root=install, stoptime_s=30, runner=_runner_from_hot)
    assert result["ok"] is True
    assert result["run_count"] == 4
    assert result["best"]["parameters"]["T_hot"] == "320[K]"
    assert float(result["best"]["results"]["T_avg_K"]) == 310


def test_sweep_rejects_more_than_eight_runs(tmp_path: Path) -> None:
    java, spec, install = _write_case(
        tmp_path,
        {
            "parameters": {"T_hot": {"value": "400[K]"}},
            "sweep": {"T_hot": ["1[K]", "2[K]", "3[K]"], "L": ["1[m]", "2[m]", "3[m]"]},
            "exports": ["T_avg_K"],
            "goal": {"expression": "T_avg_K", "sense": "min"},
        },
    )
    result = run_sweep(java, spec, runs_root=tmp_path / "runs", install_root=install, runner=_runner_from_hot)
    assert result["ok"] is False
    assert result["launched_solver"] is False
    assert "超过上限" in result["error"]


def test_advise_says_single_run_is_not_an_optimum(tmp_path: Path) -> None:
    report = tmp_path / "report.json"
    report.write_text(
        json.dumps({"ok": True, "results": {"T_avg_K": "350.000000"}, "goal": {"expression": "T_avg_K", "sense": "min"}}),
        encoding="utf-8",
    )
    result = advise(report)
    assert result["ok"] is True
    assert result["launched_solver"] is False
    assert any(fact["name"] == "single_run" for fact in result["facts"])
