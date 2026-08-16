from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np

from .config import GameConfig, LevelConfig
from .single_dp import Plan, PlanResult, best_response, evaluate_plan


@dataclass(frozen=True)
class EquilibriumResult:
    kind: str
    profile: tuple[Plan, ...]
    player_results: tuple[PlanResult, ...]
    exploitability: float
    iterations: int
    converged: bool
    cycle_detected: bool
    generated_strategies: tuple[tuple[Plan, ...], ...]


@dataclass(frozen=True)
class MixedEquilibriumResult:
    row_probabilities: tuple[float, ...]
    column_probabilities: tuple[float, ...]
    row_value: float
    column_value: float
    restricted_epsilon: float


def _opponents(profile: Sequence[Plan], player: int) -> tuple[Plan, ...]:
    return tuple(plan for index, plan in enumerate(profile) if index != player)


def _evaluate_profile(
    profile: Sequence[Plan],
    game: GameConfig,
    level: LevelConfig,
    weather: tuple[str, ...],
) -> tuple[PlanResult, ...]:
    return tuple(
        evaluate_plan(profile[player], _opponents(profile, player), game, level, weather)
        for player in range(game.player_count)
    )


def _global_gains(
    profile: Sequence[Plan],
    results: Sequence[PlanResult],
    game: GameConfig,
    level: LevelConfig,
    weather: tuple[str, ...],
) -> tuple[float, ...]:
    gains = []
    for player in range(game.player_count):
        response = best_response(_opponents(profile, player), game, level, weather)
        current = results[player].terminal_wealth
        gains.append(max(0.0, response.terminal_wealth - current))
    return tuple(gains)


def find_pure_ne(
    game: GameConfig,
    level: LevelConfig,
    weather: tuple[str, ...],
    update_order: tuple[int, ...] | None = None,
    initial_profile: Sequence[Plan] | None = None,
    max_iterations: int = 100,
    tolerance: float = 1e-9,
) -> EquilibriumResult:
    if update_order is None:
        update_order = tuple(range(game.player_count))
    if tuple(sorted(update_order)) != tuple(range(game.player_count)):
        raise ValueError("更新顺序必须恰好包含全部玩家")
    if initial_profile is None:
        independent = best_response((), game, level, weather).plan
        profile = [independent for _ in range(game.player_count)]
    else:
        if len(initial_profile) != game.player_count:
            raise ValueError("初始策略数量必须等于玩家数")
        profile = list(initial_profile)

    seen: set[tuple[Plan, ...]] = set()
    generated: list[list[Plan]] = [[] for _ in range(game.player_count)]
    cycle = False
    for iteration in range(1, max_iterations + 1):
        key = tuple(profile)
        if key in seen:
            cycle = True
            break
        seen.add(key)
        for player, plan in enumerate(profile):
            if plan not in generated[player]:
                generated[player].append(plan)

        changed = False
        for player in update_order:
            others = _opponents(profile, player)
            current = evaluate_plan(profile[player], others, game, level, weather)
            response = best_response(others, game, level, weather)
            if (not current.feasible) or response.terminal_wealth > current.terminal_wealth + tolerance:
                profile[player] = response.plan
                if response.plan not in generated[player]:
                    generated[player].append(response.plan)
                changed = True

        results = _evaluate_profile(profile, game, level, weather)
        gains = _global_gains(profile, results, game, level, weather)
        epsilon = max(gains, default=0.0)
        if epsilon <= tolerance:
            return EquilibriumResult(
                kind="pure",
                profile=tuple(profile),
                player_results=results,
                exploitability=epsilon,
                iterations=iteration,
                converged=True,
                cycle_detected=False,
                generated_strategies=tuple(tuple(items) for items in generated),
            )
        if not changed:
            break

    results = _evaluate_profile(profile, game, level, weather)
    gains = _global_gains(profile, results, game, level, weather)
    return EquilibriumResult(
        kind="unresolved",
        profile=tuple(profile),
        player_results=results,
        exploitability=max(gains, default=float("inf")),
        iterations=min(max_iterations, len(seen)),
        converged=False,
        cycle_detected=cycle,
        generated_strategies=tuple(tuple(items) for items in generated),
    )


def solve_restricted_mixed(
    row_strategies: Sequence[Plan],
    column_strategies: Sequence[Plan],
    game: GameConfig,
    level: LevelConfig,
    weather: tuple[str, ...],
    tolerance: float = 1e-8,
) -> MixedEquilibriumResult:
    """求两人受限战略式博弈的混合均衡，并复核受限集 exploitability。"""
    try:
        import nashpy as nash
    except ImportError as exc:  # pragma: no cover - depends on optional runtime
        raise RuntimeError("混合均衡兜底需要安装 nashpy") from exc

    row_payoff = np.empty((len(row_strategies), len(column_strategies)))
    column_payoff = np.empty_like(row_payoff)
    for r, row in enumerate(row_strategies):
        for c, column in enumerate(column_strategies):
            row_payoff[r, c] = evaluate_plan(row, (column,), game, level, weather).terminal_wealth
            column_payoff[r, c] = evaluate_plan(column, (row,), game, level, weather).terminal_wealth
    candidates = list(nash.Game(row_payoff, column_payoff).support_enumeration())
    if not candidates:
        raise RuntimeError("受限博弈未取得混合均衡")
    for row_prob, column_prob in candidates:
        row_values = row_payoff @ column_prob
        column_values = row_prob @ column_payoff
        row_value = float(row_prob @ row_values)
        column_value = float(column_values @ column_prob)
        epsilon = max(float(np.max(row_values) - row_value), float(np.max(column_values) - column_value), 0.0)
        if epsilon <= tolerance:
            return MixedEquilibriumResult(
                tuple(float(x) for x in row_prob),
                tuple(float(x) for x in column_prob),
                row_value,
                column_value,
                epsilon,
            )
    raise RuntimeError("混合均衡未通过受限集偏离检验")

