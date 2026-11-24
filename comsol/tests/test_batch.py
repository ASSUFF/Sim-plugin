import json
from pathlib import Path
from types import SimpleNamespace

from comsol_plugin.batch import parse_results, run_java

GOOD = """
import com.comsol.model.*;
import com.comsol.model.util.ModelUtil;
public class Sample {
    public static void main(String[] args) {
        ModelUtil.initStandalone(false);
        Model model = ModelUtil.create("Sample");
        model.param().set("L", "20[mm]");
        System.out.println("===RESULT===");
        System.out.println("L=" + model.param().get("L"));
        model.save("Sample.mph");
    }
}
"""


def _install(root: Path) -> None:
    win64 = root / "bin" / "win64"
    win64.mkdir(parents=True)
    for name in ("comsolbatch.exe", "comsolcompile.exe"):
        (win64 / name).write_text("", encoding="utf-8")


def test_parse_results_reads_marker_block() -> None:
    stdout = "progress\n===RESULT===\nL=20[mm]\nvolume_m3=8.0e-6\n===END===\n"
    assert parse_results(stdout) == {"L": "20[mm]", "volume_m3": "8.0e-6"}


def test_invalid_java_does_not_launch(tmp_path: Path) -> None:
    java = tmp_path / "Sample.java"
    java.write_text("public class Sample {}", encoding="utf-8")
    calls: list[list[str]] = []

    def runner(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    result = run_java(java, runs_root=tmp_path / "runs", install_root=tmp_path, runner=runner)
    assert result["ok"] is False
    assert result["stage"] == "validate"
    assert result["launched_solver"] is False
    assert calls == []


def test_spec_value_replaces_java_literal(tmp_path: Path) -> None:
    install = tmp_path / "comsol"
    _install(install)
    java = tmp_path / "Sample.java"
    java.write_text(GOOD, encoding="utf-8")
    spec = tmp_path / "job.json"
    spec.write_text('{"parameters": {"L": {"value": "5[mm]"}}, "exports": ["L"]}', encoding="utf-8")
    seen: list[str] = []

    def runner(command, **kwargs):
        if Path(command[0]).name == "comsolcompile.exe":
            seen.append(Path(command[1]).read_text(encoding="utf-8"))
            Path(command[1]).with_suffix(".class").write_text("class", encoding="utf-8")
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        return SimpleNamespace(returncode=0, stdout="===RESULT===\nL=5[mm]\n", stderr="")

    result = run_java(java, spec, runs_root=tmp_path / "runs", install_root=install, stoptime_s=30, runner=runner)
    assert result["ok"] is True
    assert 'set("L", "5[mm]")' in seen[0]
    assert 'set("L", "20[mm]")' not in seen[0]


def test_unconfirmed_spec_does_not_launch(tmp_path: Path) -> None:
    java = tmp_path / "Sample.java"
    java.write_text(GOOD, encoding="utf-8")
    spec = tmp_path / "job.json"
    spec.write_text('{"parameters": {"L": {"value": "5[mm]"}}}', encoding="utf-8")
    result = run_java(java, spec, runs_root=tmp_path / "runs", install_root=tmp_path, check_confirmation=True)
    assert result["ok"] is False
    assert result["stage"] == "confirm"
    assert result["launched_solver"] is False


def test_report_records_assumed_items(tmp_path: Path) -> None:
    install = tmp_path / "comsol"
    _install(install)
    java = tmp_path / "Sample.java"
    java.write_text(GOOD, encoding="utf-8")
    spec = tmp_path / "job.json"
    spec.write_text(
        '{"parameters": {"L": {"value": "20[mm]"}}, "confirmation": {"items": ['
        '{"name": "frequency", "source": "specified", "value": "稳态"},'
        '{"name": "material", "source": "assumed", "value": "导热系数 10"}]}}',
        encoding="utf-8",
    )

    def runner(command, **kwargs):
        if Path(command[0]).name == "comsolcompile.exe":
            Path(command[1]).with_suffix(".class").write_text("class", encoding="utf-8")
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        return SimpleNamespace(returncode=0, stdout="===RESULT===\nL=20[mm]\n", stderr="")

    result = run_java(java, spec, runs_root=tmp_path / "runs", install_root=install, stoptime_s=30, runner=runner)
    saved = json.loads(Path(result["report"]).read_text(encoding="utf-8"))
    assert saved["assumptions"] == ["material: 导热系数 10"]


def test_compile_failure_keeps_the_compiler_text(tmp_path: Path) -> None:
    install = tmp_path / "comsol"
    _install(install)
    java = tmp_path / "Sample.java"
    java.write_text(GOOD, encoding="utf-8")
    seen = {}

    def runner(command, **kwargs):
        seen.update(kwargs)
        return SimpleNamespace(returncode=1, stdout="", stderr="错误：找不到符号\n")

    result = run_java(java, runs_root=tmp_path / "runs", install_root=install, stoptime_s=30, runner=runner)
    assert result["ok"] is False
    assert result["stage"] == "compile"
    assert "找不到符号" in result["error"]
    assert "找不到符号" in result["log_tail"]
    assert seen["errors"] == "replace"


def test_spec_run_root_is_honored(tmp_path: Path) -> None:
    install = tmp_path / "comsol"
    _install(install)
    java = tmp_path / "Sample.java"
    java.write_text(GOOD, encoding="utf-8")
    spec = tmp_path / "job.json"
    root = tmp_path / "自定义结果"
    spec.write_text(json.dumps({"run_root": str(root)}), encoding="utf-8")

    def runner(command, **kwargs):
        if Path(command[0]).name == "comsolcompile.exe":
            Path(command[1]).with_suffix(".class").write_text("class", encoding="utf-8")
            (Path(command[1]).parent / "mode.csv").write_text("x,y\n", encoding="utf-8")
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        return SimpleNamespace(returncode=0, stdout="===RESULT===\nL=1\n", stderr="")

    result = run_java(java, spec, install_root=install, stoptime_s=30, runner=runner)
    assert str(root) in result["work_dir"]
    assert any(path.endswith("mode.csv") for path in result["export_files"])


def test_fake_toolchain_returns_results(tmp_path: Path) -> None:
    install = tmp_path / "comsol"
    _install(install)
    java = tmp_path / "Sample.java"
    java.write_text(GOOD, encoding="utf-8")

    def runner(command, **kwargs):
        if Path(command[0]).name == "comsolcompile.exe":
            Path(command[1]).with_suffix(".class").write_text("class", encoding="utf-8")
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        return SimpleNamespace(
            returncode=0,
            stdout="MESH_ELEMENTS=6674\n===RESULT===\nL=20[mm]\n",
            stderr="",
        )

    result = run_java(java, runs_root=tmp_path / "runs", install_root=install, stoptime_s=30, runner=runner)
    assert result["ok"] is True
    assert result["solver"]["mesh_elements"] == 6674
    assert result["solver"]["elapsed_s"] >= 0
    assert result["launched_solver"] is True
    assert result["results"] == {"L": "20[mm]"}
    assert result["returncode"] == 0
    assert Path(result["work_dir"]).is_dir()
