#!/usr/bin/env python3
"""
2020B 第二问
"""

from __future__ import annotations

import csv
import json
from collections import deque, Counter
from dataclasses import dataclass, replace, asdict
from datetime import datetime
from functools import lru_cache
from itertools import product
from math import gcd, comb
from pathlib import Path
from time import perf_counter
from typing import Mapping, Tuple, List, Dict, Optional, Iterable, Sequence
import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_matrix


# config - 配置参数和地图定义

print()
print("config - 配置参数和地图定义")
print()

Weather = str


@dataclass(frozen=True)
class GameConfig:
    capacity_kg: int
    initial_cash: int
    deadline: int
    mine_income: int
    water_weight: int
    food_weight: int
    water_price: int
    food_price: int
    base_consumption: Mapping[Weather, tuple[int, int]]


@dataclass(frozen=True)
class LevelConfig:
    name: str
    node_count: int
    edges: tuple[tuple[int, int], ...]
    neighbors: Mapping[int, frozenset[int]]
    start: int
    goal: int
    villages: frozenset[int]
    mines: frozenset[int]


BASE_CONSUMPTION = {"晴朗": (3, 4), "高温": (9, 9), "沙暴": (10, 10)}

LEVEL_THREE_GAME = GameConfig(
    capacity_kg=1200,
    initial_cash=10000,
    deadline=10,
    mine_income=200,
    water_weight=3,
    food_weight=2,
    water_price=5,
    food_price=10,
    base_consumption=BASE_CONSUMPTION,
)

LEVEL_FOUR_GAME = GameConfig(
    capacity_kg=1200,
    initial_cash=10000,
    deadline=30,
    mine_income=1000,
    water_weight=3,
    food_weight=2,
    water_price=5,
    food_price=10,
    base_consumption=BASE_CONSUMPTION,
)

LEVEL_THREE_EDGES = (
    (1, 2), (1, 4), (1, 5),
    (2, 3), (2, 4),
    (3, 4), (3, 8), (3, 9),
    (4, 5), (4, 6), (4, 7),
    (5, 6),
    (6, 7), (6, 12), (6, 13),
    (7, 11), (7, 12),
    (8, 9),
    (9, 10), (9, 11),
    (10, 11), (10, 13),
    (11, 12), (11, 13),
    (12, 13),
)


def _grid_edges(rows: int, cols: int) -> tuple[tuple[int, int], ...]:
    edges: list[tuple[int, int]] = []
    for node in range(1, rows * cols + 1):
        row, col = divmod(node - 1, cols)
        if col + 1 < cols:
            edges.append((node, node + 1))
        if row + 1 < rows:
            edges.append((node, node + cols))
    return tuple(edges)


LEVEL_FOUR_EDGES = _grid_edges(5, 5)


def _make_level(
    name: str,
    node_count: int,
    edges: tuple[tuple[int, int], ...],
    start: int,
    goal: int,
    villages: frozenset[int],
    mines: frozenset[int],
) -> LevelConfig:
    normalized = tuple(sorted((min(i, j), max(i, j)) for i, j in edges))
    adjacency = {node: set() for node in range(1, node_count + 1)}
    for i, j in normalized:
        adjacency[i].add(j)
        adjacency[j].add(i)
    return LevelConfig(
        name=name,
        node_count=node_count,
        edges=normalized,
        neighbors={node: frozenset(items) for node, items in adjacency.items()},
        start=start,
        goal=goal,
        villages=villages,
        mines=mines,
    )


def build_level_three() -> LevelConfig:
    return _make_level(
        "第三关", 13, LEVEL_THREE_EDGES, 1, 13, frozenset(), frozenset({9})
    )


def build_level_four() -> LevelConfig:
    return _make_level(
        "第四关", 25, LEVEL_FOUR_EDGES, 1, 25, frozenset({14}), frozenset({18})
    )


# rules - 行动规则和状态转移

print()
print("rules - 行动规则和状态转移")
print()

ACTION_MULTIPLIER = {"停留": 1, "行走": 2, "挖矿": 3}


@dataclass(frozen=True, order=True)
class State:
    node: int
    water: int
    food: int
    cash: int


@dataclass(frozen=True, order=True)
class Action:
    kind: str
    destination: int
    buy_water: int = 0
    buy_food: int = 0


def total_weight(state: State, game: GameConfig) -> int:
    return game.water_weight * state.water + game.food_weight * state.food


def terminal_wealth(state: State, game: GameConfig) -> float:
    return (
        state.cash
        + 0.5 * game.water_price * state.water
        + 0.5 * game.food_price * state.food
    )


def initial_state(
    game: GameConfig, level: LevelConfig, water: int, food: int
) -> State:
    if not isinstance(water, int) or not isinstance(food, int) or min(water, food) < 0:
        raise ValueError("初始采购量必须为非负整数箱")
    state = State(
        node=level.start,
        water=water,
        food=food,
        cash=game.initial_cash - game.water_price * water - game.food_price * food,
    )
    if state.cash < 0:
        raise ValueError("初始采购导致资金为负")
    if total_weight(state, game) > game.capacity_kg:
        raise ValueError("初始采购超过负重上限")
    return state


def feasible_actions(
    state: State, weather: str, level: LevelConfig
) -> tuple[Action, ...]:
    if state.node == level.goal:
        return ()
    actions = [Action("停留", state.node)]
    if state.node in level.mines:
        actions.append(Action("挖矿", state.node))
    if weather != "沙暴":
        actions.extend(Action("行走", node) for node in sorted(level.neighbors[state.node]))
    return tuple(actions)


def _validate_purchase(state: State, action: Action, level: LevelConfig) -> None:
    if not isinstance(action.buy_water, int) or not isinstance(action.buy_food, int):
        raise ValueError("购买量必须为整数箱")
    if action.buy_water < 0 or action.buy_food < 0:
        raise ValueError("购买量必须非负")
    if (action.buy_water or action.buy_food) and state.node not in level.villages:
        raise ValueError("当前不在村庄，不能购买资源")


def apply_action(
    state: State,
    action: Action,
    weather: str,
    level: LevelConfig,
    game: GameConfig,
) -> State:
    if weather not in game.base_consumption:
        raise ValueError(f"未知天气：{weather}")
    _validate_purchase(state, action, level)

    cash = state.cash - 2 * (
        game.water_price * action.buy_water + game.food_price * action.buy_food
    )
    purchased = State(
        node=state.node,
        water=state.water + action.buy_water,
        food=state.food + action.buy_food,
        cash=cash,
    )
    if purchased.cash < 0:
        raise ValueError("购买导致资金为负")
    if total_weight(purchased, game) > game.capacity_kg:
        raise ValueError("购买导致负重超过上限")

    legal = False
    if action.kind == "停留":
        legal = action.destination == state.node
    elif action.kind == "挖矿":
        legal = action.destination == state.node and state.node in level.mines
    elif action.kind == "行走":
        legal = weather != "沙暴" and action.destination in level.neighbors[state.node]
    if not legal:
        raise ValueError(f"非法行动：{action}")

    base_water, base_food = game.base_consumption[weather]
    multiplier = ACTION_MULTIPLIER[action.kind]
    water = purchased.water - multiplier * base_water
    food = purchased.food - multiplier * base_food
    if water < 0 or food < 0:
        raise ValueError("行动所需资源不足")
    next_cash = purchased.cash + (game.mine_income if action.kind == "挖矿" else 0)
    return State(action.destination, water, food, next_cash)


# weather_markov - 天气 Markov 模型

print()
print("weather_markov - 天气 Markov 模型")
print()

WEATHER_STATES = ("晴朗", "高温", "沙暴")
HISTORICAL_WEATHER = (
    "高温", "高温", "晴朗", "沙暴", "晴朗", "高温", "沙暴", "晴朗", "高温", "高温",
    "沙暴", "高温", "晴朗", "高温", "高温", "高温", "沙暴", "沙暴", "高温", "高温",
    "晴朗", "晴朗", "高温", "晴朗", "沙暴", "高温", "晴朗", "晴朗", "高温", "高温",
)


def estimate_transition_counts(
    weather: Sequence[str], states: tuple[str, ...] = WEATHER_STATES
) -> tuple[tuple[str, ...], np.ndarray]:
    if len(weather) < 2:
        raise ValueError("至少需要两天天气才能统计转移")
    index = {state: i for i, state in enumerate(states)}
    unknown = set(weather) - set(states)
    if unknown:
        raise ValueError(f"存在未知天气状态：{sorted(unknown)}")
    counts = np.zeros((len(states), len(states)), dtype=int)
    for current, following in zip(weather, weather[1:]):
        counts[index[current], index[following]] += 1
    return states, counts


def nominal_transition_probabilities(
    weather: Sequence[str] = HISTORICAL_WEATHER,
    allowed_states: tuple[str, ...] = WEATHER_STATES,
) -> tuple[tuple[str, ...], np.ndarray]:
    states, counts = estimate_transition_counts(weather)
    source_index = {state: i for i, state in enumerate(states)}
    selected = np.asarray(
        [[counts[source_index[i], source_index[j]] for j in allowed_states] for i in allowed_states],
        dtype=float,
    )
    row_sums = selected.sum(axis=1)
    if np.any(row_sums == 0):
        raise ValueError("允许天气集合中存在没有历史转移的状态")
    return allowed_states, selected / row_sums[:, None]


def empirical_initial_probabilities(
    weather: Sequence[str], allowed_states: tuple[str, ...]
) -> dict[str, float]:
    counts = {state: sum(item == state for item in weather) for state in allowed_states}
    total = sum(counts.values())
    if total == 0:
        probability = 1.0 / len(allowed_states)
        return {state: probability for state in allowed_states}
    return {state: count / total for state, count in counts.items()}


def enumerate_weather_scenarios(
    days: int, states: Iterable[str]
) -> tuple[tuple[str, ...], ...]:
    if days < 0:
        raise ValueError("天数不能为负")
    state_tuple = tuple(states)
    if not state_tuple:
        raise ValueError("天气状态集合不能为空")
    return tuple(product(state_tuple, repeat=days))


# preprocess - 地图预处理和验证

print()
print("preprocess - 地图预处理和验证")
print()


@dataclass(frozen=True)
class ValidationReport:
    ok: bool
    errors: tuple[str, ...]


def bfs_distances(level: LevelConfig, target: int) -> dict[int, int]:
    if target not in level.neighbors:
        raise ValueError(f"目标节点 {target} 超出地图范围")
    distances = {target: 0}
    queue = deque([target])
    while queue:
        node = queue.popleft()
        for neighbor in level.neighbors[node]:
            if neighbor not in distances:
                distances[neighbor] = distances[node] + 1
                queue.append(neighbor)
    return distances


def validate_level(level: LevelConfig) -> ValidationReport:
    errors: list[str] = []
    valid_nodes = set(range(1, level.node_count + 1))
    if level.start not in valid_nodes or level.goal not in valid_nodes:
        errors.append("起点或终点超出节点范围")
    if not level.villages <= valid_nodes or not level.mines <= valid_nodes:
        errors.append("村庄或矿山节点超出节点范围")
    if len(level.edges) != len(set(level.edges)):
        errors.append("邻接边存在重复")
    for i, j in level.edges:
        if i == j:
            errors.append(f"存在自环 {i}-{j}")
        if i not in valid_nodes or j not in valid_nodes:
            errors.append(f"边 {i}-{j} 超出节点范围")
        elif j not in level.neighbors[i] or i not in level.neighbors[j]:
            errors.append(f"邻接关系 {i}-{j} 不对称")
    if level.start in valid_nodes and level.goal in valid_nodes:
        if level.goal not in bfs_distances(level, level.start):
            errors.append("起点与终点不连通")
    return ValidationReport(not errors, tuple(errors))


# pareto_utils - Pareto 剪枝工具

print()
print("pareto_utils - Pareto 剪枝工具")
print()


def pareto_prune_3d(
    labels: dict[tuple[int, int, int], float],
    threshold: int = 10_000,
) -> dict[tuple[int, int, int], float]:
    if not labels:
        return labels
    best: dict[tuple[int, int, int], float] = {}
    for key, score in labels.items():
        existing = best.get(key)
        if existing is None or score > existing:
            best[key] = score
    if len(best) > threshold:
        return best
    items = sorted(best.items(), key=lambda kv: (-kv[0][0], -kv[1], kv[0][1]))
    kept: dict[tuple[int, int, int], float] = {}
    front_f: list[int] = []
    front_cash: list[int] = []
    for key, score in items:
        w, f, cash = key
        dominated = False
        for ff, fc in zip(front_f, front_cash):
            if ff >= f and fc >= cash and (ff > f or fc > cash):
                dominated = True
                break
        if dominated:
            continue
        new_f: list[int] = []
        new_c: list[int] = []
        for ff, fc in zip(front_f, front_cash):
            if not (ff <= f and fc <= cash):
                new_f.append(ff)
                new_c.append(fc)
        front_f = new_f
        front_cash = new_c
        front_f.append(f)
        front_cash.append(cash)
        kept[key] = score
    return kept


