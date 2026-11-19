import json
from pathlib import Path

from sim_plugin.paper import add_paper, compare, create_case, set_spec, set_targets, status


def test_case_holds_the_request_and_a_saved_pdf(tmp_path: Path) -> None:
    folder = tmp_path / "ln-eom"
    created = create_case(folder, "铌酸锂电光调制器的电极仿真", "hfss")
    assert created["ok"] is True
    assert created["launched_solver"] is False
    source = tmp_path / "article.pdf"
    source.write_bytes(b"%PDF-1.4")
    added = add_paper(
        folder,
        {"title": "Electrode design", "year": 2020, "doi": "10.1000/example"},
        pdf=source,
    )
    assert added["pdf"].endswith("paper.pdf")
    assert (folder / "paper.pdf").read_bytes() == b"%PDF-1.4"
    assert source.is_file()


def test_missing_pdf_is_not_invented(tmp_path: Path) -> None:
    folder = tmp_path / "case"
    create_case(folder, "一段波导", "fdtd")
    result = add_paper(folder, {"title": "A waveguide"}, pdf=tmp_path / "missing.pdf")
    assert result["ok"] is False
    assert result["launched_solver"] is False
    assert not (folder / "paper.pdf").exists()


def test_compare_uses_the_paper_tolerance(tmp_path: Path) -> None:
    folder = tmp_path / "case"
    create_case(folder, "电极 S11", "hfss")
    add_paper(folder, {"title": "Electrode paper", "year": 2020})
    set_targets(
        folder,
        {
            "metrics": [
                {"name": "S11_dB", "paper": -20, "unit": "dB", "tolerance": 2, "note": "10 GHz"},
                {"name": "bandwidth_GHz", "paper": {"min": 40, "max": 50}},
            ]
        },
    )
    set_spec(folder, {"name": "electrode", "frequency_hz": 1e10})
    result = compare(
        folder,
        {"metrics": [{"name": "S11_dB", "simulated": -18.4}, {"name": "bandwidth_GHz", "simulated": 55}]},
    )
    assert result["launched_solver"] is False
    assert result["rows"][0]["within"] is True
    assert result["rows"][1]["within"] is False
    assert (folder / "汇报.md").is_file()
    saved = json.loads((folder / "comparison.json").read_text(encoding="utf-8"))
    assert saved["mismatched"] == 1
    state = status(folder)
    assert state["missing"] == []


def test_report_path_supplies_the_simulated_value(tmp_path: Path) -> None:
    folder = tmp_path / "case"
    create_case(folder, "透射", "fdtd")
    set_targets(folder, {"metrics": [{"name": "T", "paper": 0.42, "tolerance": 0.05}]})
    report = tmp_path / "report.json"
    report.write_text(
        json.dumps({"best": {"results": {"T": 0.4}}}),
        encoding="utf-8",
    )
    result = compare(folder, {}, report=report, mapping={"T": "best.results.T"})
    assert result["rows"][0]["simulated"] == 0.4
    assert result["rows"][0]["within"] is True


def test_compare_before_targets_does_not_launch(tmp_path: Path) -> None:
    folder = tmp_path / "case"
    create_case(folder, "稳态导热", "comsol")
    result = compare(folder, {"T_avg_K": 350})
    assert result["ok"] is False
    assert result["stage"] == "paper"
    assert result["launched_solver"] is False
