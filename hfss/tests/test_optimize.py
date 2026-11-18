import json
from pathlib import Path

from hfss_plugin.advise import advise
from hfss_plugin.optimize import optimize
from sim_plugin.confirm import CORE_ITEMS, STUDY_ITEMS, confirm


def _items(*, study: bool) -> list[dict]:
    names = list(CORE_ITEMS) + (list(STUDY_ITEMS) if study else [])
    return [{"name": name, "source": "specified", "value": name} for name in names]


def test_optimize_picks_lower_reflection_and_refines(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("hfss_plugin.optimize._runs_root", lambda: tmp_path)
    monkeypatch.setattr("hfss_plugin.optimize.license_error", lambda: None)

    def evaluate(spec, **kwargs):
        length = spec["geometry"]["length_m"]
        return {
            "ok": True,
            "launched_solver": True,
            "run_dir": f"run-{length}",
            "s_db": {"dB(S(P1,P1))": -100.0 + length * 1000, "dB(S(P2,P1))": 0.0},
        }

    monkeypatch.setattr("hfss_plugin.optimize.run", evaluate)
    study = confirm(
        {
            "name": "wr90_length",
            "base": {"name": "wr90", "geometry": {"length_m": 0.03}},
            "parameter": {"path": "geometry.length_m"},
            "optimize": {"min": 0.02, "max": 0.04, "max_runs": 4},
            "metric": {"goal": "min", "key": "dB(S(P1,P1))"},
            "confirmation": {"items": _items(study=True)},
        }
    )["spec"]
    result = optimize(study)
    assert result["ok"] is True
    assert result["run_count"] == 4
    assert result["best"]["value"] == 0.02
    assert result["launched_solver"] is True
    report = json.loads(Path(result["report"]).read_text(encoding="utf-8"))
    advice = advise(report["report"])
    assert advice["launched_solver"] is False
    names = {fact["name"] for fact in advice["facts"]}
    assert "best" in names
    assert "boundary" in names


def test_optimize_rejects_too_many_runs() -> None:
    result = optimize(
        {
            "base": {"name": "wr90"},
            "parameter": {"path": "geometry.length_m"},
            "optimize": {"min": 0.02, "max": 0.04, "max_runs": 9},
            "metric": {"goal": "min", "key": "dB(S(P1,P1))"},
        }
    )
    assert result["ok"] is False
    assert result["launched_solver"] is False


def test_advise_single_run_is_not_an_optimum(tmp_path: Path) -> None:
    report = tmp_path / "summary.json"
    report.write_text(
        json.dumps({"ok": True, "s_db": {"frequency_ghz": 10.0, "dB(S(P2,P1))": -0.0, "dB(S(P1,P1))": -64.084}}),
        encoding="utf-8",
    )
    result = advise(report)
    assert any(fact["name"] == "single_run" for fact in result["facts"])
    assert any("S21" in fact["detail"] and "S11" in fact["detail"] for fact in result["facts"])