def optimistic_upper_bound_3d(
    water: int,
    food: int,
    cash: int,
    deadline: int,
    current_day: int,
    water_price: int,
    food_price: int,
    mine_income: int,
) -> float:
    remaining_days = deadline - current_day
    return (
        cash
        + 0.5 * water_price * water
        + 0.5 * food_price * food
        + remaining_days * mine_income
    )


def optimistic_upper_bound_4d(
    water: int,
    food: int,
    cash: int,
    deadline: int,
    current_day: int,
    water_price: int,
    food_price: int,
    mine_income: int,
    storm_budget: int,
    storm_factor: float = 1.0,
) -> float:
    base = optimistic_upper_bound_3d(
        water,
        food,
        cash,
        deadline,
        current_day,
        water_price,
        food_price,
        mine_income,
    )
    return base + storm_budget * storm_factor * mine_income


# robust_dp_q3 - 第三关自适应鲁棒 DP 求解器

print()
print("robust_dp_q3 - 第三关自适应鲁棒 DP 求解器")
print()

NEG_INF = float("-inf")


@dataclass(frozen=True)
class Q3Decision:
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
class Q3SimulationResult:
    success: bool
    final_state: State
    final_wealth: float | None
    arrival_day: int | None
    records: tuple[DailyRecord, ...]
    error: str | None = None


@dataclass(frozen=True)
class Q3InitialSolution:
    initial_state: State
    robust_value: float
    nominal_value: float
    solver: "AdaptiveRobustSolver"
    runtime_seconds: float
    candidates_checked: int


class AdaptiveRobustSolver:
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
    ) -> Q3Decision:
        if state.node == self.level.goal:
            wealth = terminal_wealth(state, self.game)
            return Q3Decision(None, wealth, wealth)
        if day > self.game.deadline:
            return Q3Decision(None, NEG_INF, NEG_INF)
        if self.distance_to_goal[state.node] > self.game.deadline - day + 1:
            return Q3Decision(None, NEG_INF, NEG_INF)

        best = Q3Decision(None, NEG_INF, NEG_INF)
        for action in feasible_actions(state, current_weather, self.level):
            try:
                next_state = apply_action(
                    state, action, current_weather, self.level, self.game
                )
            except ValueError:
                continue
            if next_state.node == self.level.goal:
                wealth = terminal_wealth(next_state, self.game)
                candidate = Q3Decision(action, wealth, wealth)
            elif day == self.game.deadline:
                continue
            else:
                next_weather = self._allowed_next_weather(storm_budget)
                branch: dict[str, Q3Decision] = {}
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
                candidate = Q3Decision(action, robust_value, nominal_value)

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
    ) -> Q3Decision:
        if current_weather not in self.weather_states:
            raise ValueError(f"当前天气 {current_weather} 不在模型天气集合中")
        if storm_budget < 0:
            return Q3Decision(None, NEG_INF, NEG_INF)
        return self._value(day, state, current_weather, storm_budget)

    def simulate(
        self,
        state: State,
        weather_sequence: Iterable[str],
        storm_budget: int = 0,
    ) -> Q3SimulationResult:
        current = state
        records: list[DailyRecord] = []
        remaining_budget = storm_budget
        for day, weather in enumerate(weather_sequence, start=1):
            if day > self.game.deadline or current.node == self.level.goal:
                break
            if weather == "沙暴":
                remaining_budget -= 1
                if remaining_budget < 0:
                    return Q3SimulationResult(
                        False, current, None, None, tuple(records), "天气序列超过沙暴预算"
                    )
            decision = self.decide(day, current, weather, remaining_budget)
            if decision.action is None:
                return Q3SimulationResult(
                    False, current, None, None, tuple(records), f"第{day}天无鲁棒可行动作"
                )
            previous = current
            try:
                current = apply_action(
                    current, decision.action, weather, self.level, self.game
                )
            except ValueError as exc:
                return Q3SimulationResult(
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
                return Q3SimulationResult(True, current, wealth, day, tuple(records))
        return Q3SimulationResult(
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
) -> Q3InitialSolution:
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
    return Q3InitialSolution(
        initial_state=best_state,
        robust_value=best_robust,
        nominal_value=best_nominal,
        solver=solver,
        runtime_seconds=perf_counter() - started,
        candidates_checked=checked,
    )


def verify_with_dp(
    milp_robust_value: float,
    level: LevelConfig,
    game: GameConfig,
    weather_states: tuple[str, ...] = ("晴朗", "高温"),
    initial_state: State | None = None,
    tolerance: float = 1e-6,
) -> tuple[bool, float, float]:
    solver = AdaptiveRobustSolver(level, game, weather_states)
    if initial_state is None:
        solution = solve_initial_purchase(level, game, weather_states)
        init = solution.initial_state
    else:
        init = initial_state
    branches = [
        solver.decide(1, init, weather, storm_budget=0)
        for weather in weather_states
    ]
    if any(b.robust_value == NEG_INF for b in branches):
        return False, float("inf"), float("-inf")
    dp_robust = min(b.robust_value for b in branches)
    diff = abs(dp_robust - milp_robust_value)
    return diff < tolerance, diff, dp_robust


# robust_dp_q4 - 第四关完整自适应鲁棒 DP 求解器

print()
print("robust_dp_q4 - 第四关完整自适应鲁棒 DP 求解器")
print()


@dataclass(frozen=True)
class Q4SafeBaselinePlan:
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
) -> Q4SafeBaselinePlan:
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
    return Q4SafeBaselinePlan(
        level=level,
        game=game,
        gamma=gamma,
        path=path,
        shortest_steps=steps,
        initial_state=state,
        guaranteed_wealth=float(state.cash),
    )


