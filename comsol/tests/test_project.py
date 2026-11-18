from pathlib import Path

from comsol_plugin.project import inspect_mph, set_mph


def test_missing_mph_is_rejected() -> None:
    result = inspect_mph("missing.mph")
    assert result["ok"] is False
    assert result["launched_solver"] is False
    assert result["solved"] is False


def test_non_mph_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "model.txt"
    path.write_text("nope", encoding="utf-8")
    result = set_mph(path, {"L": "2[mm]"})
    assert result["ok"] is False
    assert "mph" in result["error"]


def test_existing_java_loads_the_copy_target(tmp_path: Path, monkeypatch) -> None:
    project = tmp_path / "plate.mph"
    project.write_text("mph", encoding="utf-8")
    seen = {}

    def fake_run(java, **kwargs):
        seen["java"] = Path(java).read_text(encoding="utf-8")
        return {
            "ok": True,
            "launched_solver": True,
            "results": {"param.L": "20[mm]", "study.std1": "Study 1"},
        }

    monkeypatch.setattr("comsol_plugin.project.run_java", fake_run)
    result = set_mph(project, {"L": "2[mm]"}, runs_root=tmp_path)
    assert result["solved"] is False
    assert result["project_parameters"]["L"] == "20[mm]"
    assert result["studies"]["std1"] == "Study 1"
    assert project.as_posix() in seen["java"]
    assert 'model.param().set("L", "2[mm]")' in seen["java"]
    assert ".run()" not in seen["java"]


def test_solve_requires_a_study_tag(tmp_path: Path) -> None:
    project = tmp_path / "plate.mph"
    project.write_text("mph", encoding="utf-8")
    result = set_mph(project, {}, solve=True)
    assert result["ok"] is False
    assert result["launched_solver"] is False
    assert "study" in result["error"]
