"""One pre-solve checklist for mesh, passes, convergence, time, and frequency points.

A failed item stops the launch. Items that do not apply to that spec are skipped.
"""

from __future__ import annotations

NAMES = ("mesh", "passes", "convergence", "time", "frequency_points")


def rejection(spec: object, solver: str) -> dict | None:
    target = spec
    if isinstance(spec, dict) and isinstance(spec.get("base"), dict):
        target = spec["base"]
    if not isinstance(target, dict):
        target = {}
    items = _items(target, solver)
    failed = [item["name"] for item in items if item["status"] == "fail"]
    if not failed:
        return None
    return {
        "ok": False,
        "launched_solver": False,
        "stage": "checklist",
        "checklist": items,
        "error": "求解前检查未通过：" + "、".join(failed) + "。",
    }


def _items(spec: dict, solver: str) -> list[dict]:
    if solver == "hfss":
        return _hfss(spec)
    if solver == "fdtd":
        return _fdtd(spec)
    return [
        _skip(name, "网格、自适应、收敛、仿真时间和频点写在 COMSOL 的 Java 里。")
        for name in NAMES
    ]


def _hfss(spec: dict) -> list[dict]:
    owned = not spec.get("project")
    mesh = spec.get("mesh_accuracy", spec.get("mesh accuracy"))
    passes = spec.get("max_passes")
    delta = spec.get("max_delta_s")
    return [
        _range("mesh", mesh, 1, 8, "网格精度", required=False, skipped="这份 HFSS 规格用自适应网格，不单列网格精度。"),
        _range("passes", passes, 1, 20, "自适应次数 max_passes", required=owned, skipped="自适应次数在工程文件里。"),
        _range("convergence", delta, 1e-6, 0.2, "收敛标准 max_delta_s", required=owned, skipped="收敛标准在工程文件里。"),
        _skip("time", "频域求解不使用仿真时间。"),
        _frequency_points(spec, required=owned),
    ]


def _fdtd(spec: dict) -> list[dict]:
    simulation = spec.get("simulation") if isinstance(spec.get("simulation"), dict) else {}
    source = spec.get("global_source") if isinstance(spec.get("global_source"), dict) else {}
    owned = not spec.get("project")
    mesh = simulation.get("mesh accuracy", simulation.get("mesh_accuracy"))
    duration = simulation.get("simulation time", simulation.get("simulation_time"))
    shutoff = simulation.get("auto shutoff min", simulation.get("auto_shutoff_min"))
    has_band = "wavelength start" in source or "wavelength_start" in source
    return [
        _range("mesh", mesh, 1, 8, "网格精度 mesh accuracy", required=owned, skipped="网格精度在工程文件里。"),
        _skip("passes", "FDTD 不用自适应次数。"),
        _range("convergence", shutoff, 1e-9, 0.1, "收敛标准 auto shutoff min", required=False, skipped="未单独设置提前停止。"),
        _range("time", duration, 1e-18, 1e-6, "仿真时间 simulation time", required=owned, skipped="仿真时间在工程文件里。"),
        _pass("frequency_points", "波长范围已给出。") if has_band or not owned else _fail("frequency_points", "需要 global_source 里的波长起止。"),
    ]


def _frequency_points(spec: dict, *, required: bool) -> dict:
    if isinstance(spec.get("frequencies_hz"), list):
        return _range("frequency_points", len(spec["frequencies_hz"]), 1, 21, "频点数量", required=True, skipped="")
    if isinstance(spec.get("frequency_hz"), (int, float)) and not isinstance(spec.get("frequency_hz"), bool):
        return _pass("frequency_points", "1 个频点。")
    if required:
        return _fail("frequency_points", "需要 frequency_hz，或 1 到 21 个 frequencies_hz。")
    return _skip("frequency_points", "频点在工程文件里。")


def _range(name: str, value, low: float, high: float, label: str, *, required: bool, skipped: str) -> dict:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return _fail(name, f"需要{label}，范围 {low:g} 到 {high:g}。") if required else _skip(name, skipped)
    if low <= float(value) <= high:
        return _pass(name, f"{label}={value:g}。")
    return _fail(name, f"{label}={value:g}，需要在 {low:g} 到 {high:g}。")


def _pass(name: str, detail: str) -> dict:
    return {"name": name, "status": "pass", "detail": detail}


def _fail(name: str, detail: str) -> dict:
    return {"name": name, "status": "fail", "detail": detail}


def _skip(name: str, detail: str) -> dict:
    return {"name": name, "status": "skipped", "detail": detail}
