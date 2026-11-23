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


def test_mode_count_above_four_is_rejected() -> None:
    errors, _warnings = validate_spec(_guide(modes=5))
    assert any("modes" in error for error in errors)
