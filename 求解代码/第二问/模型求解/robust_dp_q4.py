from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from itertools import product
from math import comb
from typing import Iterable

from .config import GameConfig, LevelConfig
from .robust_dp_q3 import DailyRecord, SimulationResult
from .transition import Action, State, apply_action, initial_state, terminal_wealth, total_weight


@dataclass(frozen=True)
class SafeBaselinePlan:
    level: LevelConfig
    game: GameConfig
    gamma: int
    path: tuple[int, ...]
    shortest_steps: int
    initial_state: State
    guaranteed_wealth: float
    model_role: str = "第四关预算鲁棒模型的可行性下界（非全局最优解）"


def allowed_weather(remaining_budget: int) -> tuple[str, ...]:
    if remaining_budget < 0:
        raise ValueError("剩余沙暴预算不能为负")
    return ("晴朗", "高温") if remaining_budget == 0 else ("晴朗", "高温", "沙暴")


def budgeted_scenario_count(days: int, gamma: int) -> int:
    if days < 0 or gamma < 0:
        raise ValueError("天数和沙暴预算必须非负")
    return sum(comb(days, storms) * 2 ** (days - storms) for storms in range(min(days, gamma) + 1))


def enumerate_budgeted_scenarios(
    days: int, gamma: int, max_scenarios: int = 1_000_000
) -> tuple[tuple[str, ...], ...]:
    count = budgeted_scenario_count(days, gamma)
    if count > max_scenarios:
        raise ValueError(
            f"预算情景数 {count} 超过显式枚举上限 {max_scenarios}，应使用动态预算状态"
        )
    return tuple(
        scenario
        for scenario in product(("晴朗", "高温", "沙暴"), repeat=days)
        if scenario.count("沙暴") <= gamma
    )


def _shortest_path(level: LevelConfig) -> tuple[int, ...]:
    parent: dict[int, int | None] = {level.start: None}
    queue = deque([level.start])
    while queue:
        node = queue.popleft()
        if node == level.goal:
            break
        for neighbor in sorted(level.neighbors[node]):
            if neighbor not in parent:
                parent[neighbor] = node
                queue.append(neighbor)
    if level.goal not in parent:
        raise ValueError("起点与终点不连通")
    reversed_path = []
    node: int | None = level.goal
    while node is not None:
        reversed_path.append(node)
        node = parent[node]
    return tuple(reversed(reversed_path))


def build_safe_baseline(
    level: LevelConfig, game: GameConfig, gamma: int
) -> SafeBaselinePlan:
    """构造“沙暴停留、非沙暴沿最短路移动”的可证明安全下界。

    该函数用于验证预算含义和给出第四关可行财富下界，不声称替代含村庄、
    矿山和 Pareto 剪枝的完整最优鲁棒 DP。
    """
    if gamma < 0:
        raise ValueError("沙暴预算必须非负")
    path = _shortest_path(level)
    steps = len(path) - 1
    if steps + gamma > game.deadline:
        raise ValueError("最短移动天数加沙暴等待天数超过截止日")
    nonstorm = ("晴朗", "高温")
    move_water = 2 * max(game.base_consumption[w][0] for w in nonstorm)
    move_food = 2 * max(game.base_consumption[w][1] for w in nonstorm)
    storm_water, storm_food = game.base_consumption["沙暴"]
    water = steps * move_water + gamma * storm_water
    food = steps * move_food + gamma * storm_food
    state = initial_state(game, level, water, food)
    return SafeBaselinePlan(
        level=level,
        game=game,
        gamma=gamma,
        path=path,
        shortest_steps=steps,
        initial_state=state,
        guaranteed_wealth=float(state.cash),
    )


def simulate_safe_baseline(
    plan: SafeBaselinePlan, weather_sequence: Iterable[str]
) -> SimulationResult:
    state = plan.initial_state
    path_index = 0
    storms_used = 0
    records: list[DailyRecord] = []
    for day, weather in enumerate(weather_sequence, start=1):
        if day > plan.game.deadline or state.node == plan.level.goal:
            break
        if weather == "沙暴":
            storms_used += 1
            if storms_used > plan.gamma:
                return SimulationResult(
                    False, state, None, None, tuple(records), "实际沙暴次数超过预算"
                )
            action = Action("停留", state.node)
        else:
            if path_index + 1 >= len(plan.path):
                break
            action = Action("行走", plan.path[path_index + 1])
            path_index += 1
        previous = state
        try:
            state = apply_action(state, action, weather, plan.level, plan.game)
        except ValueError as exc:
            return SimulationResult(
                False, previous, None, None, tuple(records), f"第{day}天：{exc}"
            )
        records.append(
            DailyRecord(
                day=day,
                weather=weather,
                from_node=previous.node,
                to_node=state.node,
                action=action.kind,
                buy_water=0,
                buy_food=0,
                cash=state.cash,
                water=state.water,
                food=state.food,
                weight=total_weight(state, plan.game),
                robust_value=plan.guaranteed_wealth,
                nominal_value=float("nan"),
            )
        )
        if state.node == plan.level.goal:
            return SimulationResult(
                True, state, terminal_wealth(state, plan.game), day, tuple(records)
            )
    return SimulationResult(
        False, state, None, None, tuple(records), "截止日前未到达终点"
    )


def scan_safe_baselines(
    level: LevelConfig, game: GameConfig, gammas: Iterable[int] = range(7)
) -> tuple[SafeBaselinePlan, ...]:
    return tuple(build_safe_baseline(level, game, gamma) for gamma in gammas)