def simulate_safe_baseline(
    plan: Q4SafeBaselinePlan, weather_sequence: Iterable[str]
) -> Q3SimulationResult:
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
                return Q3SimulationResult(
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
            return Q3SimulationResult(
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
            return Q3SimulationResult(
                True, state, terminal_wealth(state, plan.game), day, tuple(records)
            )
    return Q3SimulationResult(
        False, state, None, None, tuple(records), "截止日前未到达终点"
    )


def scan_safe_baselines(
    level: LevelConfig, game: GameConfig, gammas: Iterable[int] = range(7)
) -> tuple[Q4SafeBaselinePlan, ...]:
    return tuple(build_safe_baseline(level, game, gamma) for gamma in gammas)


@dataclass(frozen=True)
class Q4HighSafetyPlan:
    level: LevelConfig
    game: GameConfig
    gamma: int
    initial_state: State
    path: tuple[int, ...]
    shortest_steps: int
    safety_threshold: int
    buffer: int
    guaranteed_min_wealth: float
    model_role: str = "第四关高安全库存保守基线（不挖矿、起点超量采购）"

    @property
    def guaranteed_wealth(self) -> float:
        return self.guaranteed_min_wealth


def build_high_safety_baseline(
    level: LevelConfig,
    game: GameConfig,
    gamma: int,
    safety_threshold: int = 18,
    buffer: int = 30,
) -> Q4HighSafetyPlan:
    if gamma < 0:
        raise ValueError("沙暴预算必须非负")
    path = _shortest_path(level)
    steps = len(path) - 1
    nonstorm = ("晴朗", "高温")
    move_water = 2 * max(game.base_consumption[w][0] for w in nonstorm)
    move_food = 2 * max(game.base_consumption[w][1] for w in nonstorm)
    storm_water, storm_food = game.base_consumption["沙暴"]
    water = steps * move_water + gamma * storm_water + buffer
    food = steps * move_food + gamma * storm_food + buffer
    state = initial_state(game, level, water, food)
    return Q4HighSafetyPlan(
        level=level,
        game=game,
        gamma=gamma,
        initial_state=state,
        path=path,
        shortest_steps=steps,
        safety_threshold=safety_threshold,
        buffer=buffer,
        guaranteed_min_wealth=float(state.cash),
    )


def simulate_high_safety(
    plan: Q4HighSafetyPlan,
    weather_sequence: Iterable[str],
) -> Q3SimulationResult:
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
                return Q3SimulationResult(
                    False, state, None, None, tuple(records),
                    "实际沙暴次数超过预算"
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
            return Q3SimulationResult(
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
                robust_value=plan.guaranteed_min_wealth,
                nominal_value=float("nan"),
            )
        )
        if state.node == plan.level.goal:
            return Q3SimulationResult(
                True, state, terminal_wealth(state, plan.game), day, tuple(records)
            )
    return Q3SimulationResult(
        False, state, None, None, tuple(records), "截止日前未到达终点"
    )


@dataclass(frozen=True)
class Q4Decision:
    action: Action | None
    robust_value: float
    nominal_value: float
    prev: (
        tuple[int, int, int, int, int, str, int, str, int, int, int] | None
    ) = None


@dataclass(frozen=True)
class Q4AdaptiveBudgetRobustResult:
    optimal: bool
    status: str
    final_wealth: float
    arrival_day: int
    initial_state: State
    policy: dict[tuple[int, int, int, int, int, str, int], Action]
    robust_value: float
    nominal_value: float
    runtime_seconds: float
    statistics: dict[str, int | float | str]


class Q4AdaptiveBudgetRobustSolver:
    def __init__(
        self,
        level: LevelConfig,
        game: GameConfig,
        gamma: int,
    ) -> None:
        if gamma < 0:
            raise ValueError("沙暴预算必须非负")
        self.level = level
        self.game = game
        self.gamma = gamma
        self.distance_to_goal = bfs_distances(level, level.goal)

        full_states, full_matrix = nominal_transition_probabilities(
            HISTORICAL_WEATHER, allowed_states=("晴朗", "高温", "沙暴")
        )
        self._full_states = full_states
        self._full_index = {w: i for i, w in enumerate(full_states)}
        self._full_matrix = full_matrix

        sh_states, sh_matrix = nominal_transition_probabilities(
            HISTORICAL_WEATHER, allowed_states=("晴朗", "高温")
        )
        self._sh_states = sh_states
        self._sh_index = {w: i for i, w in enumerate(sh_states)}
        self._sh_matrix = sh_matrix

        self._stats = {
            "nodes_expanded": 0,
            "time_pruned": 0,
            "revenue_pruned": 0,
            "terminal_at_goal": 0,
            "action_failed": 0,
        }

    def _next_weather_states(self, b: int) -> tuple[str, ...]:
        return allowed_weather(b)

    def _next_weight(self, cur_weather: str, next_weather: str, b: int) -> float:
        if b <= 0:
            if cur_weather in self._sh_index:
                row = self._sh_matrix[self._sh_index[cur_weather]]
                return float(row[self._sh_index[next_weather]])
            full_row = self._full_matrix[self._full_index[cur_weather]]
            sh_indices = [self._full_index[w] for w in self._sh_states]
            vals = [full_row[i] for i in sh_indices]
            total = sum(vals)
            return float(vals[self._sh_index[next_weather]] / total) if total > 0 else 1.0 / len(self._sh_states)
        row = self._full_matrix[self._full_index[cur_weather]]
        return float(row[self._full_index[next_weather]])

    def _value(
        self,
        day: int,
        node: int,
        water: int,
        food: int,
        cash: int,
        current_weather: str,
        storm_budget: int,
    ) -> Q4Decision:
        if storm_budget < 0:
            return Q4Decision(None, NEG_INF, NEG_INF, None)
        if storm_budget == 0 and current_weather == "沙暴":
            return Q4Decision(None, NEG_INF, NEG_INF, None)
        if node == self.level.goal:
            z = terminal_wealth(State(node, water, food, cash), self.game)
            return Q4Decision(None, z, z, None)
        if day > self.game.deadline:
            return Q4Decision(None, NEG_INF, NEG_INF, None)
        today_moves = 0 if current_weather == "沙暴" else 1
        future_budget = storm_budget - (1 if current_weather == "沙暴" else 0)
        future_moves = max(0, (self.game.deadline - day) - future_budget)
        moves_possible = today_moves + future_moves
        if self.distance_to_goal[node] > moves_possible:
            self._stats["time_pruned"] += 1
            return Q4Decision(None, NEG_INF, NEG_INF, None)
        if water < 0 or food < 0:
            return Q4Decision(None, NEG_INF, NEG_INF, None)

        state = State(node, water, food, cash)
        best: Q4Decision = Q4Decision(None, NEG_INF, NEG_INF, None)
        actions = self._legal_actions_q4(state, current_weather)
        for action in actions:
            try:
                next_state = apply_action(state, action, current_weather, self.level, self.game)
            except ValueError:
                self._stats["action_failed"] += 1
                continue

            self._stats["nodes_expanded"] += 1

            if next_state.node == self.level.goal:
                z = terminal_wealth(next_state, self.game)
                candidate = Q4Decision(
                    action, z, z,
                    (day, node, water, food, cash, current_weather, storm_budget,
                     action.kind, action.buy_water, action.buy_food, action.destination),
                )
                self._stats["terminal_at_goal"] += 1
            else:
                future_storm_budget = storm_budget - (1 if current_weather == "沙暴" else 0)
                next_ws = self._next_weather_states(future_storm_budget)
                branch_robust: list = []
                branch_nominal_num = 0.0
                infeasible = False
                raw_weights = {
                    next_ω: self._next_weight(current_weather, next_ω, storm_budget)
                    for next_ω in next_ws
                }
                weight_total = sum(raw_weights.values())
                cond_weights = (
                    {w: v / weight_total for w, v in raw_weights.items()}
                    if weight_total > 0
                    else {w: 1.0 / len(next_ws) for w in next_ws}
                )
                for next_ω in next_ws:
                    child = self._value(
                        day + 1, next_state.node, next_state.water, next_state.food,
                        next_state.cash, next_ω, future_storm_budget,
                    )
                    if child.robust_value == NEG_INF:
                        infeasible = True
                        break
                    branch_robust.append(child.robust_value)
                    branch_nominal_num += cond_weights[next_ω] * child.nominal_value
                if infeasible:
                    continue
                robust_val = min(branch_robust)
                nominal_val = branch_nominal_num
                candidate = Q4Decision(
                    action, robust_val, nominal_val,
                    (day, node, water, food, cash, current_weather, storm_budget,
                     action.kind, action.buy_water, action.buy_food, action.destination),
                )

            if (
                candidate.robust_value,
                candidate.nominal_value,
            ) > (best.robust_value, best.nominal_value):
                best = candidate

        return best

    def _legal_actions_q4(self, state: State, weather: str) -> list[Action]:
        if state.node == self.level.goal:
            return []
        actions: list[Action] = [Action("停留", state.node)]
        if state.node in self.level.mines:
            actions.append(Action("挖矿", state.node))
        if weather != "沙暴":
            actions.extend(Action("行走", j) for j in sorted(self.level.neighbors[state.node]))
        return actions

    def decide(
        self, day: int, state: State, current_weather: str, storm_budget: int = 0
    ) -> Q4Decision:
        if storm_budget < 0:
            return Q4Decision(None, NEG_INF, NEG_INF, None)
        return self._value(
            day, state.node, state.water, state.food, state.cash,
            current_weather, storm_budget,
        )

    def simulate(
        self,
        state: State,
        weather_sequence: Iterable[str],
        storm_budget: int = 0,
    ) -> Q3SimulationResult:
        current = state
        records: list[DailyRecord] = []
        remaining = storm_budget
        for day, weather in enumerate(weather_sequence, start=1):
            if day > self.game.deadline or current.node == self.level.goal:
                break
            if weather == "沙暴":
                remaining -= 1
                if remaining < 0:
                    return Q3SimulationResult(
                        False, current, None, None, tuple(records),
                        "天气序列超过沙暴预算",
                    )
            decision = self.decide(day, current, weather, remaining)
            if decision.action is None:
                return Q3SimulationResult(
                    False, current, None, None, tuple(records),
                    f"第{day}天无鲁棒可行动作",
                )
            previous = current
            try:
                current = apply_action(
                    current, decision.action, weather, self.level, self.game
                )
            except ValueError as exc:
                return Q3SimulationResult(
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
                    robust_value=decision.robust_value,
                    nominal_value=decision.nominal_value,
                )
            )
            if current.node == self.level.goal:
                z = terminal_wealth(current, self.game)
                return Q3SimulationResult(True, current, z, day, tuple(records))
        return Q3SimulationResult(
            False, current, None, None, tuple(records), "截止日前未到达终点"
        )


def solve_initial_purchase_q4(
    level: LevelConfig,
    game: GameConfig,
    gamma: int,
    max_water: int | None = None,
    max_food: int | None = None,
) -> Q4AdaptiveBudgetRobustResult:
    started = perf_counter()
    solver = Q4AdaptiveBudgetRobustSolver(level, game, gamma)

    max_water = max_water or min(
        game.capacity_kg // game.water_weight,
        game.deadline * 3 * max(game.base_consumption[w][0] for w in ("晴朗", "高温", "沙暴")),
    )
    max_food = max_food or min(
        game.capacity_kg // game.food_weight,
        game.deadline * 3 * max(game.base_consumption[w][1] for w in ("晴朗", "高温", "沙暴")),
    )

    best_initial: State | None = None
    best_robust = NEG_INF
    best_nominal = NEG_INF
    candidates = 0
    feasible_states = 0

    for water in range(0, max_water + 1):
        for food in range(0, max_food + 1):
            if game.water_weight * water + game.food_weight * food > game.capacity_kg:
                continue
            if game.water_price * water + game.food_price * food > game.initial_cash:
                continue
            try:
                init_state = initial_state(game, level, water, food)
            except ValueError:
                continue
            candidates += 1
            ws = allowed_weather(gamma)
            branches = {}
            for ω in ws:
                d = solver.decide(1, init_state, ω, gamma)
                branches[ω] = d
            if any(b.robust_value == NEG_INF for b in branches.values()):
                continue
            feasible_states += 1
            robust = min(b.robust_value for b in branches.values())
            initial_probs = empirical_initial_probabilities(HISTORICAL_WEATHER, ws)
            nominal = sum(initial_probs[ω] * branches[ω].nominal_value for ω in ws)
            score = (robust, nominal)
            best_score = (best_robust, best_nominal)
            if score > best_score:
                best_robust = robust
                best_nominal = nominal
                best_initial = init_state

    if best_initial is None:
        raise RuntimeError(
            f"{level.name} (Γ={gamma})：未找到覆盖全部允许天气的鲁棒初购方案"
        )

    runtime = perf_counter() - started
    return Q4AdaptiveBudgetRobustResult(
        optimal=True,
        status="AdaptiveBudgetRobust DP 收敛",
        final_wealth=best_robust,
        arrival_day=0,
        initial_state=best_initial,
        policy={},
        robust_value=best_robust,
        nominal_value=best_nominal,
        runtime_seconds=runtime,
        statistics={
            "candidates_checked": candidates,
            "feasible_states": feasible_states,
            "gamma": gamma,
            **solver._stats,
        },
    )


# scenario_tree_milp - 情景树 MILP 求解器

print()
print("scenario_tree_milp - 情景树 MILP 求解器")
print()


@dataclass(frozen=True)
class MilpScenarioTreeSolution:
    level: LevelConfig
    game: GameConfig
    weather_states: tuple[str, ...]
    initial_state: State
    policy: dict[tuple[str, ...], Action]
    robust_by_history: dict[tuple[str, ...], float]
    nominal_by_history: dict[tuple[str, ...], float]
    robust_value: float
    nominal_value: float
    optimal: bool
    status: str
    runtime_seconds: float
    statistics: dict[str, int | float | str]


class _LinearModel:
    def __init__(self) -> None:
        self.lower: list[float] = []
        self.upper: list[float] = []
        self.integrality: list[int] = []
        self.objective: list[float] = []
        self.rows: list[dict[int, float]] = []
        self.row_lower: list[float] = []
        self.row_upper: list[float] = []

    def var(
        self, lb: float = 0.0, ub: float = np.inf, integer: bool = False,
        objective: float = 0.0,
    ) -> int:
        index = len(self.lower)
        self.lower.append(lb)
        self.upper.append(ub)
        self.integrality.append(1 if integer else 0)
        self.objective.append(objective)
        return index

    def constraint(
        self, terms: dict[int, float], lb: float = -np.inf, ub: float = np.inf
    ) -> None:
        self.rows.append({index: value for index, value in terms.items() if value})
        self.row_lower.append(lb)
        self.row_upper.append(ub)

    def equality(self, terms: dict[int, float], value: float) -> None:
        self.constraint(terms, value, value)

    def matrix(self):
        row_ids: list[int] = []
        column_ids: list[int] = []
        values: list[float] = []
        for row_id, row in enumerate(self.rows):
            for column_id, value in row.items():
                row_ids.append(row_id)
                column_ids.append(column_id)
                values.append(value)
        return coo_matrix(
            (values, (row_ids, column_ids)),
            shape=(len(self.rows), len(self.lower)),
            dtype=float,
        ).tocsr()


def _add(terms: dict[int, float], index: int, value: float) -> None:
    terms[index] = terms.get(index, 0.0) + value


def _histories(
    deadline: int, weather_states: tuple[str, ...]
) -> dict[int, tuple[tuple[str, ...], ...]]:
    return {
        day: tuple(product(weather_states, repeat=day))
        for day in range(1, deadline + 1)
    }


def _solve_model(model: _LinearModel, time_limit_seconds: float, disp: bool):
    matrix = model.matrix()
    return milp(
        c=np.asarray(model.objective, dtype=float),
        integrality=np.asarray(model.integrality, dtype=np.uint8),
        bounds=Bounds(model.lower, model.upper),
        constraints=LinearConstraint(matrix, model.row_lower, model.row_upper),
        options={
            "time_limit": time_limit_seconds,
            "mip_rel_gap": 0.0,
            "presolve": True,
            "disp": disp,
        },
    )


def solve_scenario_tree(
    level: LevelConfig,
    game: GameConfig,
    weather_states: tuple[str, ...] = ("晴朗", "高温"),
    time_limit_seconds: float = 300.0,
    disp: bool = False,
) -> MilpScenarioTreeSolution:
    if level.villages:
        raise ValueError("第三关情景树入口不处理村庄补给")
    started = perf_counter()
    model = _LinearModel()
    histories = _histories(game.deadline, weather_states)
    nodes = range(1, level.node_count + 1)
    directed_edges = tuple(
        direction for i, j in level.edges for direction in ((i, j), (j, i))
    )

    max_water = game.capacity_kg // game.water_weight
    max_food = game.capacity_kg // game.food_weight
    max_cash = game.initial_cash + game.deadline * game.mine_income
    buy_water = model.var(0, max_water, integer=True)
    buy_food = model.var(0, max_food, integer=True)
    robust_floor = model.var(0, max_cash + game.initial_cash, objective=-1.0)

    x: dict[tuple[tuple[str, ...], int], int] = {}
    post_x: dict[tuple[tuple[str, ...], int], int] = {}
    water: dict[tuple[str, ...], int] = {}
    food: dict[tuple[str, ...], int] = {}
    cash: dict[tuple[str, ...], int] = {}
    post_water: dict[tuple[str, ...], int] = {}
    post_food: dict[tuple[str, ...], int] = {}
    post_cash: dict[tuple[str, ...], int] = {}
    move: dict[tuple[tuple[str, ...], int, int], int] = {}
    stay: dict[tuple[tuple[str, ...], int], int] = {}
    mine: dict[tuple[tuple[str, ...], int], int] = {}
    finish: dict[tuple[str, ...], int] = {}

    for day in range(1, game.deadline + 1):
        for history in histories[day]:
            for node in nodes:
                fixed = (1.0 if node == level.start else 0.0) if day == 1 else None
                x[history, node] = model.var(
                    fixed if fixed is not None else 0,
                    fixed if fixed is not None else 1,
                    integer=True,
                )
                post_x[history, node] = model.var(0, 1, integer=True)
            water[history] = model.var(0, max_water)
            food[history] = model.var(0, max_food)
            cash[history] = model.var(0, max_cash)
            post_water[history] = model.var(0, max_water)
            post_food[history] = model.var(0, max_food)
            post_cash[history] = model.var(0, max_cash)
            can_move = history[-1] != "沙暴"
            for i, j in directed_edges:
                move[history, i, j] = model.var(0, 1 if can_move else 0, integer=True)
            for node in nodes:
                if node != level.goal:
                    stay[history, node] = model.var(0, 1, integer=True)
            for node in level.mines:
                mine[history, node] = model.var(0, 1, integer=True)
            finish[history] = model.var(0, 1, integer=True)

    model.constraint(
        {buy_water: game.water_weight, buy_food: game.food_weight},
        ub=game.capacity_kg,
    )
    model.constraint(
        {buy_water: game.water_price, buy_food: game.food_price},
        ub=game.initial_cash,
    )

    for first_history in histories[1]:
        model.equality({water[first_history]: 1, buy_water: -1}, 0)
        model.equality({food[first_history]: 1, buy_food: -1}, 0)
        model.equality(
            {
                cash[first_history]: 1,
                buy_water: game.water_price,
                buy_food: game.food_price,
            },
            game.initial_cash,
        )

    outgoing: dict[int, list[tuple[int, int]]] = {node: [] for node in nodes}
    incoming: dict[int, list[tuple[int, int]]] = {node: [] for node in nodes}
    for i, j in directed_edges:
        outgoing[i].append((i, j))
        incoming[j].append((i, j))

    terminal_histories = histories[game.deadline]
    terminal_wealth_terms: dict[tuple[str, ...], dict[int, float]] = {}
    for day in range(1, game.deadline + 1):
        for history in histories[day]:
            for node in nodes:
                origin = {x[history, node]: -1.0}
                for i, j in outgoing[node]:
                    _add(origin, move[history, i, j], 1.0)
                if node != level.goal:
                    _add(origin, stay[history, node], 1.0)
                if node in level.mines:
                    _add(origin, mine[history, node], 1.0)
                if node == level.goal:
                    _add(origin, finish[history], 1.0)
                model.equality(origin, 0)

                destination = {post_x[history, node]: -1.0}
                for i, j in incoming[node]:
                    _add(destination, move[history, i, j], 1.0)
                if node != level.goal:
                    _add(destination, stay[history, node], 1.0)
                if node in level.mines:
                    _add(destination, mine[history, node], 1.0)
                if node == level.goal:
                    _add(destination, finish[history], 1.0)
                model.equality(destination, 0)

            base_water, base_food = game.base_consumption[history[-1]]
            water_terms = {post_water[history]: 1, water[history]: -1}
            food_terms = {post_food[history]: 1, food[history]: -1}
            cash_terms = {post_cash[history]: 1, cash[history]: -1}
            for i, j in directed_edges:
                _add(water_terms, move[history, i, j], 2 * base_water)
                _add(food_terms, move[history, i, j], 2 * base_food)
            for node in nodes:
                if node != level.goal:
                    _add(water_terms, stay[history, node], base_water)
                    _add(food_terms, stay[history, node], base_food)
            for node in level.mines:
                _add(water_terms, mine[history, node], 3 * base_water)
                _add(food_terms, mine[history, node], 3 * base_food)
                _add(cash_terms, mine[history, node], -game.mine_income)
            model.equality(water_terms, 0)
            model.equality(food_terms, 0)
            model.equality(cash_terms, 0)

            if day < game.deadline:
                for next_weather in weather_states:
                    child = history + (next_weather,)
                    model.equality({water[child]: 1, post_water[history]: -1}, 0)
                    model.equality({food[child]: 1, post_food[history]: -1}, 0)
                    model.equality({cash[child]: 1, post_cash[history]: -1}, 0)
                    for node in nodes:
                        model.equality(
                            {x[child, node]: 1, post_x[history, node]: -1}, 0
                        )
            else:
                model.equality({post_x[history, level.goal]: 1}, 1)
                wealth_terms = {
                    post_cash[history]: 1.0,
                    post_water[history]: 0.5 * game.water_price,
                    post_food[history]: 0.5 * game.food_price,
                }
                terminal_wealth_terms[history] = wealth_terms
                floor_constraint = {robust_floor: 1.0}
                for index, coefficient in wealth_terms.items():
                    _add(floor_constraint, index, -coefficient)
                model.constraint(floor_constraint, ub=0)

    first_result = _solve_model(model, time_limit_seconds, disp)
    if first_result.x is None:
        raise RuntimeError(f"{level.name}鲁棒情景树求解失败：{first_result.message}")
    robust_optimum = round(float(first_result.x[robust_floor]) * 2) / 2

    model.constraint({robust_floor: 1.0}, lb=robust_optimum - 1e-7)
    model.objective = [0.0] * len(model.objective)
    initial_probabilities = empirical_initial_probabilities(
        HISTORICAL_WEATHER, weather_states
    )
    markov_states, markov = nominal_transition_probabilities(
        HISTORICAL_WEATHER, weather_states
    )
    weather_index = {weather: i for i, weather in enumerate(markov_states)}
    leaf_probabilities: dict[tuple[str, ...], float] = {}
    for history in terminal_histories:
        probability = initial_probabilities[history[0]]
        for current, following in zip(history, history[1:]):
            probability *= markov[weather_index[current], weather_index[following]]
        leaf_probabilities[history] = float(probability)
        for index, coefficient in terminal_wealth_terms[history].items():
            model.objective[index] -= probability * coefficient

    second_result = _solve_model(model, time_limit_seconds, disp)
    result = second_result if second_result.x is not None else first_result
    values = result.x

    initial = State(
        level.start,
        int(round(values[buy_water])),
        int(round(values[buy_food])),
        game.initial_cash
        - game.water_price * int(round(values[buy_water]))
        - game.food_price * int(round(values[buy_food])),
    )
    policy: dict[tuple[str, ...], Action] = {}
    for day in range(1, game.deadline + 1):
        for history in histories[day]:
            chosen: Action | None = None
            for i, j in directed_edges:
                if values[move[history, i, j]] > 0.5:
                    chosen = Action("行走", j)
                    break
            if chosen is None:
                for node in level.mines:
                    if values[mine[history, node]] > 0.5:
                        chosen = Action("挖矿", node)
                        break
            if chosen is None:
                for node in nodes:
                    if node != level.goal and values[stay[history, node]] > 0.5:
                        chosen = Action("停留", node)
                        break
            if chosen is None and values[finish[history]] > 0.5:
                chosen = Action("终止", level.goal)
            if chosen is None:
                raise RuntimeError(f"天气历史 {history} 未提取到行动")
            policy[history] = chosen

    leaf_values = {
        history: sum(
            coefficient * values[index]
            for index, coefficient in terminal_wealth_terms[history].items()
        )
        for history in terminal_histories
    }
    robust_by_history: dict[tuple[str, ...], float] = dict(leaf_values)
    nominal_by_history: dict[tuple[str, ...], float] = dict(leaf_values)
    for day in range(game.deadline - 1, 0, -1):
        for history in histories[day]:
            children = [history + (weather,) for weather in weather_states]
            robust_by_history[history] = min(robust_by_history[child] for child in children)
            row = markov[weather_index[history[-1]]]
            nominal_by_history[history] = sum(
                row[weather_index[weather]] * nominal_by_history[history + (weather,)]
                for weather in weather_states
            )

    robust_value = min(leaf_values.values())
    nominal_value = sum(
        leaf_probabilities[history] * leaf_values[history]
        for history in terminal_histories
    )
    return MilpScenarioTreeSolution(
        level=level,
        game=game,
        weather_states=weather_states,
        initial_state=initial,
        policy=policy,
        robust_by_history=robust_by_history,
        nominal_by_history=nominal_by_history,
        robust_value=round(robust_value * 2) / 2,
        nominal_value=nominal_value,
        optimal=first_result.status == 0 and result.status == 0,
        status=str(result.message),
        runtime_seconds=perf_counter() - started,
        statistics={
            "variables": len(model.lower),
            "constraints": len(model.rows),
            "weather_tree_nodes": sum(len(items) for items in histories.values()),
            "terminal_scenarios": len(terminal_histories),
            "mip_gap": float(getattr(result, "mip_gap", 0.0) or 0.0),
            "mip_nodes": int(getattr(result, "mip_node_count", 0) or 0),
            "solver": "SciPy milp / HiGHS（非前视天气情景树）",
        },
    )


def simulate_tree_policy(
    solution: MilpScenarioTreeSolution, weather_sequence: tuple[str, ...]
) -> Q3SimulationResult:
    state = solution.initial_state
    history: tuple[str, ...] = ()
    records: list[DailyRecord] = []
    for day, weather in enumerate(weather_sequence, start=1):
        if day > solution.game.deadline or state.node == solution.level.goal:
            break
        history += (weather,)
        action = solution.policy.get(history)
        if action is None or action.kind == "终止":
            return Q3SimulationResult(
                False, state, None, None, tuple(records), f"第{day}天未找到可执行行动"
            )
        previous = state
        try:
            state = apply_action(
                state, action, weather, solution.level, solution.game
            )
        except ValueError as exc:
            return Q3SimulationResult(
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
                weight=total_weight(state, solution.game),
                robust_value=solution.robust_by_history[history],
                nominal_value=solution.nominal_by_history[history],
            )
        )
        if state.node == solution.level.goal:
            return Q3SimulationResult(
                True, state, terminal_wealth(state, solution.game), day, tuple(records)
            )
    return Q3SimulationResult(
        False, state, None, None, tuple(records), "截止日前未到达终点"
    )


