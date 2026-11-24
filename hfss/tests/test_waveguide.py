from hfss_aedt.engine import s_expressions, wall_conductivity
from hfss_aedt.validate import validate_spec


def _guide(**geometry):
    body = {
        "kind": "rectangular_waveguide",
        "a_m": 0.02286,
        "b_m": 0.01016,
        "length_m": 0.03,
        "material": "vacuum",
    }
    body.update(geometry)
    return {"name": "wr90", "frequency_hz": 1.0e10, "geometry": body}


def test_inspect_snapshot_lists_variable_names() -> None:
    from hfss_aedt.engine import design_variable_names, snapshot

    class _Manager:
        independent_variables = {"length": object(), "offset": object()}

    class _Model:
        project_name = "owned"
        design_name = "HFSS"
        modeler = type("Modeler", (), {"object_names": ["waveguide"]})()
        setup_names = ["Setup1"]
        variable_manager = _Manager()

    assert design_variable_names(_Model()) == ["length", "offset"]
    assert snapshot(_Model())["variables"] == ["length", "offset"]


def test_single_mode_names_stay_the_same() -> None:
    assert s_expressions(1) == [
        "dB(S(P1,P1))",
        "dB(S(P2,P1))",
        "dB(S(P1,P2))",
        "dB(S(P2,P2))",
    ]


def test_second_mode_uses_the_port_mode_index() -> None:
    names = s_expressions(2)
    assert "dB(S(P2:1,P1:1))" in names
    assert "dB(S(P2:2,P1:1))" in names
    assert "dB(S(P2,P1))" not in names


def test_gold_wall_uses_a_known_conductivity() -> None:
    assert wall_conductivity({"wall": "pec"}) is None
    assert wall_conductivity({"wall": "gold"}) == 4.1e7
    assert wall_conductivity({"wall": "finite", "wall_conductivity_s_m": 1.0e7}) == 1.0e7


def test_two_modes_and_a_named_wall_pass_validation() -> None:
    errors, warnings = validate_spec(_guide(modes=2, wall="gold"))
    assert errors == []
    assert warnings == []


def test_finite_wall_without_conductivity_is_rejected() -> None:
    errors, _warnings = validate_spec(_guide(wall="finite"))
    assert any("wall_conductivity_s_m" in error for error in errors)


def test_in_solver_frequency_sweep_is_not_eight_runs(tmp_path) -> None:
    from sim_plugin.checklist import rejection
    from hfss_aedt.engine import spectrum_frequencies, write_spectrum_csv

    spec = _guide()
    spec["max_passes"] = 4
    spec["max_delta_s"] = 0.02
    spec["frequency_sweep"] = {"start_hz": 8.0e9, "stop_hz": 12.0e9, "count": 41}
    errors, _warnings = validate_spec(spec)
    assert errors == []
    assert rejection(spec, "hfss") is None
    spec["frequency_sweep"] = {"start_hz": 8.0e9, "stop_hz": 12.0e9, "count": 3}
    assert spectrum_frequencies(spec, 3) == [8.0e9, 10.0e9, 12.0e9]
    path = write_spectrum_csv(tmp_path, spec, {"dB(S(P2,P1))": [0.0, -0.2, -0.1]})
    text = __import__("pathlib").Path(path).read_text(encoding="utf-8")
    assert "frequency_hz" in text.splitlines()[0]
    assert "8e+09" in text or "8000000000" in text


def test_touchstone_keeps_every_frequency_row(tmp_path) -> None:
    from hfss_aedt.engine import touchstone_db, write_spectrum_csv

    path = tmp_path / "sweep.s2p"
    path.write_text(
        "\n".join(
            [
                "! Solution: Setup1 : Sweep1",
                "# GHz S MA R 50",
                "220 0.1 0 0.98 0 0.98 0 0.1 0",
                "300 0.2 0 0.90 0 0.90 0 0.2 0",
            ]
        ),
        encoding="utf-8",
    )
    parsed = touchstone_db(path)
    assert parsed["frequency_hz"] == [220e9, 300e9]
    assert parsed["dB(S(P2,P1))"][0] != parsed["dB(S(P2,P1))"][1]
    spec = _guide()
    spec["frequency_sweep"] = {"start_hz": 220e9, "stop_hz": 300e9, "count": 2}
    csv_path = write_spectrum_csv(tmp_path, spec, parsed)
    text = __import__("pathlib").Path(csv_path).read_text(encoding="utf-8")
    assert "2.2e+11" in text or "220000000000" in text
    assert "3e+11" in text or "300000000000" in text


def test_non_ascii_run_dir_uses_an_ascii_scratch(tmp_path) -> None:
    from hfss_aedt.engine import ascii_workdir, needs_ascii_scratch, publish_ascii, relocated

    public = tmp_path / "中文路径" / "run"
    public.mkdir(parents=True)
    assert needs_ascii_scratch(public) is True
    work, mirrored = ascii_workdir(public)
    assert mirrored == public
    assert needs_ascii_scratch(work) is False
    (work / "model.s2p").write_text("# GHz S MA\n", encoding="utf-8")
    nested = work / "model.aedtresults"
    nested.mkdir()
    (nested / "field.txt").write_text("ok", encoding="utf-8")
    publish_ascii(work, mirrored)
    assert (public / "model.s2p").is_file()
    assert (public / "model.aedtresults" / "field.txt").read_text(encoding="utf-8") == "ok"
    assert relocated(str(work / "model.s2p"), work, public).endswith("model.s2p")
    assert "中文路径" in relocated(str(work / "model.s2p"), work, public)
    __import__("shutil").rmtree(work, ignore_errors=True)


def test_solver_usage_reads_written_tet_count(tmp_path) -> None:
    from hfss_aedt.engine import solver_usage

    folder = tmp_path / "results"
    folder.mkdir()
    (folder / "DV_F80_SU.txt").write_text("NumTets 742\nFrequency 8000000000\n", encoding="utf-8")
    usage = solver_usage(
        folder,
        {"frequency_hz": 1e10, "max_passes": 4, "frequency_sweep": {"count": 3}},
        {"frequency_hz": [8e9, 1e10, 12e9], "dB(S(P2,P1))": [0, 0, 0]},
    )
    assert usage["mesh_tets"] == 742
    assert usage["frequency_count"] == 3
    assert usage["max_passes"] == 4


def test_path_check_flags_a_chinese_onedrive_folder(tmp_path) -> None:
    from sim_plugin.pathcheck import inspect_path

    report = inspect_path(tmp_path / "OneDrive" / "中文")
    assert report["non_ascii"] is True
    assert report["onedrive"] is True
    assert report["notes"]


def test_listed_frequencies_stay_capped_at_21() -> None:
    from sim_plugin.checklist import rejection

    spec = _guide()
    spec["max_passes"] = 4
    spec["max_delta_s"] = 0.02
    spec["frequencies_hz"] = [1.0e10] * 30
    assert rejection(spec, "hfss") is not None


def test_mode_count_above_four_is_rejected() -> None:
    errors, _warnings = validate_spec(_guide(modes=5))
    assert any("modes" in error for error in errors)
