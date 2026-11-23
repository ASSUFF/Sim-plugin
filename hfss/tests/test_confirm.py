from sim_plugin.confirm import CORE_ITEMS, STUDY_ITEMS, assumption_lines, confirm, rejection
from hfss_plugin.backend import run


def _items(*, study: bool = False) -> list[dict]:
    names = list(CORE_ITEMS) + (list(STUDY_ITEMS) if study else [])
    return [{"name": name, "source": "specified", "value": name} for name in names]


def test_confirm_returns_the_spec_a_solver_accepts() -> None:
    draft = {"name": "wr90", "frequency_hz": 1e10, "confirmation": {"items": _items()}}
    result = confirm(draft)
    assert result["ok"] is True
    assert result["launched_solver"] is False
    assert rejection(result["spec"]) is None
    changed = dict(result["spec"])
    changed["frequency_hz"] = 2e10
    refused = rejection(changed)
    assert refused is not None
    assert refused["stage"] == "confirm"
    assert refused["launched_solver"] is False


def test_unconfirmed_run_does_not_launch(monkeypatch) -> None:
    def explode(*args, **kwargs):
        raise AssertionError("solver started")

    monkeypatch.setattr("hfss_plugin.backend._engine", explode)
    monkeypatch.setattr("hfss_plugin.backend.license_error", explode)
    result = run({"name": "wr90"})
    assert result["stage"] == "confirm"
    assert result["launched_solver"] is False


def test_assumption_lines_keep_only_assumed_items() -> None:
    spec = {
        "confirmation": {
            "items": [
                {"name": "frequency", "source": "specified", "value": "10 GHz"},
                {"name": "material", "source": "assumed", "value": "vacuum"},
            ]
        }
    }
    assert assumption_lines(spec) == ["material: vacuum"]


def test_sweep_reuses_a_confirmed_base() -> None:
    import copy

    base = confirm({"name": "wr90", "frequency_hz": 1e10, "confirmation": {"items": _items()}})["spec"]
    study_items = [{"name": name, "source": "specified", "value": name} for name in STUDY_ITEMS]
    result = confirm(
        {
            "name": "length",
            "base": base,
            "values": [0.02, 0.03],
            "confirmation": {"items": study_items},
        }
    )
    assert result["ok"] is True
    assert rejection(result["spec"]) is None
    edited = copy.deepcopy(result["spec"])
    edited["base"]["frequency_hz"] = 2e10
    refused = rejection(edited)
    assert refused is not None
    assert refused["stage"] == "confirm"
    stale = copy.deepcopy(base)
    stale["frequency_hz"] = 3e10
    again = confirm({"base": stale, "values": [1, 2], "confirmation": {"items": study_items}})
    assert again["ok"] is False
    assert "frequency" in again["missing"]


def test_study_checklist_requires_the_goal_range_and_limit() -> None:
    result = confirm({"values": [1, 2], "confirmation": {"items": _items()}})
    assert result["ok"] is False
    assert result["missing"] == ["goal", "range", "limit"]