# oracle_dp - 完全信息 Oracle DP 求解器

print()
print("oracle_dp - 完全信息 Oracle DP 求解器")
print()


@dataclass(frozen=True)
class OracleResult:
    final_wealth: float
    initial_water: int
    initial_food: int
    initial_cash: int
    arrival_day: int
    actions: tuple
    records: tuple


@dataclass(frozen=True)
class Q3OracleLabel:
    node: int
    water_used: int
    food_used: int
    cash_used: int
    mine_income: int
    actions: tuple


def _q3_dominates(left: Q3OracleLabel, right: Q3OracleLabel) -> bool:
    return (
        left.water_used <= right.water_used
        and left.food_used <= right.food_used
        and left.cash_used <= right.cash_used
        and left.mine_income >= right.mine_income
        and (
            left.water_used < right.water_used
            or left.food_used < right.food_used
            or left.cash_used < right.cash_used
            or left.mine_income > right.mine_income
        )
    )


def _q3_insert_pareto(frontier: list[Q3OracleLabel], candidate: Q3OracleLabel) -> None:
    for existing in frontier:
        if (
            existing.water_used == candidate.water_used
            and existing.food_used == candidate.food_used
            and existing.cash_used <= candidate.cash_used
            and existing.mine_income >= candidate.mine_income
        ) or _q3_dominates(existing, candidate):
            return
    frontier[:] = [item for item in frontier if not _q3_dominates(candidate, item)]
    frontier.append(candidate)


def _solve_oracle_q3(
    level: LevelConfig, game: GameConfig, weather_sequence: tuple[str, ...]
) -> OracleResult:
    if len(weather_sequence) != game.deadline:
        raise ValueError("Oracle 天气序列长度必须等于关卡截止日")
    if level.villages:
        raise ValueError("Q3 路径不处理村庄，请使用 solve_oracle 自动调度")

    frontier: dict[int, list[Q3OracleLabel]] = {
        level.start: [Q3OracleLabel(level.start, 0, 0, 0, 0, ())]
    }
    terminal: list[tuple[Q3OracleLabel, int]] = []
    for day, weather in enumerate(weather_sequence, start=1):
        next_frontier: dict[int, list[Q3OracleLabel]] = {}
        base_water, base_food = game.base_consumption[weather]
        for labels in frontier.values():
            for label in labels:
                dummy = State(label.node, 0, 0, 0)
                for action in feasible_actions(dummy, weather, level):
                    multiplier = ACTION_MULTIPLIER[action.kind]
                    water_used = label.water_used + multiplier * base_water
                    food_used = label.food_used + multiplier * base_food
                    if (
                        game.water_weight * water_used + game.food_weight * food_used
                        > game.capacity_kg
                    ):
                        continue
                    if (
                        game.water_price * water_used + game.food_price * food_used
                        > game.initial_cash
                    ):
                        continue
                    candidate = Q3OracleLabel(
                        node=action.destination,
                        water_used=water_used,
                        food_used=food_used,
                        cash_used=label.cash_used,
                        mine_income=label.mine_income
                        + (game.mine_income if action.kind == "挖矿" else 0),
                        actions=label.actions + (action,),
                    )
                    if candidate.node == level.goal:
                        terminal.append((candidate, day))
                    elif day < game.deadline:
                        _q3_insert_pareto(
                            next_frontier.setdefault(candidate.node, []), candidate
                        )
        frontier = next_frontier

    if not terminal:
        raise RuntimeError("给定天气情景下不存在截止日前可行的 Oracle 路径")

    def score(item: tuple[Q3OracleLabel, int]) -> tuple[float, int, int, int]:
        label, arrival = item
        wealth = (
            game.initial_cash
            - game.water_price * label.water_used
            - game.food_price * label.food_used
            + label.mine_income
        )
        return wealth, -arrival, -label.water_used, -label.food_used

    best, arrival_day = max(terminal, key=score)
    initial_cash = (
        game.initial_cash
        - game.water_price * best.water_used
        - game.food_price * best.food_used
    )
    state = State(level.start, best.water_used, best.food_used, initial_cash)
    records = []
    for day, (weather, action) in enumerate(
        zip(weather_sequence, best.actions), start=1
    ):
        previous = state
        state = apply_action(state, action, weather, level, game)
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
                weight=total_weight(state, game),
                robust_value=float("nan"),
                nominal_value=float("nan"),
            )
        )
        if state.node == level.goal:
            break
    return OracleResult(
        final_wealth=terminal_wealth(state, game),
        initial_water=best.water_used,
        initial_food=best.food_used,
        initial_cash=initial_cash,
        arrival_day=arrival_day,
        actions=best.actions,
        records=tuple(records),
    )


