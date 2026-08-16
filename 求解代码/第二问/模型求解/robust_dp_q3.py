from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from math import gcd
from time import perf_counter
from typing import Iterable

from .config import GameConfig, LevelConfig
from .preprocess import bfs_distances
from .transition import (
    Action,
    State,
    apply_action,
    feasible_actions,
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
class Decision:
    action: Action | None
    robust_value: float
    nominal_value: float


@dataclass(frozen=True)
class DailyRecord:
    day: int
    weather: str
    from_node: int
    to_node: int
    action: str
    buy_water: int
    buy_food: int
    cash: int
    water: int
    food: int
    weight: int
    robust_value: float
    nominal_value: float


@dataclass(frozen=True)
class SimulationResult:
    success: bool
    final_state: State
    final_wealth: float | None
    arrival_day: int | None
    records: tuple[DailyRecord, ...]
    error: str | None = None


@dataclass(frozen=True)
class InitialSolution:
    initial_state: State
    robust_value: float
    nominal_value: float
    solver: "AdaptiveRobustSolver"
    runtime_seconds: float
    candidates_checked: int


class AdaptiveRobustSolver:
    """有限期自适应鲁棒 Bellman 求解器。

    ``decide`` 的输入仅含日期、当前状态、当天气和剩余沙暴预算，不接受
    完整未来天气序列；完整序列只由 ``simulate`` 在验证时逐日揭示。
    """

    def __init__(
        self,
        level: LevelConfig,
        game: GameConfig,
        weather_states: tuple[str, ...] = ("晴朗", "高温"),
    ) -> None:
        self.level = level
        self.game = game
        self.weather_states = weather_states
        self.distance_to_goal = bfs_distances(level, level.goal)
        markov_states, matrix = nominal_transition_probabilities(
            HISTORICAL_WEATHER, allowed_states=weather_states
        )
        self._weather_index = {weather: i for i, weather in enumerate(markov_states)}
        self._markov = matrix

    def _allowed_next_weather(self, storm_budget: int) -> tuple[str, ...]:
        if "沙暴" in self.weather_states and storm_budget <= 0:
            return tuple(weather for weather in self.weather_states if weather != "沙暴")
        return self.weather_states

    def _nominal_weights(
        self, current_weather: str, next_weather: tuple[str, ...]
    ) -> dict[str, float]:
        row = self._markov[self._weather_index[current_weather]]
        raw = {weather: row[self._weather_index[weather]] for weather in next_weather}
        total = sum(raw.values())
        if total <= 0:
            return {weather: 1.0 / len(next_weather) for weather in next_weather}
        return {weather: value / total for weather, value in raw.items()}

    @lru_cache(maxsize=None)
    def _value(
        self, day: int, state: State, current_weather: str, storm_budget: int
    ) -> Decision:
        if state.node == self.level.goal:
            wealth = terminal_wealth(state, self.game)
            return Decision(None, wealth, wealth)
        if day > self.game.deadline:
            return Decision(None, NEG_INF, NEG_INF)
        if self.distance_to_goal[state.node] > self.game.deadline - day + 1:
            return Decision(None, NEG_INF, NEG_INF)

        best = Decision(None, NEG_INF, NEG_INF)
        for action in feasible_actions(state, current_weather, self.level):
            try:
                next_state = apply_action(
                    state, action, current_weather, self.level, self.game
                )
            except ValueError:
                continue
            if next_state.node == self.level.goal:
                wealth = terminal_wealth(next_state, self.game)
                candidate = Decision(action, wealth, wealth)
            elif day == self.game.deadline:
                continue
            else:
                next_weather = self._allowed_next_weather(storm_budget)
                branch: dict[str, Decision] = {}
                for weather in next_weather:
                    next_budget = storm_budget - (1 if weather == "沙暴" else 0)
                    branch[weather] = self._value(
                        day + 1, next_state, weather, next_budget
                    )
                if any(item.robust_value == NEG_INF for item in branch.values()):
                    continue
                robust_value = min(item.robust_value for item in branch.values())
                weights = self._nominal_weights(current_weather, next_weather)
                nominal_value = sum(
                    weights[weather] * branch[weather].nominal_value
                    for weather in next_weather
                )
                candidate = Decision(action, robust_value, nominal_value)

            candidate_score = (
                candidate.robust_value,
                candidate.nominal_value,
                action.kind == "挖矿",
                action.kind == "行走",
                -action.destination,
            )
            best_action = best.action or Action("", 10**9)
            best_score = (
                best.robust_value,
                best.nominal_value,
                best_action.kind == "挖矿",
                best_action.kind == "行走",
                -best_action.destination,
            )
            if candidate_score > best_score:
                best = candidate
        return best

    def decide(
        self, day: int, state: State, current_weather: str, storm_budget: int = 0
    ) -> Decision:
        if current_weather not in self.weather_states:
            raise ValueError(f"当前天气 {current_weather} 不在模型天气集合中")
        if storm_budget < 0:
            return Decision(None, NEG_INF, NEG_INF)
        return self._value(day, state, current_weather, storm_budget)

    def simulate(
        self,
        state: State,
        weather_sequence: Iterable[str],
        storm_budget: int = 0,
    ) -> SimulationResult:
        current = state
        records: list[DailyRecord] = []
        remaining_budget = storm_budget
        for day, weather in enumerate(weather_sequence, start=1):
            if day > self.game.deadline or current.node == self.level.goal:
                break
            if weather == "沙暴":
                remaining_budget -= 1
                if remaining_budget < 0:
                    return SimulationResult(
                        False, current, None, None, tuple(records), "天气序列超过沙暴预算"
                    )
            decision = self.decide(day, current, weather, remaining_budget)
            if decision.action is None:
                return SimulationResult(
                    False, current, None, None, tuple(records), f"第{day}天无鲁棒可行动作"
                )
            previous = current
            try:
                current = apply_action(
                    current, decision.action, weather, self.level, self.game
                )
            except ValueError as exc:
                return SimulationResult(
                    False, previous, None, None, tuple(records), f"第{day}天：{exc}"
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
                    robust_value=decision.robust_value,
                    nominal_value=decision.nominal_value,
                )
            )
            if current.node == self.level.goal:
                wealth = terminal_wealth(current, self.game)
                return SimulationResult(True, current, wealth, day, tuple(records))
        return SimulationResult(
            False, current, None, None, tuple(records), "截止日前未到达终点"
        )


