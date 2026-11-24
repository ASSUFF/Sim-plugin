import json
from pathlib import Path

from sim_plugin.paper import add_paper, compare, create_case, set_spec, set_targets, status, write_map


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


def test_report_array_index_and_default_map(tmp_path: Path) -> None:
    folder = tmp_path / "case"
    create_case(folder, "透射", "fdtd")
    set_targets(folder, {"metrics": [{"name": "T", "paper": 0.5, "tolerance": 0.1}]})
    written = write_map(folder)
    assert written["mapping"]["T"] == "exports[0].data.array.values[middle]"
    report = tmp_path / "report.json"
    report.write_text(
        json.dumps({"exports": [{"data": {"array": {"values": [0.1, 0.48, 0.2]}}}]}),
        encoding="utf-8",
    )
    result = compare(folder, {}, report=report)
    assert result["mapping_source"] == "对照.json"
    assert result["rows"][0]["simulated"] == 0.48
    assert result["rows"][0]["within"] is True


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
    report_text = (folder / "汇报.md").read_text(encoding="utf-8")
    assert "40–50" in report_text
    assert "—" not in report_text.split("bandwidth_GHz")[0]
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


def test_comsol_report_stores_numbers_as_strings(tmp_path: Path) -> None:
    folder = tmp_path / "case"
    create_case(folder, "加热器温度", "comsol")
    set_targets(
        folder,
        {
            "metrics": [
                {"name": "T_heater_max_K", "paper": 411, "tolerance": 20, "unit": "K"},
                {"name": "note", "paper": 1, "tolerance": 0},
            ]
        },
    )
    report = tmp_path / "report.json"
    report.write_text(
        json.dumps({"results": {"T_heater_max_K": "415.24", "note": "not-a-number"}}),
        encoding="utf-8",
    )
    result = compare(
        folder,
        {},
        report=report,
        mapping={"T_heater_max_K": "results.T_heater_max_K", "note": "results.note"},
    )
    assert result["rows"][0]["simulated"] == 415.24
    assert result["rows"][0]["within"] is True
    assert result["rows"][1]["simulated"] is None


def test_non_finite_result_is_rejected() -> None:
    from sim_plugin.result_check import problems

    found = problems({"E": "Infinity", "V": 1.0}, {"V": {"min": 0.5}})
    assert any("E" in item for item in found)
    assert not any(item.startswith("V=") for item in found)


def test_paper_new_solver_flag_does_not_crash(tmp_path: Path) -> None:
    from sim_plugin.cli import main

    code = main(
        [
            "paper",
            "new",
            "--folder",
            str(tmp_path / "case"),
            "--solver",
            "hfss",
            "--request",
            "铌酸锂电极",
        ]
    )
    assert code == 0
    assert (tmp_path / "case" / "request.json").is_file()


def test_compare_before_targets_does_not_launch(tmp_path: Path) -> None:
    folder = tmp_path / "case"
    create_case(folder, "稳态导热", "comsol")
    result = compare(folder, {"T_avg_K": 350})
    assert result["ok"] is False
    assert result["stage"] == "paper"
    assert result["launched_solver"] is False
