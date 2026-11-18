from sim_plugin.confirm import CORE_ITEMS, STUDY_ITEMS, confirm, rejection
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


def test_study_checklist_requires_the_goal_range_and_limit() -> None:
    result = confirm({"values": [1, 2], "confirmation": {"items": _items()}})
    assert result["ok"] is False
    assert result["missing"] == ["goal", "range", "limit"]