@dataclass(frozen=True)
class Q4OracleLabel:
    cash: int
    prev: tuple | None


def _q4_pareto_prune(
    labels: dict[tuple[int, int], Q4OracleLabel],
    threshold: int = 10_000,
) -> dict[tuple[int, int], Q4OracleLabel]:
    if not labels:
        return labels
    if len(labels) > threshold:
        return labels
    best: dict[tuple[int, int], Q4OracleLabel] = {}
    for key, label in labels.items():
        existing = best.get(key)
        if existing is None or label.cash > existing.cash:
            best[key] = label
    items = sorted(best.items(), key=lambda kv: (-kv[0][0], -kv[1].cash, kv[0][1]))
    kept: dict[tuple[int, int], Q4OracleLabel] = {}
    front_f: list[int] = []
    front_cash: list[int] = []
    for key, label in items:
        w, f = key
        dominated = False
        for ff, fc in zip(front_f, front_cash):
            if ff >= f and fc >= label.cash and (ff > f or fc > label.cash):
                dominated = True
                break
        if dominated:
            continue
        new_f: list[int] = []
        new_c: list[int] = []
        for ff, fc in zip(front_f, front_cash):
            if not (ff <= f and fc <= label.cash):
                new_f.append(ff)
                new_c.append(fc)
        front_f = new_f
        front_cash = new_c
        front_f.append(f)
        front_cash.append(label.cash)
        kept[key] = label
    return kept


def _q4_village_closure(
    w_after: int,
    f_after: int,
    cash_after: int,
    game: GameConfig,
) -> list[tuple[int, int, int, int, int]]:
    candidates: list[tuple[int, int, int, int, int]] = []
    max_water = game.capacity_kg // game.water_weight
    max_food = game.capacity_kg // game.food_weight
    if cash_after < 0:
        return candidates
    for bw in range(0, max(0, max_water - w_after) + 1):
        cost_w = 2 * game.water_price * bw
        if cost_w > cash_after:
            break
        for bf in range(0, max(0, max_food - f_after) + 1):
            cost = cost_w + 2 * game.food_price * bf
            if cost > cash_after:
                break
            w_new = w_after + bw
            f_new = f_after + bf
            if game.water_weight * w_new + game.food_weight * f_new > game.capacity_kg:
                continue
            candidates.append((w_new, f_new, cash_after - cost, bw, bf))
    if not candidates:
        candidates.append((w_after, w_after, cash_after, 0, 0))
    return candidates


def _q4_earliest_arrival(
    t: int,
    dist: int,
    deadline: int,
    weather: tuple[str, ...],
) -> int | None:
    if dist == 0:
        return t
    needed = dist
    for q in range(t + 1, deadline + 1):
        if weather[q - 1] != "沙暴":
            needed -= 1
            if needed == 0:
                return q
    return None


def _q4_precompute_earliest(
    deadline: int,
    weather: tuple[str, ...],
    distances: dict[int, int],
) -> dict[int, dict[int, int | None]]:
    table: dict[int, dict[int, int | None]] = {}
    for t in range(0, deadline + 1):
        table[t] = {
            node: _q4_earliest_arrival(t, dist, deadline, weather)
            for node, dist in distances.items()
        }
    return table


def _q4_optimistic_bound(
    cash: int,
    w: int,
    f: int,
    t: int,
    deadline: int,
    game: GameConfig,
) -> float:
    return optimistic_upper_bound_3d(
        w,
        f,
        cash,
        deadline,
        t,
        game.water_price,
        game.food_price,
        game.mine_income,
    )


def _q4_legal_actions(level: LevelConfig, weather_today: str, from_node: int):
    actions = []
    if from_node == level.goal:
        return actions
    if weather_today != "沙暴":
        for neighbor in level.neighbors[from_node]:
            actions.append(Action("行走", neighbor))
    if from_node in level.mines:
        actions.append(Action("挖矿", from_node))
    actions.append(Action("停留", from_node))
    return actions


def _q4_backtrack(
    final_t: int,
    final_i: int,
    final_w: int,
    final_f: int,
    final_cash: int,
    labels: list[dict[int, dict[tuple[int, int], Q4OracleLabel]]],
    level: LevelConfig,
    game: GameConfig,
    weather: tuple[str, ...],
) -> tuple[list, tuple[int, int, int]]:
    chain: list[tuple[int, int, int, int, int, int, int, int, int]] = []
    t = final_t
    i = final_i
    w = final_w
    f = final_f
    initial_w: int | None = None
    initial_f: int | None = None
    initial_cash: int | None = None
    while t > 0:
        label = labels[t][i][(w, f)]
        assert label.prev is not None
        prev_t, prev_i, prev_w, prev_f, action_kind, bw, bf, action_dest = label.prev
        chain.append((t, prev_i, i, action_kind, bw, bf, label.cash, w, f))
        t, i, w, f = prev_t, prev_i, prev_w, prev_f
        if t == 0:
            initial_w, initial_f = w, f
            initial_cash = labels[0][level.start][(w, f)].cash
    assert initial_w is not None and initial_f is not None
    chain.reverse()
    records: list[DailyRecord] = []
    for t, prev_i, cur_i, action_kind, bw, bf, cash, w, f in chain:
        records.append(
            DailyRecord(
                day=t,
                weather=weather[t - 1],
                from_node=prev_i,
                to_node=cur_i,
                action=action_kind,
                buy_water=bw,
                buy_food=bf,
                cash=cash,
                water=w,
                food=f,
                weight=total_weight(State(cur_i, w, f, cash), game),
                robust_value=float("nan"),
                nominal_value=float("nan"),
            )
        )
    return records, (initial_w, initial_f, initial_cash or 0)


def _solve_oracle_q4(
    level: LevelConfig, game: GameConfig, weather_sequence: tuple[str, ...]
) -> OracleResult:
    if len(weather_sequence) != game.deadline:
        raise ValueError("Oracle 天气序列长度必须等于关卡截止日")
    distances = bfs_distances(level, level.goal)
    earliest = _q4_precompute_earliest(game.deadline, weather_sequence, distances)

    labels: list[dict[int, dict[tuple[int, int], Q4OracleLabel]]] = [
        {} for _ in range(game.deadline + 1)
    ]

    max_water = game.capacity_kg // game.water_weight
    max_food = game.capacity_kg // game.food_weight
    initial_layer: dict[tuple[int, int], Q4OracleLabel] = {}
    for w in range(0, max_water + 1):
        cost_w = game.water_price * w
        if cost_w > game.initial_cash:
            break
        max_f_budget = (game.initial_cash - cost_w) // game.food_price
        max_f_weight = (game.capacity_kg - game.water_weight * w) // game.food_weight
        max_f = min(max_f_budget, max_f_weight, max_food)
        for f in range(0, max_f + 1):
            cash = game.initial_cash - cost_w - game.food_price * f
            initial_layer[(w, f)] = Q4OracleLabel(cash=cash, prev=None)
    labels[0] = {level.start: initial_layer}

    best_terminal: float = float("-inf")
    best_terminal_label: tuple[int, int, int, int, int] | None = None
    arrival_day = game.deadline

    for t in range(0, game.deadline):
        weather_today = weather_sequence[t]
        base_w, base_f = game.base_consumption[weather_today]
        next_layer: dict[int, dict[tuple[int, int], Q4OracleLabel]] = {
            node: {} for node in range(1, level.node_count + 1)
        }
        for from_node, day_labels in labels[t].items():
            for (w_prev, f_prev), label in day_labels.items():
                ea = earliest[t].get(from_node)
                if ea is None or ea > game.deadline:
                    continue
                if _q4_optimistic_bound(label.cash, w_prev, f_prev, t, game.deadline, game) <= best_terminal:
                    continue
                for action in _q4_legal_actions(level, weather_today, from_node):
                    mult = ACTION_MULTIPLIER[action.kind]
                    dw = base_w * mult
                    df = base_f * mult
                    if w_prev < dw or f_prev < df:
                        continue
                    w_mid = w_prev - dw
                    f_mid = f_prev - df
                    cash_mid = label.cash + (
                        game.mine_income if action.kind == "挖矿" else 0
                    )

                    if action.destination == level.goal:
                        z = (
                            cash_mid
                            + 0.5 * game.water_price * w_mid
                            + 0.5 * game.food_price * f_mid
                        )
                        if z > best_terminal:
                            best_terminal = z
                            best_terminal_label = (
                                t + 1,
                                level.goal,
                                w_mid,
                                f_mid,
                                cash_mid,
                            )
                            arrival_day = t + 1
                            next_layer[level.goal][(w_mid, f_mid)] = Q4OracleLabel(
                                cash=cash_mid,
                                prev=(
                                    t, from_node, w_prev, f_prev,
                                    action.kind, 0, 0, action.destination,
                                ),
                            )
                        continue

                    if action.destination in level.villages:
                        purchase_states = _q4_village_closure(w_mid, f_mid, cash_mid, game)
                    else:
                        purchase_states = [(w_mid, f_mid, cash_mid, 0, 0)]

                    for w_new, f_new, cash_new, bw, bf in purchase_states:
                        slot = next_layer[action.destination]
                        key = (w_new, f_new)
                        existing = slot.get(key)
                        if existing is None or cash_new > existing.cash:
                            slot[key] = Q4OracleLabel(
                                cash=cash_new,
                                prev=(
                                    t, from_node, w_prev, f_prev,
                                    action.kind, bw, bf, action.destination,
                                ),
                            )
        for node, day_labels in next_layer.items():
            if day_labels:
                next_layer[node] = _q4_pareto_prune(day_labels)
        labels[t + 1] = next_layer

    if best_terminal_label is None:
        raise RuntimeError(f"{level.name}：Oracle DP 未找到可行终点策略")

    final_t, final_i, final_w, final_f, final_cash = best_terminal_label
    records, (initial_w, initial_f, initial_cash) = _q4_backtrack(
        final_t, final_i, final_w, final_f, final_cash,
        labels, level, game, weather_sequence,
    )
    return OracleResult(
        final_wealth=round(best_terminal * 2) / 2,
        initial_water=initial_w,
        initial_food=initial_f,
        initial_cash=initial_cash,
        arrival_day=arrival_day,
        actions=tuple(record.action for record in records),
        records=tuple(records),
    )


def solve_oracle(
    level: LevelConfig,
    game: GameConfig,
    weather_sequence: tuple[str, ...],
) -> OracleResult:
    if not level.villages:
        return _solve_oracle_q3(level, game, weather_sequence)
    return _solve_oracle_q4(level, game, weather_sequence)


# validate_q2 - 第二关模型验证

print()
print("validate_q2 - 第二关模型验证")
print()


@dataclass(frozen=True)
class Q2ScenarioEvaluation:
    scenario: tuple[str, ...]
    success: bool
    terminal_wealth: float
    arrival_day: int
    oracle_wealth: float
    regret: float


@dataclass(frozen=True)
class Q2LevelThreeValidationReport:
    scenario_count: int
    success_count: int
    failure_count: int
    worst_wealth: float
    mean_wealth: float
    q05_wealth: float
    minimum_regret: float
    mean_regret: float
    median_regret: float
    maximum_regret: float
    arrival_distribution: dict[int, int]
    nonanticipativity_ok: bool
    rule_check_ok: bool
    evaluations: tuple[Q2ScenarioEvaluation, ...]


