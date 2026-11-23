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
