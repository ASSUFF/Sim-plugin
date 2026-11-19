"""Cartesian product for a sweep. The total is capped at 8 before any solver starts."""

from __future__ import annotations

MAX_RUNS = 8


def combinations(grid: object) -> tuple[list[dict], str | None]:
    if not isinstance(grid, dict) or not grid:
        return [], "sweep 需要是非空对象，键是参数名，值是取值数组。"
    names: list[str] = []
    columns: list[list] = []
    for name, values in grid.items():
        if not isinstance(name, str) or not name.strip():
            return [], "sweep 的参数名需要是非空字符串。"
        if not isinstance(values, list) or not 2 <= len(values) <= MAX_RUNS:
            return [], f"参数 {name} 的扫描取值需要 2 到 {MAX_RUNS} 个。"
        names.append(name)
        columns.append(list(values))
    rows: list[dict] = [{}]
    for name, column in zip(names, columns):
        rows = [{**row, name: value} for row in rows for value in column]
    if len(rows) > MAX_RUNS:
        return [], f"扫描组合有 {len(rows)} 个，超过上限 {MAX_RUNS}。请减少取值。"
    return rows, None