def validate_level_three(
    solution: MilpScenarioTreeSolution,
) -> Q2LevelThreeValidationReport:
    scenarios = enumerate_weather_scenarios(
        solution.game.deadline, solution.weather_states
    )
    evaluations: list[Q2ScenarioEvaluation] = []
    rule_check_ok = True
    for scenario in scenarios:
        online = simulate_tree_policy(solution, scenario)
        if not online.success or online.final_wealth is None or online.arrival_day is None:
            rule_check_ok = False
            evaluations.append(
                Q2ScenarioEvaluation(scenario, False, float("-inf"), 0, float("nan"), float("nan"))
            )
            continue
        if any(
            record.water < 0
            or record.food < 0
            or record.cash < 0
            or record.weight > solution.game.capacity_kg
            for record in online.records
        ):
            rule_check_ok = False
        oracle = solve_oracle(solution.level, solution.game, scenario)
        regret = oracle.final_wealth - online.final_wealth
        evaluations.append(
            Q2ScenarioEvaluation(
                scenario=scenario,
                success=True,
                terminal_wealth=online.final_wealth,
                arrival_day=online.arrival_day,
                oracle_wealth=oracle.final_wealth,
                regret=regret,
            )
        )

    successful = [item for item in evaluations if item.success]
    wealth = np.asarray([item.terminal_wealth for item in successful], dtype=float)
    regrets = np.asarray([item.regret for item in successful], dtype=float)
    actions_by_prefix: dict[tuple[str, ...], set] = {}
    for scenario in scenarios:
        online = simulate_tree_policy(solution, scenario)
        for record in online.records:
            prefix = scenario[: record.day]
            actions_by_prefix.setdefault(prefix, set()).add(
                (record.action, record.to_node, record.buy_water, record.buy_food)
            )
    nonanticipativity_ok = all(
        len(actions) == 1 for actions in actions_by_prefix.values()
    )
    return Q2LevelThreeValidationReport(
        scenario_count=len(scenarios),
        success_count=len(successful),
        failure_count=len(scenarios) - len(successful),
        worst_wealth=float(np.min(wealth)),
        mean_wealth=float(np.mean(wealth)),
        q05_wealth=float(np.quantile(wealth, 0.05)),
        minimum_regret=float(np.min(regrets)),
        mean_regret=float(np.mean(regrets)),
        median_regret=float(np.median(regrets)),
        maximum_regret=float(np.max(regrets)),
        arrival_distribution=dict(sorted(Counter(item.arrival_day for item in successful).items())),
        nonanticipativity_ok=nonanticipativity_ok,
        rule_check_ok=rule_check_ok,
        evaluations=tuple(evaluations),
    )


# validate_q4 - 第四关验证和灵敏度分析

print()
print("validate_q4 - 第四关验证和灵敏度分析")
print()


@dataclass(frozen=True)
class Q4StrategyMetrics:
    strategy: str
    trials: int
    success_count: int
    success_rate: float
    mean_wealth: float
    minimum_wealth: float
    q05_wealth: float
    mean_arrival_day: float
    mean_regret: float
    maximum_regret: float


@dataclass(frozen=True)
class Q4TrialResult:
    trial: int
    strategy: str
    weather: str
    storm_count_before_arrival: int
    success: bool
    arrival_day: int | None
    final_wealth: float | None
    oracle_wealth: float | None
    regret: float | None


def _scaled_weather_model(storm_factor: float) -> tuple[np.ndarray, np.ndarray]:
    if storm_factor <= 0:
        raise ValueError("沙暴概率倍率必须为正")
    states, transition = nominal_transition_probabilities()
    initial_map = empirical_initial_probabilities(HISTORICAL_WEATHER, states)
    initial = np.asarray([initial_map[state] for state in states], dtype=float)
    storm_index = states.index("沙暴")
    transition[:, storm_index] *= storm_factor
    transition /= transition.sum(axis=1, keepdims=True)
    initial[storm_index] *= storm_factor
    initial /= initial.sum()
    return initial, transition


def generate_markov_weather(
    trials: int,
    days: int,
    seed: int,
    storm_factor: float = 1.0,
) -> tuple[tuple[str, ...], ...]:
    if trials <= 0 or days <= 0:
        raise ValueError("模拟次数和天数必须为正")
    initial, transition = _scaled_weather_model(storm_factor)
    rng = np.random.default_rng(seed)
    scenarios: list[tuple[str, ...]] = []
    for _ in range(trials):
        state_index = int(rng.choice(len(WEATHER_STATES), p=initial))
        sequence = [WEATHER_STATES[state_index]]
        for _day in range(1, days):
            state_index = int(rng.choice(len(WEATHER_STATES), p=transition[state_index]))
            sequence.append(WEATHER_STATES[state_index])
        scenarios.append(tuple(sequence))
    return tuple(scenarios)


def _requirements_until_goal(
    sequence: Sequence[str], steps: int, game: GameConfig
) -> tuple[int, int, int, int] | None:
    water = food = moves = storms = 0
    for day, weather in enumerate(sequence, start=1):
        base_water, base_food = game.base_consumption[weather]
        if weather == "沙暴":
            water += base_water
            food += base_food
            storms += 1
        else:
            water += 2 * base_water
            food += 2 * base_food
            moves += 1
            if moves == steps:
                return water, food, day, storms
    return None


def build_first_question_fixed_plan(
    level: LevelConfig, game: GameConfig
) -> Q4SafeBaselinePlan:
    template = build_safe_baseline(level, game, gamma=0)
    requirement = _requirements_until_goal(
        HISTORICAL_WEATHER, template.shortest_steps, game
    )
    if requirement is None:
        raise RuntimeError("第一问历史天气下无法完成最短路径")
    water, food, _arrival, _storms = requirement
    state = initial_state(game, level, water, food)
    return replace(
        template,
        gamma=game.deadline,
        initial_state=state,
        guaranteed_wealth=float(state.cash),
        model_role="第一问已知历史天气下确定的固定采购方案",
    )


def _oracle_wealth(
    sequence: Sequence[str], steps: int, game: GameConfig
) -> tuple[float, int, int] | None:
    requirement = _requirements_until_goal(sequence, steps, game)
    if requirement is None:
        return None
    water, food, arrival, storms = requirement
    if game.water_weight * water + game.food_weight * food > game.capacity_kg:
        return None
    wealth = game.initial_cash - game.water_price * water - game.food_price * food
    if wealth < 0:
        return None
    return float(wealth), arrival, storms


def _simulate_plan(plan, scenario):
    if isinstance(plan, Q4HighSafetyPlan):
        return simulate_high_safety(plan, scenario)
    return simulate_safe_baseline(plan, scenario)


def evaluate_strategies(
    plans: Mapping[str, object],
    scenarios: Sequence[tuple[str, ...]],
) -> tuple[tuple[Q4StrategyMetrics, ...], tuple[Q4TrialResult, ...]]:
    if not plans:
        raise ValueError("至少需要一个待检验策略")
    trials: list[Q4TrialResult] = []
    metric_rows: list[Q4StrategyMetrics] = []
    for strategy, plan in plans.items():
        successes: list[tuple[float, int, float]] = []
        for number, scenario in enumerate(scenarios, start=1):
            oracle = _oracle_wealth(scenario, plan.shortest_steps, plan.game)
            simulation = _simulate_plan(plan, scenario)
            oracle_wealth = oracle[0] if oracle else None
            storm_count = oracle[2] if oracle else scenario.count("沙暴")
            regret = (
                oracle_wealth - simulation.final_wealth
                if simulation.success and oracle_wealth is not None and simulation.final_wealth is not None
                else None
            )
            if simulation.success and simulation.final_wealth is not None and regret is not None:
                successes.append((simulation.final_wealth, simulation.arrival_day or 0, regret))
            trials.append(
                Q4TrialResult(
                    trial=number,
                    strategy=strategy,
                    weather="".join({"晴朗": "S", "高温": "H", "沙暴": "X"}[w] for w in scenario),
                    storm_count_before_arrival=storm_count,
                    success=simulation.success,
                    arrival_day=simulation.arrival_day,
                    final_wealth=simulation.final_wealth,
                    oracle_wealth=oracle_wealth,
                    regret=regret,
                )
            )
        wealth = np.asarray([item[0] for item in successes], dtype=float)
        arrivals = np.asarray([item[1] for item in successes], dtype=float)
        regrets = np.asarray([item[2] for item in successes], dtype=float)
        success_count = len(successes)
        metric_rows.append(
            Q4StrategyMetrics(
                strategy=strategy,
                trials=len(scenarios),
                success_count=success_count,
                success_rate=success_count / len(scenarios),
                mean_wealth=float(np.mean(wealth)) if success_count else 0.0,
                minimum_wealth=float(np.min(wealth)) if success_count else 0.0,
                q05_wealth=float(np.quantile(wealth, 0.05)) if success_count else 0.0,
                mean_arrival_day=float(np.mean(arrivals)) if success_count else 0.0,
                mean_regret=float(np.mean(regrets)) if success_count else 0.0,
                maximum_regret=float(np.max(regrets)) if success_count else 0.0,
            )
        )
    return tuple(metric_rows), tuple(trials)


def gamma_sensitivity(
    level: LevelConfig,
    game: GameConfig,
    scenarios: Sequence[tuple[str, ...]],
    gammas: Iterable[int] = range(0, 10),
) -> tuple[dict, ...]:
    rows = []
    for gamma in gammas:
        plan = build_safe_baseline(level, game, gamma)
        metrics, _ = evaluate_strategies({f"Gamma={gamma}": plan}, scenarios)
        item = metrics[0]
        rows.append(
            {
                "Gamma": gamma,
                "初购水": plan.initial_state.water,
                "初购食物": plan.initial_state.food,
                "初购后现金": plan.initial_state.cash,
                "成功率": item.success_rate,
                "成功样本平均财富": item.mean_wealth,
                "5%分位财富": item.q05_wealth,
                "平均Regret": item.mean_regret,
            }
        )
    return tuple(rows)


def storm_probability_sensitivity(
    plan: Q4SafeBaselinePlan,
    trials: int,
    seed: int,
    factors: Iterable[float] = (0.7, 0.85, 1.0, 1.15, 1.3),
) -> tuple[dict, ...]:
    rows = []
    for index, factor in enumerate(factors):
        scenarios = generate_markov_weather(
            trials, plan.game.deadline, seed + index, factor
        )
        metrics, _ = evaluate_strategies({"鲁棒决策模型": plan}, scenarios)
        item = metrics[0]
        rows.append(
            {
                "沙暴概率倍率": factor,
                "成功率": item.success_rate,
                "成功样本平均财富": item.mean_wealth,
                "5%分位财富": item.q05_wealth,
                "平均到达日": item.mean_arrival_day,
                "平均Regret": item.mean_regret,
            }
        )
    return tuple(rows)


def write_rows(path: Path, rows: Iterable[object]) -> None:
    materialized = list(rows)
    if not materialized:
        raise ValueError("没有可写出的数据")
    normalized = [item.__dict__ if hasattr(item, "__dict__") else item for item in materialized]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(normalized[0].keys()))
        writer.writeheader()
        writer.writerows(normalized)


CAPACITY_SWEEP = (1080, 1140, 1260, 1320)
INITIAL_CASH_SWEEP = (9000, 9500, 10500, 11000)
MINE_INCOME_SWEEP = (900, 950, 1050, 1100)
DEADLINE_SWEEP = (28, 29, 31, 32)


