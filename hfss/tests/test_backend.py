import json
from pathlib import Path
from types import SimpleNamespace

from hfss_plugin.advise import advise
from hfss_plugin.backend import doctor, inspect, license_error, prepare, run, set_project, sweep, validate


def _python(tmp_path: Path) -> Path:
    exe = tmp_path / "python.exe"
    exe.write_text("", encoding="utf-8")
    return exe


def test_missing_backend_python_does_not_launch(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("HFSS_AEDT_PYTHON", raising=False)
    monkeypatch.delenv("HFSS_AEDT_SRC", raising=False)
    result = doctor(python=tmp_path / "missing.exe")
    assert result["ok"] is False
    assert result["launched_solver"] is False
    assert result["stage"] == "backend"
    assert "HFSS_AEDT_PYTHON" in result["error"]
    assert "HFSS_AEDT_SRC" in result["error"]
    assert "simulation" not in result["error"]


def test_doctor_reads_backend_json(tmp_path: Path) -> None:
    def runner(command, **kwargs):
        assert command[0].endswith("python.exe")
        assert "hfss_aedt.discover" in command[2]
        return SimpleNamespace(returncode=0, stdout='{"ok": true, "version": "2024.2", "launched_solver": false}\n', stderr="")

    result = doctor(python=_python(tmp_path), src=tmp_path, runner=runner)
    assert result["ok"] is True
    assert result["version"] == "2024.2"
    assert result["launched_solver"] is False


def test_prepare_sends_spec_on_stdin(tmp_path: Path) -> None:
    seen = {}

    def runner(command, **kwargs):
        seen["input"] = kwargs["input"]
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"ok": True, "launched_solver": False, "assumptions": ["frequency=10 GHz"]}),
            stderr="",
        )

    result = prepare({"name": "partial"}, python=_python(tmp_path), src=tmp_path, runner=runner)
    assert json.loads(seen["input"]) == {"name": "partial"}
    assert result["assumptions"] == ["frequency=10 GHz"]


def _engine_file(tmp_path: Path) -> None:
    engine = tmp_path / "hfss_aedt" / "engine.py"
    engine.parent.mkdir(parents=True, exist_ok=True)
    engine.write_text("", encoding="utf-8")


def test_run_parses_hfss_result_and_validates_first(tmp_path: Path) -> None:
    _engine_file(tmp_path)
    calls: list[list[str]] = []

    def runner(command, **kwargs):
        calls.append(command)
        if "-c" in command:
            return SimpleNamespace(returncode=0, stdout='{"ok": true, "launched_solver": false}\n', stderr="")
        return SimpleNamespace(
            returncode=0,
            stdout='noise\nHFSS_RESULT {"ok": true, "run_dir": "D:/runs/wr90", "s_db": {"dB(S(P2,P1))": 0.0}}\n',
            stderr="",
        )

    result = run({"name": "wr90"}, python=_python(tmp_path), src=tmp_path, runner=runner)
    assert result["ok"] is True
    assert result["launched_solver"] is True
    assert result["s_db"]["dB(S(P2,P1))"] == 0.0
    assert calls[0][1] == "-c"
    assert calls[1][2] == "run"


def test_closed_license_port_is_reported() -> None:
    message = license_error("59999@127.0.0.1")
    assert message is not None
    assert "59999@127.0.0.1" in message


def test_inspect_opens_a_copy_of_an_existing_project(tmp_path: Path, monkeypatch) -> None:
    project = tmp_path / "model.aedt"
    project.write_text("dummy", encoding="utf-8")
    monkeypatch.setattr("hfss_plugin.backend._runs_root", lambda: tmp_path / "runs")
    monkeypatch.setattr("hfss_plugin.backend._engine_path", lambda source=None: tmp_path / "engine.py")
    monkeypatch.setattr("hfss_plugin.backend._backend_python", lambda: tmp_path / "python.exe")
    monkeypatch.setattr("hfss_plugin.backend._backend_src", lambda: tmp_path)
    (tmp_path / "engine.py").write_text("", encoding="utf-8")
    (tmp_path / "python.exe").write_text("", encoding="utf-8")
    seen = {}

    def runner(command, **kwargs):
        seen["command"] = command
        return SimpleNamespace(
            returncode=0,
            stdout='HFSS_RESULT {"ok": true, "model": {"objects": ["box"], "setups": ["Setup1"]}}\n',
            stderr="",
        )

    result = inspect(str(project), runner=runner)
    assert result["ok"] is True
    assert result["solved"] is False
    assert result["source_preserved"] is True
    assert seen["command"][2] == "inspect"
    opened = Path(seen["command"][4])
    assert opened.is_file()
    assert opened.resolve() != project.resolve()


