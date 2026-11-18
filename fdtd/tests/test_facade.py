import json
from pathlib import Path
from types import SimpleNamespace

from fdtd_plugin.advise import advise
from fdtd_plugin.backend import doctor, run
from fdtd_plugin.optimize import optimize_with


def test_doctor_reports_missing_install_without_launching(monkeypatch) -> None:
    def missing():
        raise FileNotFoundError("lumapi.py was not found")

    monkeypatch.setattr("fdtd_plugin.backend.find_install", missing)
    result = doctor()
    assert result["ok"] is False
    assert result["installed"] is False
    assert result["launched_solver"] is False
    blocked = run({"name": "smoke"})
    assert blocked["stage"] == "install"
    assert blocked["launched_solver"] is False


def test_optimize_picks_the_higher_transmission(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LUMERICAL_FDTD_RUNS", str(tmp_path))

    def evaluate(spec):
        width = spec["overrides"][-1]["value"]
        return {
            "ok": True,
            "launched_solver": True,
            "exports": [{"name": "T", "data": {"fields": {"T": {"values": [width]}}}}],
        }

    result = optimize_with(
        {
            "name": "wg",
            "base": {"name": "wg"},
            "parameter": {"object": "waveguide", "property": "y span"},
            "optimize": {"min": 2e-7, "max": 5e-7, "max_runs": 4},
            "metric": {"goal": "max", "export": "T"},
        },
        evaluate,
    )
    assert result["ok"] is True
    assert result["run_count"] == 4
    assert result["best"]["value"] == 5e-7
    advice = advise(result["report"])
    assert advice["launched_solver"] is False
    assert any(fact["name"] == "boundary" for fact in advice["facts"])


def test_run_uses_the_lumerical_interpreter(monkeypatch, tmp_path: Path) -> None:
    python = tmp_path / "python.exe"
    python.write_text("", encoding="utf-8")
    monkeypatch.delenv("LUMERICAL_PYTHON", raising=False)
    monkeypatch.setenv("LUMERICAL_FDTD_RUNS", str(tmp_path))

    class Install:
        def __init__(self):
            self.python = python

        def as_dict(self):
            return {"python": str(self.python), "lumapi": "lumapi.py", "root": "Lumerical", "api_dir": "api", "bin_dir": "bin", "solver": None}

    monkeypatch.setattr("fdtd_plugin.backend.find_install", lambda: Install())
    seen = {}

    def runner(command, **kwargs):
        seen["command"] = command
        return SimpleNamespace(returncode=0, stdout='FDTD_RESULT {"ok": true, "run_dir": "run"}\n', stderr="")

    result = run({"name": "smoke", "simulation": {"dimension": "2D"}}, runner=runner)
    assert result["ok"] is True
    assert seen["command"][0] == str(python)


def test_prepare_fills_wavelength_without_solver() -> None:
    from fdtd_plugin.backend import prepare

    result = prepare({"commands": [{"op": "addrect", "properties": {"name": "wg"}}]})
    assert result["launched_solver"] is False
    assert result["spec"]["global_source"]["wavelength start"] == 1.55e-6