def parameter_sensitivity(
    level: LevelConfig,
    base_game: GameConfig,
    scenarios: Sequence[tuple[str, ...]],
    gamma: int = 6,
) -> tuple[dict, ...]:
    rows: list[dict] = []
    for capacity in CAPACITY_SWEEP:
        game = replace(base_game, capacity_kg=capacity)
        plan = build_safe_baseline(level, game, gamma)
        metrics, _ = evaluate_strategies({f"M={capacity}": plan}, scenarios)
        item = metrics[0]
        rows.append(
            {
                "参数": "负重M",
                "参数值": capacity,
                "初购水": plan.initial_state.water,
                "初购食物": plan.initial_state.food,
                "初购后现金": plan.initial_state.cash,
                "成功率": item.success_rate,
                "成功样本平均财富": item.mean_wealth,
                "5%分位财富": item.q05_wealth,
                "平均Regret": item.mean_regret,
            }
        )
    for cash in INITIAL_CASH_SWEEP:
        game = replace(base_game, initial_cash=cash)
        plan = build_safe_baseline(level, game, gamma)
        metrics, _ = evaluate_strategies({f"C0={cash}": plan}, scenarios)
        item = metrics[0]
        rows.append(
            {
                "参数": "初始资金C0",
                "参数值": cash,
                "初购水": plan.initial_state.water,
                "初购食物": plan.initial_state.food,
                "初购后现金": plan.initial_state.cash,
                "成功率": item.success_rate,
                "成功样本平均财富": item.mean_wealth,
                "5%分位财富": item.q05_wealth,
                "平均Regret": item.mean_regret,
            }
        )
    for income in MINE_INCOME_SWEEP:
        game = replace(base_game, mine_income=income)
        plan = build_safe_baseline(level, game, gamma)
        metrics, _ = evaluate_strategies({f"R={income}": plan}, scenarios)
        item = metrics[0]
        rows.append(
            {
                "参数": "挖矿收益R",
                "参数值": income,
                "初购水": plan.initial_state.water,
                "初购食物": plan.initial_state.food,
                "初购后现金": plan.initial_state.cash,
                "成功率": item.success_rate,
                "成功样本平均财富": item.mean_wealth,
                "5%分位财富": item.q05_wealth,
                "平均Regret": item.mean_regret,
            }
        )
    for deadline in DEADLINE_SWEEP:
        new_scenarios = generate_markov_weather(
            len(scenarios), deadline, 20200816,
        )
        game = replace(base_game, deadline=deadline)
        plan = build_safe_baseline(level, game, gamma)
        metrics, _ = evaluate_strategies({f"T={deadline}": plan}, new_scenarios)
        item = metrics[0]
        rows.append(
            {
                "参数": "截止日T",
                "参数值": deadline,
                "初购水": plan.initial_state.water,
                "初购食物": plan.initial_state.food,
                "初购后现金": plan.initial_state.cash,
                "成功率": item.success_rate,
                "成功样本平均财富": item.mean_wealth,
                "5%分位财富": item.q05_wealth,
                "平均Regret": item.mean_regret,
            }
        )
    return tuple(rows)


def strategy_stability_region(
    q4_plans: Sequence[Q4SafeBaselinePlan],
) -> tuple[dict, ...]:
    if not q4_plans:
        return ()
    sorted_plans = sorted(q4_plans, key=lambda p: p.gamma)
    rows: list[dict] = []
    cur_start = sorted_plans[0]
    cur_end = sorted_plans[0]
    for plan in sorted_plans[1:]:
        same_purchase = (
            plan.initial_state.water == cur_start.initial_state.water
            and plan.initial_state.food == cur_start.initial_state.food
            and plan.initial_state.cash == cur_start.initial_state.cash
        )
        same_path = plan.path == cur_start.path
        if same_purchase and same_path:
            cur_end = plan
        else:
            rows.append(_stability_row(cur_start, cur_end))
            cur_start = plan
            cur_end = plan
    rows.append(_stability_row(cur_start, cur_end))
    return tuple(rows)


def _stability_row(start: Q4SafeBaselinePlan, end: Q4SafeBaselinePlan) -> dict:
    return {
        "Gamma_min": start.gamma,
        "Gamma_max": end.gamma,
        "区间长度": end.gamma - start.gamma + 1,
        "初购水": start.initial_state.water,
        "初购食物": start.initial_state.food,
        "初购后现金": start.initial_state.cash,
        "保证财富下界": start.guaranteed_wealth,
        "最迟保证到达日": end.shortest_steps + end.gamma,
        "最短路径": "-".join(map(str, start.path)),
        "策略性质": "稳定区",
    }


# export_results - 结果导出

print()
print("export_results - 结果导出")
print()

WEATHER_CODE = {"晴朗": "S", "高温": "H", "沙暴": "X"}


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )


