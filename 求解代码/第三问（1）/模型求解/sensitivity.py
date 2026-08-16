from __future__ import annotations

from dataclasses import replace
from typing import Iterable

from .config import GameConfig, LevelConfig
from .game_open_loop import find_pure_ne


def _strategy_signature(result) -> str:
    return ";".join(
        f"{record.day}:{record.from_node}-{record.action}-{record.to_node}"
        for record in result.records
    )


def _solve_row(
    label: str,
    value: int | str,
    game: GameConfig,
    level: LevelConfig,
    weather: tuple[str, ...],
    update_order: tuple[int, ...] = (0, 1),
) -> dict[str, object]:
    equilibrium = find_pure_ne(game, level, weather, update_order=update_order)
    return {
        "扫描维度": label,
        "参数值": value,
        "更新顺序": "-".join(str(index + 1) for index in update_order),
        "均衡类型": equilibrium.kind,
        "收敛": equilibrium.converged,
        "迭代次数": equilibrium.iterations,
        "epsilon": equilibrium.exploitability,
        "玩家1财富": equilibrium.player_results[0].terminal_wealth,
        "玩家2财富": equilibrium.player_results[1].terminal_wealth,
        "玩家1到达日": equilibrium.player_results[0].arrival_day,
        "玩家2到达日": equilibrium.player_results[1].arrival_day,
        "玩家1策略": _strategy_signature(equilibrium.player_results[0]),
        "玩家2策略": _strategy_signature(equilibrium.player_results[1]),
    }


def scan_sensitivity(
    game: GameConfig,
    level: LevelConfig,
    weather: tuple[str, ...],
    revenues: Iterable[int] = (0, 100, 200, 300, 400),
    capacities: Iterable[int] = (1000, 1200, 1400),
    initial_cash_values: Iterable[int] = (8000, 10000, 12000),
    update_orders: Iterable[tuple[int, int]] = ((0, 1), (1, 0)),
) -> tuple[dict[str, object], ...]:
    rows: list[dict[str, object]] = []
    for revenue in revenues:
        rows.append(_solve_row("R", revenue, replace(game, mine_income=revenue), level, weather))
    for capacity in capacities:
        rows.append(_solve_row("M", capacity, replace(game, capacity_kg=capacity), level, weather))
    for cash in initial_cash_values:
        rows.append(_solve_row("C0", cash, replace(game, initial_cash=cash), level, weather))
    for order in update_orders:
        if tuple(order) == (0, 1):
            continue
        rows.append(_solve_row("更新顺序", "-".join(map(str, order)), game, level, weather, tuple(order)))
    return tuple(rows)