def _step_gcd(game: GameConfig, weather_states: tuple[str, ...], resource: int) -> int:
    result = 0
    for weather in weather_states:
        base = game.base_consumption[weather][resource]
        for multiplier in (1, 2, 3):
            result = gcd(result, base * multiplier)
    return max(result, 1)


def solve_initial_purchase(
    level: LevelConfig,
    game: GameConfig,
    weather_states: tuple[str, ...] = ("晴朗", "高温"),
) -> InitialSolution:
    started = perf_counter()
    solver = AdaptiveRobustSolver(level, game, weather_states)
    max_water = min(
        game.capacity_kg // game.water_weight,
        game.deadline * 3 * max(game.base_consumption[w][0] for w in weather_states),
    )
    max_food = min(
        game.capacity_kg // game.food_weight,
        game.deadline * 3 * max(game.base_consumption[w][1] for w in weather_states),
    )
    water_step = _step_gcd(game, weather_states, 0)
    food_step = _step_gcd(game, weather_states, 1)
    initial_probabilities = empirical_initial_probabilities(
        HISTORICAL_WEATHER, weather_states
    )

    best_state: State | None = None
    best_robust = NEG_INF
    best_nominal = NEG_INF
    checked = 0
    for water in range(0, max_water + 1, water_step):
        for food in range(0, max_food + 1, food_step):
            if game.water_weight * water + game.food_weight * food > game.capacity_kg:
                continue
            if game.water_price * water + game.food_price * food > game.initial_cash:
                continue
            state = initial_state(game, level, water, food)
            branches = {
                weather: solver.decide(1, state, weather, storm_budget=0)
                for weather in weather_states
            }
            checked += 1
            if any(item.robust_value == NEG_INF for item in branches.values()):
                continue
            robust = min(item.robust_value for item in branches.values())
            nominal = sum(
                initial_probabilities[weather] * branches[weather].nominal_value
                for weather in weather_states
            )
            score = (robust, nominal, -total_weight(state, game), -water, -food)
            if best_state is None:
                best_score = (NEG_INF, NEG_INF, NEG_INF, NEG_INF, NEG_INF)
            else:
                best_score = (
                    best_robust,
                    best_nominal,
                    -total_weight(best_state, game),
                    -best_state.water,
                    -best_state.food,
                )
            if score > best_score:
                best_state = state
                best_robust = robust
                best_nominal = nominal
    if best_state is None:
        raise RuntimeError(f"{level.name}不存在覆盖全部允许天气的鲁棒初购方案")
    return InitialSolution(
        initial_state=best_state,
        robust_value=best_robust,
        nominal_value=best_nominal,
        solver=solver,
        runtime_seconds=perf_counter() - started,
        candidates_checked=checked,
    )
