import json
from pathlib import Path

from comsol_plugin.validate import validate_job

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "ParameterBlock.java"
SPEC = Path(__file__).resolve().parents[1] / "examples" / "parameter_block.json"


def _write_java(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")


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


def test_example_spec_passes() -> None:
    result = validate_job(EXAMPLE, SPEC)
    assert result["ok"] is True
    assert result["launched_solver"] is False
    assert result["class_name"] == "ParameterBlock"
    assert result["parameters"] == ["L"]
    assert result["exports"] == ["L"]
    assert result["errors"] == []


def test_class_name_must_match_file(tmp_path: Path) -> None:
    path = tmp_path / "Other.java"
    _write_java(path, GOOD)
    result = validate_job(path)
    assert result["ok"] is False
    assert any("公开类名" in error for error in result["errors"])


def test_external_process_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "Sample.java"
    _write_java(path, GOOD.replace("ModelUtil.initStandalone(false);", "ModelUtil.initStandalone(false);\n        Runtime.getRuntime();"))
    result = validate_job(path)
    assert result["ok"] is False
    assert any("外部进程" in error for error in result["errors"])


def test_spec_parameter_must_be_set_in_java(tmp_path: Path) -> None:
    java = tmp_path / "Sample.java"
    spec = tmp_path / "job.json"
    _write_java(java, GOOD)
    spec.write_text(
        json.dumps({"parameters": {"W": {"value": "1[mm]"}}, "exports": ["L"], "goal": {"expression": "L", "sense": "min"}}),
        encoding="utf-8",
    )
    result = validate_job(java, spec)
    assert result["ok"] is False
    assert any("参数 W" in error for error in result["errors"])
    assert result["goal"] == {"expression": "L", "sense": "min"}


def test_dynamic_exports_skip_the_literal_name_check(tmp_path: Path) -> None:
    java = tmp_path / "Sample.java"
    spec = tmp_path / "job.json"
    _write_java(
        java,
        GOOD.replace('System.out.println("L="', 'System.out.printf("mode%d=", i); // L='),
    )
    spec.write_text(
        json.dumps({"exports": ["mode0"], "dynamic_exports": True}),
        encoding="utf-8",
    )
    result = validate_job(java, spec)
    assert result["errors"] == []


def test_goal_outside_exports_fails(tmp_path: Path) -> None:
    java = tmp_path / "Sample.java"
    spec = tmp_path / "job.json"
    _write_java(java, GOOD)
    spec.write_text(json.dumps({"exports": ["L"], "goal": {"expression": "volume", "sense": "max"}}), encoding="utf-8")
    result = validate_job(java, spec)
    assert result["ok"] is False
    assert any("goal.expression" in error for error in result["errors"])