def test_set_project_does_not_solve(monkeypatch) -> None:
    seen = {}

    def fake_run(spec, **kwargs):
        seen["spec"] = spec
        return {"ok": True, "launched_solver": True}

    monkeypatch.setattr("hfss_plugin.backend.run", fake_run)
    result = set_project({"project": "model.aedt", "variables": {"L": "30mm"}})
    assert result["solved"] is False
    assert seen["spec"]["setup_only"] is True
    assert seen["spec"]["variables"]["L"] == "30mm"


def test_protected_project_is_refused(tmp_path: Path) -> None:
    result = run({"project": r"S:\simulation\HFSS\4mm.aedt"}, python=_python(tmp_path), src=tmp_path)
    assert result["ok"] is False
    assert result["launched_solver"] is False
    assert "4mm.aedt" in result["error"]


def test_sweep_publishes_comsol_rows_and_best(tmp_path: Path, monkeypatch) -> None:
    _engine_file(tmp_path)
    monkeypatch.setattr("hfss_plugin.backend._runs_root", lambda: tmp_path)
    summary = tmp_path / "run02"
    summary.mkdir()
    (summary / "summary.json").write_text(
        json.dumps({"s_db": {"dB(S(P2,P1))": -0.0, "dB(S(P1,P1))": -69.985}}),
        encoding="utf-8",
    )

    def runner(command, **kwargs):
        payload = {
            "ok": True,
            "goal": "min",
            "points": [
                {"value": 0.02, "ok": True, "score": -69.985, "run_dir": str(summary)},
                {"value": 0.03, "ok": True, "score": -64.084, "run_dir": "missing"},
                {"value": 0.04, "ok": True, "score": -67.465, "run_dir": "missing-too"},
            ],
        }
        return SimpleNamespace(returncode=0, stdout="HFSS_RESULT " + json.dumps(payload) + "\n", stderr="")

    result = sweep(
        {
            "name": "wr90_length_sweep",
            "base": {"name": "wr90"},
            "parameter": {"path": "geometry.length_m"},
            "values": [0.02, 0.03, 0.04],
            "metric": {"goal": "min", "key": "dB(S(P1,P1))"},
        },
        python=_python(tmp_path),
        src=tmp_path,
        runner=runner,
    )
    assert result["stage"] == "sweep"
    assert result["launched_solver"] is True
    assert result["goal"] == {"expression": "dB(S(P1,P1))", "sense": "min"}
    assert [row["parameters"] for row in result["rows"]] == [
        {"geometry.length_m": 0.02},
        {"geometry.length_m": 0.03},
        {"geometry.length_m": 0.04},
    ]
    assert set(result["best"]) == {"parameters", "ok", "results", "work_dir", "error"}
    assert result["best"]["parameters"] == {"geometry.length_m": 0.02}
    assert result["best"]["results"]["dB(S(P1,P1))"] == -69.985
    assert result["best"]["results"]["dB(S(P2,P1))"] == -0.0
    assert "全局最优" in result["note"]
    advice = advise(result["report"])
    assert advice["launched_solver"] is False
    names = {fact["name"] for fact in advice["facts"]}
    assert {"goal", "samples", "best", "best_s", "boundary"} <= names


def test_sweep_fills_s21_from_touchstone(tmp_path: Path, monkeypatch) -> None:
    _engine_file(tmp_path)
    monkeypatch.setattr("hfss_plugin.backend._runs_root", lambda: tmp_path)
    run_dir = tmp_path / "solved"
    run_dir.mkdir()
    (run_dir / "waveguide.s2p").write_text(
        "\n".join(
            [
                "# GHz S MA R 50",
                "10 0.000316762156100499 -102.75 0.999999949830867 178.71 0.999999949830867 178.71 0.000316762156100479 -79.83",
            ]
        ),
        encoding="utf-8",
    )

    def runner(command, **kwargs):
        payload = {
            "ok": True,
            "points": [{"value": 0.03, "ok": True, "score": -64.084, "run_dir": str(run_dir)}],
        }
        return SimpleNamespace(returncode=0, stdout="HFSS_RESULT " + json.dumps(payload) + "\n", stderr="")

    result = sweep(
        {
            "base": {"name": "wr90"},
            "parameter": {"path": "geometry.length_m"},
            "values": [0.02, 0.03],
            "metric": {"goal": "min", "key": "dB(S(P1,P1))"},
        },
        python=_python(tmp_path),
        src=tmp_path,
        runner=runner,
    )
    results = result["rows"][0]["results"]
    assert results["dB(S(P1,P1))"] == -64.084
    assert results["dB(S(P2,P1))"] == 0.0
    assert results["frequency_ghz"] == 10.0


def test_backend_without_json_is_an_error(tmp_path: Path) -> None:
    def runner(command, **kwargs):
        return SimpleNamespace(returncode=1, stdout="not json", stderr="boom")

    result = validate({}, python=_python(tmp_path), src=tmp_path, runner=runner)
    assert result["ok"] is False
    assert "JSON" in result["error"]