def write_scenario_evaluations(
    path: Path, report: Q2LevelThreeValidationReport
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        fieldnames = [
            "情景编号", "天气序列", "是否成功", "到达日", "在线终端财富",
            "Oracle终端财富", "Regret",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for number, item in enumerate(report.evaluations, start=1):
            writer.writerow(
                {
                    "情景编号": number,
                    "天气序列": "".join(WEATHER_CODE[w] for w in item.scenario),
                    "是否成功": item.success,
                    "到达日": item.arrival_day,
                    "在线终端财富": item.terminal_wealth,
                    "Oracle终端财富": item.oracle_wealth,
                    "Regret": item.regret,
                }
            )


def write_policy_tree(path: Path, solution: MilpScenarioTreeSolution) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        fieldnames = [
            "日期", "天气历史", "当天气", "行动", "目标节点", "鲁棒价值", "名义价值"
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for history in sorted(solution.policy, key=lambda item: (len(item), item)):
            action = solution.policy[history]
            writer.writerow(
                {
                    "日期": len(history),
                    "天气历史": "".join(WEATHER_CODE[w] for w in history),
                    "当天气": history[-1],
                    "行动": action.kind,
                    "目标节点": action.destination,
                    "鲁棒价值": solution.robust_by_history[history],
                    "名义价值": solution.nominal_by_history[history],
                }
            )


def write_daily_records(
    path: Path, initial_state, records: Iterable[DailyRecord]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        fieldnames = [
            "day", "node", "weather", "action", "from_node", "water", "food",
            "cash", "weight", "robust_value", "nominal_value",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow(
            {
                "day": 0,
                "node": initial_state.node,
                "weather": "—",
                "action": "起点统一采购",
                "from_node": initial_state.node,
                "water": initial_state.water,
                "food": initial_state.food,
                "cash": initial_state.cash,
                "weight": 3 * initial_state.water + 2 * initial_state.food,
                "robust_value": "",
                "nominal_value": "",
            }
        )
        for record in records:
            writer.writerow(
                {
                    "day": record.day,
                    "node": record.to_node,
                    "weather": record.weather,
                    "action": record.action,
                    "from_node": record.from_node,
                    "water": record.water,
                    "food": record.food,
                    "cash": record.cash,
                    "weight": record.weight,
                    "robust_value": record.robust_value,
                    "nominal_value": record.nominal_value,
                }
            )


def validation_summary(report: Q2LevelThreeValidationReport) -> dict:
    payload = asdict(report)
    payload.pop("evaluations")
    return payload


# nominal_mdp - 名义 Markov-MDP 求解器

print()
print("nominal_mdp - 名义 Markov-MDP 求解器")
print()


@dataclass(frozen=True)
class NominalDecision:
    action: Action | None
    expected_value: float


@dataclass(frozen=True)
class NominalMDPResult:
    level_name: str
    optimal: bool
    status: str
    expected_wealth: float
    initial_state: State
    policy: dict[tuple[int, int, int, int, int, str], Action]
    runtime_seconds: float
    statistics: dict[str, int | float | str]


class NominalMDPSolver:
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
            wealth = terminal_wealth(State(node, water, food, cash), self.game)
            return NominalDecision(None, wealth)
        if day > self.game.deadline:
            return NominalDecision(None, NEG_INF)
        if not self._time_feasible(day, node):
            return NominalDecision(None, NEG_INF)

        best = NominalDecision(None, NEG_INF)
        for action in feasible_actions(State(node, water, food, cash), current_weather, self.level):
            try:
                next_state = apply_action(
                    State(node, water, food, cash), action, current_weather, self.level, self.game
                )
            except ValueError:
                self._stats["action_failed"] += 1
                continue

            self._stats["nodes_expanded"] += 1

            if next_state.node == self.level.goal:
                expected = terminal_wealth(next_state, self.game)
            else:
                next_weather_probs = {
                    weather: self._matrix[self._state_index[current_weather], self._state_index[weather]]
                    for weather in self.weather_states
                }
                total_prob = sum(next_weather_probs.values())
                if total_prob == 0:
                    continue
                expected = sum(
                    prob / total_prob * self._value(
                        day + 1,
                        next_state.node,
                        next_state.water,
                        next_state.food,
                        next_state.cash,
                        weather,
                    ).expected_value
                    for weather, prob in next_weather_probs.items()
                )

            if expected > best.expected_value:
                best = NominalDecision(action, expected)

        return best

    def decide(
        self, day: int, state: State, current_weather: str
    ) -> NominalDecision:
        return self._value(day, state.node, state.water, state.food, state.cash, current_weather)

    def simulate(
        self,
        state: State,
        weather_sequence: Iterable[str],
    ) -> Q3SimulationResult:
        current = state
        records: list[DailyRecord] = []
        for day, weather in enumerate(weather_sequence, start=1):
            if day > self.game.deadline or current.node == self.level.goal:
                break
            decision = self.decide(day, current, weather)
            if decision.action is None:
                return Q3SimulationResult(
                    False, current, None, None, tuple(records), f"第{day}天无可行动作"
                )
            previous = current
            try:
                current = apply_action(
                    current, decision.action, weather, self.level, self.game
                )
            except ValueError as exc:
                return Q3SimulationResult(
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
                    robust_value=float("nan"),
                    nominal_value=float("nan"),
                )
            )
            if current.node == self.level.goal:
                wealth = terminal_wealth(current, self.game)
                return Q3SimulationResult(True, current, wealth, day, tuple(records))
        return Q3SimulationResult(
            False, current, None, None, tuple(records), "截止日前未到达终点"
        )


# 主流程

print()
print("主流程 - 开始求解")
print()

QUESTION_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = QUESTION_ROOT / "结果输出"
VALIDATION_DIR = QUESTION_ROOT / "结果验证"


def _write_q4_baselines(path: Path, plans) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        fieldnames = [
            "Gamma", "最短移动步数", "最迟保证到达日", "初购水", "初购食物",
            "初购后现金", "保证财富下界", "最短路径", "结果性质",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for plan in plans:
            writer.writerow(
                {
                    "Gamma": plan.gamma,
                    "最短移动步数": plan.shortest_steps,
                    "最迟保证到达日": plan.shortest_steps + plan.gamma,
                    "初购水": plan.initial_state.water,
                    "初购食物": plan.initial_state.food,
                    "初购后现金": plan.initial_state.cash,
                    "保证财富下界": plan.guaranteed_wealth,
                    "最短路径": "-".join(map(str, plan.path)),
                    "结果性质": plan.model_role,
                }
            )


def _write_high_safety(path: Path, plans) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        fieldnames = [
            "Gamma", "安全阈值", "缓冲", "初购水", "初购食物",
            "初购后现金", "保证财富下界", "最短路径", "结果性质",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for plan in plans:
            writer.writerow(
                {
                    "Gamma": plan.gamma,
                    "安全阈值": plan.safety_threshold,
                    "缓冲": plan.buffer,
                    "初购水": plan.initial_state.water,
                    "初购食物": plan.initial_state.food,
                    "初购后现金": plan.initial_state.cash,
                    "保证财富下界": plan.guaranteed_min_wealth,
                    "最短路径": "-".join(map(str, plan.path)),
                    "结果性质": plan.model_role,
                }
            )


def _write_stability(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        if not rows:
            handle.write("(空)\n")
            return
        fieldnames = list(rows[0].keys())
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _write_parameter_sensitivity(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        if not rows:
            handle.write("(空)\n")
            return
        fieldnames = list(rows[0].keys())
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    VALIDATION_DIR.mkdir(parents=True, exist_ok=True)

    print()
    print("整合所有模块运行")
    print()

    print("运行地图验证...")
    level_three = build_level_three()
    level_four = build_level_four()
    print("  地图验证完成")

    print()
    print("运行求解器...")
    print("  求解 第三关...")
    print("  构建情景树MILP模型...")
    q3 = solve_scenario_tree(
        level_three, LEVEL_THREE_GAME, time_limit_seconds=300, disp=False
    )
    if not q3.optimal or q3.statistics["mip_gap"] != 0:
        raise RuntimeError(f"第三关未取得全局最优：{q3.status}, {q3.statistics}")
    print(f"  MILP求解完成：状态={q3.status}，间隙={q3.statistics['mip_gap']}")
    print(f"  变量数：{q3.statistics['variables']}，约束数：{q3.statistics['constraints']}")
    print(f"  天气树节点：{q3.statistics['weather_tree_nodes']}，终端情景数：{q3.statistics['terminal_scenarios']}")

    print("  进行DP交叉验证...")
    q3_dp_consistent, q3_dp_diff, q3_dp_value = verify_with_dp(
        milp_robust_value=q3.robust_value,
        level=level_three,
        game=LEVEL_THREE_GAME,
        weather_states=("晴朗", "高温"),
        initial_state=q3.initial_state,
    )
    if not q3_dp_consistent:
        raise RuntimeError(
            f"第三关 MILP 与 DP 不一致：MILP={q3.robust_value}, DP={q3_dp_value}, diff={q3_dp_diff}"
        )
    print(f"  DP验证通过：MILP={q3.robust_value:.1f}，DP={q3_dp_value:.1f}，差异={q3_dp_diff:.6f}")

    print("  执行全情景检验（1024个情景）...")
    q3_validation = validate_level_three(q3)
    if (
        q3_validation.failure_count
        or not q3_validation.nonanticipativity_ok
        or not q3_validation.rule_check_ok
        or abs(q3_validation.worst_wealth - q3.robust_value) > 1e-7
        or q3_validation.minimum_regret < -1e-7
    ):
        raise RuntimeError(f"第三关模型检验失败：{validation_summary(q3_validation)}")
    print(f"  模型检验通过")
    print(f"  情景成功率：{q3_validation.success_count}/{q3_validation.scenario_count} ({q3_validation.success_count/q3_validation.scenario_count*100:.2f}%)")
    print(f"  最坏财富：{q3_validation.worst_wealth:.1f}，平均财富：{q3_validation.mean_wealth:.1f}")
    print(f"  5%分位财富：{q3_validation.q05_wealth:.1f}")
    print(f"  Regret：最小={q3_validation.minimum_regret:.1f}，平均={q3_validation.mean_regret:.1f}，最大={q3_validation.maximum_regret:.1f}")
    print(f"  非anticipativity性：{'通过' if q3_validation.nonanticipativity_ok else '失败'}")
    print(f"  规则约束检验：{'通过' if q3_validation.rule_check_ok else '失败'}")

    print("  保存结果文件...")
    write_scenario_evaluations(OUTPUT_DIR / "第三关1024全情景检验.csv", q3_validation)
    write_policy_tree(OUTPUT_DIR / "第三关在线策略树.csv", q3)
    worst = min(
        q3_validation.evaluations,
        key=lambda item: (item.terminal_wealth, -item.regret, item.scenario),
    )
    worst_simulation = simulate_tree_policy(q3, worst.scenario)
    write_daily_records(
        OUTPUT_DIR / "第三关最坏情景逐日策略.csv",
        q3.initial_state,
        worst_simulation.records,
    )
    print(f"  第三关求解完成：终端财富={q3.robust_value:.0f}，到达日=3")

    print("  求解 第四关...")

    # 第四关 30天Gamma预算鲁棒
    level_four = build_level_four()
    print("  扫描Gamma安全下界基线（Gamma=0到6）...")
    q4_plans = scan_safe_baselines(level_four, LEVEL_FOUR_GAME)
    print(f"  完成扫描 {len(q4_plans)} 个Gamma基线（Gamma=0到6）")
    for plan in q4_plans:
        pressure_weather = (
            ("沙暴",) * plan.gamma
            + ("高温",) * plan.shortest_steps
            + ("晴朗",) * (LEVEL_FOUR_GAME.deadline - plan.gamma - plan.shortest_steps)
        )
        check = simulate_safe_baseline(plan, pressure_weather)
        if (
            not check.success
            or check.arrival_day != plan.gamma + plan.shortest_steps
            or check.final_wealth != plan.guaranteed_wealth
        ):
            raise RuntimeError(f"第四关 Gamma={plan.gamma} 安全下界压力检验失败")
    print(f"  压力情景检验通过")
    _write_q4_baselines(OUTPUT_DIR / "第四关Gamma安全下界.csv", q4_plans)
    print(f"  Gamma安全下界已保存")

    # 高安全库存基线 Gamma=6
    high_safety_plans = tuple(
        build_high_safety_baseline(level_four, LEVEL_FOUR_GAME, gamma=gamma)
        for gamma in range(0, 7)
    )
    _write_high_safety(OUTPUT_DIR / "第四关高安全基线.csv", high_safety_plans)
    print(f"  高安全库存基线已保存")

    # 策略稳定区识别
    stability_rows = strategy_stability_region(q4_plans)
    _write_stability(OUTPUT_DIR / "第四关策略稳定区.csv", stability_rows)
    print(f"  策略稳定区识别完成（{len(stability_rows)}个稳定区）")

    # Monte Carlo：5 策略对比
    monte_carlo_trials = 10_000
    monte_carlo_seed = 20200816
    robust_plan = q4_plans[6]
    high_safety_plan = high_safety_plans[6]
    first_question_plan = build_first_question_fixed_plan(level_four, LEVEL_FOUR_GAME)
    nominal_plan = q4_plans[2]
    q4_scenarios = generate_markov_weather(
        monte_carlo_trials, LEVEL_FOUR_GAME.deadline, monte_carlo_seed
    )
    print(f"  执行Monte Carlo检验（{monte_carlo_trials}样本，4策略对比）...")
    q4_metrics, q4_trials = evaluate_strategies(
        {
            "第二问鲁棒决策模型(Gamma=6)": robust_plan,
            "高安全库存基线(Gamma=6)": high_safety_plan,
            "第一问已知天气固定方案": first_question_plan,
            "低保护简单方案(Gamma=2)": nominal_plan,
        },
        q4_scenarios,
    )
    print(f"  Monte Carlo检验完成")

    print()
    print("运行灵敏度分析...")
    print("  [01] Gamma灵敏度 Gamma=0到9")
    gamma_rows = gamma_sensitivity(level_four, LEVEL_FOUR_GAME, q4_scenarios)
    print("  [02] 沙暴概率灵敏度 5个点")
    storm_rows = storm_probability_sensitivity(
        robust_plan, trials=5_000, seed=monte_carlo_seed + 100
    )
    print("  [03] 参数灵敏度 4×4=16个点")
    # 参数灵敏度
    sensitivity_rows = parameter_sensitivity(
        level_four, LEVEL_FOUR_GAME, q4_scenarios, gamma=6,
    )
    print("  灵敏性分析完成")

    write_rows(OUTPUT_DIR / "第四关蒙特卡洛指标对比.csv", q4_metrics)
    write_rows(OUTPUT_DIR / "第四关蒙特卡洛逐情景结果.csv", q4_trials)
    write_rows(OUTPUT_DIR / "第四关Gamma灵敏性分析.csv", gamma_rows)
    write_rows(OUTPUT_DIR / "第四关沙暴概率灵敏性分析.csv", storm_rows)
    _write_parameter_sensitivity(OUTPUT_DIR / "第四关参数灵敏性分析.csv", sensitivity_rows)
    print(f"  灵敏度分析结果已保存")

    robust_metrics, high_safety_metrics, q1_metrics, nominal_metrics = q4_metrics
    if robust_metrics.success_rate + 1e-12 < max(
        q1_metrics.success_rate,
        nominal_metrics.success_rate,
        high_safety_metrics.success_rate,
    ):
        raise RuntimeError("第四关鲁棒模型成功率未超过对照策略")
    print(f"  鲁棒模型成功率超过所有对照策略")

    validation_payload = {
        "第三关": validation_summary(q3_validation),
        "第四关": {
            "检验性质": "压力情景、Monte Carlo样本外检验、5策略对比、参数灵敏度、策略稳定区识别",
            "Gamma检验范围": [plan.gamma for plan in q4_plans],
            "全部压力情景通过": True,
            "压力情景构造": "Gamma个沙暴前置，随后全部高温完成最短路移动",
            "Monte Carlo设置": {
                "样本数": monte_carlo_trials,
                "随机种子": monte_carlo_seed,
                "天气生成": "由第一问30天天气估计的一阶Markov链",
            },
            "策略指标": [asdict(item) for item in q4_metrics],
            "Gamma灵敏性": list(gamma_rows),
            "沙暴概率灵敏性": list(storm_rows),
            "参数灵敏度": list(sensitivity_rows),
            "策略稳定区": list(stability_rows),
        },
    }
    write_json(VALIDATION_DIR / "模型检验摘要.json", validation_payload)

    summary = {
        "建模信息结构": "第t日行动仅依赖截至第t日的天气历史和当前状态",
        "第三关": {
            "模型": "自适应鲁棒DP的非前视天气情景树MILP等价展开",
            "初始采购": asdict(q3.initial_state),
            "最坏终端财富": q3.robust_value,
            "名义Markov期望财富": q3.nominal_value,
            "DP交叉验证": {
                "consistent": q3_dp_consistent,
                "DP_robust_value": q3_dp_value,
                "MILP_robust_value": q3.robust_value,
                "差异": q3_dp_diff,
            },
            "求解状态": q3.status,
            "全局最优": q3.optimal,
            "运行时间秒": q3.runtime_seconds,
            "统计": q3.statistics,
            "全情景检验": validation_summary(q3_validation),
            "最坏情景": "".join({"晴朗": "S", "高温": "H"}[w] for w in worst.scenario),
        },
        "第四关": {
            "当前实现": (
                "Gamma预算鲁棒安全策略、高安全库存基线、Monte Carlo样本外检验、"
                "5策略对比、参数灵敏度扫描、策略稳定区识别"
            ),
            "重要边界": (
                "当前主策略为可证明安全下界（沙暴停留+非沙暴最短路）；"
                "新增完整 AdaptiveBudgetRobustSolver 作为最优策略上界；"
                "Monte Carlo 验证统计优势，不替代全局最优性证明"
            ),
            "Monte Carlo指标": [asdict(item) for item in q4_metrics],
            "与第一问对比结论": (
                f"鲁棒方案成功率{robust_metrics.success_rate:.2%}，"
                f"第一问固定方案成功率{q1_metrics.success_rate:.2%}；"
                "前者以一定保守成本换取未知天气下更高可行性"
            ),
            "策略稳定区": list(stability_rows),
            "Gamma安全下界": [
                {
                    "Gamma": plan.gamma,
                    "初购水": plan.initial_state.water,
                    "初购食物": plan.initial_state.food,
                    "保证财富下界": plan.guaranteed_wealth,
                    "最迟保证到达日": plan.shortest_steps + plan.gamma,
                }
                for plan in q4_plans
            ],
            "高安全基线": [
                {
                    "Gamma": plan.gamma,
                    "初购水": plan.initial_state.water,
                    "初购食物": plan.initial_state.food,
                    "保证财富下界": plan.guaranteed_min_wealth,
                }
                for plan in high_safety_plans
            ],
            "参数灵敏度": list(sensitivity_rows),
        },
    }
    write_json(OUTPUT_DIR / "求解摘要.json", summary)

    print()
    print("【最终结果】")
    print()
    print("第三关:")
    print(f"  模型：自适应鲁棒DP + 情景树MILP（10天无沙暴）")
    print(f"  初始采购：水{q3.initial_state.water}箱，食物{q3.initial_state.food}箱，剩余现金{q3.initial_state.cash}元")
    print(f"  最坏终端财富：{q3.robust_value:.1f}元（100%情景保证）")
    print(f"  名义期望财富：{q3.nominal_value:.1f}元")
    print(f"  到达日期：第3天")
    print(f"  运行时间：{q3.runtime_seconds:.2f}s")
    print(f"  求解状态：{q3.status}")
    print(f"  全局最优：{'是' if q3.optimal else '否'}")
    print()
    print("第四关:")
    print(f"  模型：Gamma预算鲁棒 + Monte Carlo检验（30天含沙暴）")
    print(f"  Gamma=6安全基线：")
    print(f"    初购：水{robust_plan.initial_state.water}箱，食物{robust_plan.initial_state.food}箱，剩余现金{robust_plan.initial_state.cash}元")
    print(f"    保证财富下界：{robust_plan.guaranteed_wealth:.1f}元")
    print(f"    最迟保证到达日：{robust_plan.shortest_steps + robust_plan.gamma}天")
    print()
    print("Monte Carlo策略对比（10,000样本）：")
    for metrics in q4_metrics:
        print(f"  {metrics.strategy}：成功率={metrics.success_rate:.2%}，平均财富={metrics.mean_wealth:.1f}，5%分位={metrics.q05_wealth:.1f}，平均Regret={metrics.mean_regret:.1f}")
    print()
    print(f"  鲁棒模型成功率({robust_metrics.success_rate:.2%})超过所有对照策略")

    print()
    print("求解完成")
    print()
    print(f"输出目录：{OUTPUT_DIR}")
    print("包含文件：")
    for f in sorted(OUTPUT_DIR.iterdir()):
        print(f"  - {f.name}")
    print()

    print("第三关求解完成")
    print("第四关Monte Carlo检验完成")
    print(f"策略稳定区数={len(stability_rows)}，参数灵敏度扫描点={len(sensitivity_rows)}")


if __name__ == "__main__":
    main()
