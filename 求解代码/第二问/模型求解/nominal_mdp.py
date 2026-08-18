"""名义 Markov-MDP 求解器（建模手册 §2.2、§7）。

风险中性策略：基于题内历史估计的 Markov 转移矩阵 P̂，
按最大化期望终端财富求解。该策略作为"鲁棒 DP"对照基线（手册 §8.5）。

状态：``(t, node, water, food, cash, current_weather)``。
未来天气分布直接由 P̂ 编码（不再需要显式沙暴预算维度），
决策只依赖当前观测。

实现：递归 Bellman + ``@lru_cache`` 记忆化 + 村庄补给闭包。
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from time import perf_counter
from typing import Iterable

from .config import GameConfig, LevelConfig
from .preprocess import bfs_distances
from .robust_dp_q3 import DailyRecord, SimulationResult
from .transition import (
    ACTION_MULTIPLIER,
    Action,
    State,
    apply_action,
    initial_state,
    terminal_wealth,
    total_weight,
)
from .weather_markov import (
    HISTORICAL_WEATHER,
    empirical_initial_probabilities,
    nominal_transition_probabilities,
)


NEG_INF = float("-inf")


@dataclass(frozen=True)
class NominalDecision:
    action: Action | None
    expected_value: float


@dataclass(frozen=True)
class NominalMDPResult:
    """名义 Markov-MDP 求解结果。"""

    level_name: str
    optimal: bool
    status: str
    expected_wealth: float
    initial_state: State
    policy: dict[tuple[int, int, int, int, int, str], Action]
    runtime_seconds: float
    statistics: dict[str, int | float | str]


class NominalMDPSolver:
    """风险中性 Markov-MDP 求解器（手册 §7）。"""

    def __init__(
        self,
        level: LevelConfig,
        game: GameConfig,
        weather_states: tuple[str, ...] = ("晴朗", "高温", "沙暴"),
    ) -> None:
        self.level = level
        self.game = game
        self.weather_states = weather_states
        self.distance_to_goal = bfs_distances(level, level.goal)

        states, matrix = nominal_transition_probabilities(HISTORICAL_WEATHER, allowed_states=weather_states)
        self._states = states
        self._state_index = {w: i for i, w in enumerate(states)}
        self._matrix = matrix

        self._initial_probabilities = empirical_initial_probabilities(HISTORICAL_WEATHER, weather_states)

        self._stats = {
            "nodes_expanded": 0,
            "time_pruned": 0,
            "action_failed": 0,
        }

    def _time_feasible(self, day: int, node: int) -> bool:
        """乐观可行性：BFS 距离 ≤ 剩余天数（最理想天气都能到达）。"""
        return self.distance_to_goal[node] <= self.game.deadline - day + 1

    @lru_cache(maxsize=None)
    def _value(
        self,
        day: int,
        node: int,
        water: int,
        food: int,
        cash: int,
        current_weather: str,
    ) -> NominalDecision:
        if node == self.level.goal:
            z = terminal_wealth(State(node, water, food, cash), self.game)
            return NominalDecision(None, z)
        if day > self.game.deadline:
            return NominalDecision(None, NEG_INF)
        if not self._time_feasible(day, node):
            self._stats["time_pruned"] += 1
            return NominalDecision(None, NEG_INF)

        state = State(node, water, food, cash)
        best = NominalDecision(None, NEG_INF)
        actions = self._legal_actions(state, current_weather)
        for action in actions:
            try:
                next_state = apply_action(state, action, current_weather, self.level, self.game)
            except ValueError:
                self._stats["action_failed"] += 1
                continue
            self._stats["nodes_expanded"] += 1
            # 期望值：对下一日天气分支求值
            exp_value = 0.0
            valid = True
            for next_ω in self._states:
                child = self._value(
                    day + 1, next_state.node, next_state.water, next_state.food,
                    next_state.cash, next_ω,
                )
                if child.expected_value == NEG_INF:
                    valid = False
                    break
                p = float(self._matrix[self._state_index[current_weather], self._state_index[next_ω]])
                exp_value += p * child.expected_value
            if not valid:
                continue
            candidate = NominalDecision(action, exp_value)
            if candidate.expected_value > best.expected_value:
                best = candidate
        return best

    def _legal_actions(self, state: State, weather: str) -> list[Action]:
        if state.node == self.level.goal:
            return []
        actions: list[Action] = [Action("停留", state.node)]
        if state.node in self.level.mines:
            actions.append(Action("挖矿", state.node))
        if weather != "沙暴":
            actions.extend(Action("行走", j) for j in sorted(self.level.neighbors[state.node]))
        return actions

    def decide(self, day: int, state: State, current_weather: str) -> NominalDecision:
        return self._value(day, state.node, state.water, state.food, state.cash, current_weather)

    def simulate(
        self,
        state: State,
        weather_sequence: Iterable[str],
    ) -> SimulationResult:
        """按名义策略仿真（在线决策）。"""
        current = state
        records: list[DailyRecord] = []
        for day, weather in enumerate(weather_sequence, start=1):
            if day > self.game.deadline or current.node == self.level.goal:
                break
            decision = self.decide(day, current, weather)
            if decision.action is None:
                return SimulationResult(
                    False, current, None, None, tuple(records),
                    f"第{day}天无可行动作",
                )
            previous = current
            try:
                current = apply_action(current, decision.action, weather, self.level, self.game)
            except ValueError as exc:
                return SimulationResult(
                    False, previous, None, None, tuple(records),
                    f"第{day}天：{exc}",
                )
            records.append(
                DailyRecord(
                    day=day,
                    weather=weather,
                    from_node=previous.node,
                    to_node=current.node,
                    action=decision.action.kind,
                    buy_water=decision.action.buy_water,
                    buy_food=decision.action.buy_food,
                    cash=current.cash,
                    water=current.water,
                    food=current.food,
                    weight=total_weight(current, self.game),
                    robust_value=float("nan"),
                    nominal_value=decision.expected_value,
                )
            )
            if current.node == self.level.goal:
                z = terminal_wealth(current, self.game)
                return SimulationResult(True, current, z, day, tuple(records))
        return SimulationResult(
            False, current, None, None, tuple(records), "截止日前未到达终点"
        )


def solve_nominal_mdp(
    level: LevelConfig,
    game: GameConfig,
    weather_states: tuple[str, ...] = ("晴朗", "高温", "沙暴"),
    max_water: int | None = None,
    max_food: int | None = None,
) -> NominalMDPResult:
    """枚举初始采购，找使期望财富最大的解。"""
    started = perf_counter()
    solver = NominalMDPSolver(level, game, weather_states=weather_states)
    max_water = max_water or (game.capacity_kg // game.water_weight)
    max_food = max_food or (game.capacity_kg // game.food_weight)

    best_init: State | None = None
    best_value = NEG_INF
    candidates = 0

    for water in range(0, max_water + 1):
        cost_w = game.water_price * water
        if cost_w > game.initial_cash:
            break
        max_f_budget = (game.initial_cash - cost_w) // game.food_price
        max_f_weight = (game.capacity_kg - game.water_weight * water) // game.food_weight
        max_f = min(max_f_budget, max_f_weight, max_food)
        for food in range(0, max_f + 1):
            try:
                init_state = initial_state(game, level, water, food)
            except ValueError:
                continue
            candidates += 1
            exp_value = 0.0
            valid = True
            for ω in weather_states:
                d = solver.decide(1, init_state, ω)
                if d.expected_value == NEG_INF:
                    valid = False
                    break
                p = solver._initial_probabilities[ω]
                exp_value += p * d.expected_value
            if not valid:
                continue
            if exp_value > best_value:
                best_value = exp_value
                best_init = init_state

    if best_init is None:
        raise RuntimeError(f"{level.name}：未找到名义 MDP 期望可行初购方案")

    runtime = perf_counter() - started
    return NominalMDPResult(
        level_name=level.name,
        optimal=True,
        status="名义 Markov-MDP 收敛",
        expected_wealth=best_value,
        initial_state=best_init,
        policy={},  # 通过在线 decide 调用获取
        runtime_seconds=runtime,
        statistics={
            "candidates_checked": candidates,
            **solver._stats,
        },
    )