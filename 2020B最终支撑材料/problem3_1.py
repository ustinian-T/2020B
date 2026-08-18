#!/usr/bin/env python3
"""
2020B 第三问（1）- 第五关：双玩家博弈均衡策略

"""

from __future__ import annotations

import csv
import json
from collections import Counter, deque
from dataclasses import dataclass, replace
from math import inf
from pathlib import Path
from typing import Iterable, Mapping, Sequence
import numpy as np


# config - 配置参数和地图定义

print()
print("config - 配置参数和地图定义")
print()

Weather = str


@dataclass(frozen=True)
class GameConfig:
    """游戏全局配置"""
    player_count: int
    capacity_kg: int
    initial_cash: int
    deadline: int
    mine_income: int
    water_weight: int = 3
    food_weight: int = 2
    water_price: int = 5
    food_price: int = 10
    base_consumption: Mapping[Weather, tuple[int, int]] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.base_consumption is None:
            object.__setattr__(
                self,
                "base_consumption",
                {"晴朗": (3, 4), "高温": (9, 9), "沙暴": (10, 10)},
            )


@dataclass(frozen=True)
class LevelConfig:
    """关卡配置"""
    name: str
    node_count: int
    edges: tuple[tuple[int, int], ...]
    neighbors: Mapping[int, frozenset[int]]
    start: int
    goal: int
    villages: frozenset[int]
    mines: frozenset[int]


LEVEL5_EDGES = (
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

LEVEL5_WEATHER = (
    "晴朗", "高温", "晴朗", "晴朗", "晴朗",
    "晴朗", "高温", "高温", "高温", "高温",
)

LEVEL5_GAME = GameConfig(
    player_count=2,
    capacity_kg=1200,
    initial_cash=10000,
    deadline=10,
    mine_income=200,
)


def make_level(
    name: str,
    node_count: int,
    edges: tuple[tuple[int, int], ...],
    start: int,
    goal: int,
    villages: frozenset[int],
    mines: frozenset[int],
) -> LevelConfig:
    """构建关卡配置"""
    normalized = tuple(sorted((min(u, v), max(u, v)) for u, v in edges))
    adjacency = {node: set() for node in range(1, node_count + 1)}
    for u, v in normalized:
        if u == v or u not in adjacency or v not in adjacency:
            raise ValueError(f"非法边：{u}-{v}")
        adjacency[u].add(v)
        adjacency[v].add(u)
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


print(f"第五关地图：{13}节点，{len(LEVEL5_EDGES)}条边")
print(f"天气序列：{len(LEVEL5_WEATHER)}天")
print(f"玩家数：{LEVEL5_GAME.player_count}")
print()

# transition - 状态转移与动作定义

print()
print("transition - 状态转移与动作定义")
print()


@dataclass(frozen=True, order=True)
class PlayerState:
    """玩家状态"""
    node: int
    water: int
    food: int
    cash: float
    arrived: bool = False


@dataclass(frozen=True, order=True)
class Action:
    """动作"""
    kind: str
    destination: int | None = None
    buy_water: int = 0
    buy_food: int = 0

    @classmethod
    def move(cls, destination: int) -> "Action":
        return cls("行走", destination)

    @classmethod
    def stay(cls) -> "Action":
        return cls("停留")

    @classmethod
    def mine(cls) -> "Action":
        return cls("挖矿")

    @classmethod
    def exit(cls) -> "Action":
        return cls("退出")


@dataclass(frozen=True)
class JointStep:
    """联合步骤结果"""
    states: tuple[PlayerState, ...]
    edge_counts: Mapping[tuple[int, int], int]
    mine_counts: Mapping[int, int]
    village_counts: Mapping[int, int]
    water_consumption: tuple[int, ...]
    food_consumption: tuple[int, ...]
    mine_income: tuple[float, ...]


def total_weight(state: PlayerState, game: GameConfig) -> int:
    """计算总负重"""
    return game.water_weight * state.water + game.food_weight * state.food


def terminal_wealth(state: PlayerState, game: GameConfig) -> float:
    """计算终端财富"""
    if not state.arrived:
        raise ValueError("仅到达终点的状态可以清算")
    return (
        state.cash
        + 0.5 * game.water_price * state.water
        + 0.5 * game.food_price * state.food
    )


def initial_state(
    water: int,
    food: int,
    game: GameConfig,
    level: LevelConfig,
) -> PlayerState:
    """初始化玩家状态"""
    if not isinstance(water, int) or not isinstance(food, int) or min(water, food) < 0:
        raise ValueError("初始采购必须为非负整数箱")
    cash = game.initial_cash - game.water_price * water - game.food_price * food
    state = PlayerState(level.start, water, food, float(cash))
    if state.cash < 0:
        raise ValueError("初始采购导致资金为负")
    if total_weight(state, game) > game.capacity_kg:
        raise ValueError("初始采购超过负重上限")
    return state


def legal_actions(
    state: PlayerState,
    weather: str,
    level: LevelConfig,
) -> tuple[Action, ...]:
    """获取合法动作集合"""
    if state.arrived:
        return (Action.exit(),)
    actions = [Action.stay()]
    if state.node in level.mines:
        actions.append(Action.mine())
    if weather != "沙暴":
        actions.extend(Action.move(node) for node in sorted(level.neighbors[state.node]))
    return tuple(actions)


def _validate_action(
    state: PlayerState,
    action: Action,
    weather: str,
    level: LevelConfig,
) -> None:
    """验证动作合法性"""
    if state.arrived:
        if action.kind != "退出":
            raise ValueError("已到达玩家必须退出后续互动")
        return
    if action.buy_water or action.buy_food:
        raise ValueError("第五关没有村庄，不能在途中购买")
    if action.kind == "行走":
        if weather == "沙暴":
            raise ValueError("沙暴日禁止移动")
        if action.destination not in level.neighbors[state.node]:
            raise ValueError("只能移动到相邻节点")
    elif action.kind == "挖矿":
        if state.node not in level.mines:
            raise ValueError("仅能在矿山挖矿")
    elif action.kind == "停留":
        if action.destination not in (None, state.node):
            raise ValueError("停留动作不能改变位置")
    else:
        raise ValueError(f"未知行动：{action.kind}")


def step_joint(
    states: Sequence[PlayerState],
    actions: Sequence[Action],
    weather: str,
    game: GameConfig,
    level: LevelConfig,
) -> JointStep:
    """联合状态转移"""
    if len(states) != game.player_count or len(actions) != game.player_count:
        raise ValueError("玩家状态和动作数量必须等于玩家数")
    if weather not in game.base_consumption:
        raise ValueError(f"未知天气：{weather}")
    for state, action in zip(states, actions):
        _validate_action(state, action, weather, level)

    edge_counts = Counter(
        (state.node, int(action.destination))
        for state, action in zip(states, actions)
        if not state.arrived and action.kind == "行走"
    )
    mine_counts = Counter(
        state.node
        for state, action in zip(states, actions)
        if not state.arrived and action.kind == "挖矿"
    )
    village_counts: Counter[int] = Counter()
    base_water, base_food = game.base_consumption[weather]
    next_states: list[PlayerState] = []
    water_used: list[int] = []
    food_used: list[int] = []
    income_rows: list[float] = []

    for state, action in zip(states, actions):
        if state.arrived:
            next_states.append(state)
            water_used.append(0)
            food_used.append(0)
            income_rows.append(0.0)
            continue
        if action.kind == "行走":
            multiplier = 2 * edge_counts[(state.node, int(action.destination))]
            destination = int(action.destination)
        elif action.kind == "挖矿":
            multiplier = 3
            destination = state.node
        else:
            multiplier = 1
            destination = state.node
        consumed_water = multiplier * base_water
        consumed_food = multiplier * base_food
        water = state.water - consumed_water
        food = state.food - consumed_food
        if water < 0 or food < 0:
            raise ValueError("行动所需资源不足")
        arrived = destination == level.goal
        if not arrived and (water < 1 or food < 1):
            raise ValueError("未到终点时资源必须保持为正")
        income = (
            game.mine_income / mine_counts[state.node]
            if action.kind == "挖矿"
            else 0.0
        )
        next_states.append(
            PlayerState(
                node=destination,
                water=water,
                food=food,
                cash=state.cash + income,
                arrived=arrived,
            )
        )
        water_used.append(consumed_water)
        food_used.append(consumed_food)
        income_rows.append(income)

    return JointStep(
        states=tuple(next_states),
        edge_counts=dict(edge_counts),
        mine_counts=dict(mine_counts),
        village_counts=dict(village_counts),
        water_consumption=tuple(water_used),
        food_consumption=tuple(food_used),
        mine_income=tuple(income_rows),
    )


print("状态转移和动作定义加载完成")
print()

# single_dp - 单玩家动态规划求解器

print()
print("single_dp - 单玩家动态规划求解器")
print()


@dataclass(frozen=True)
class Plan:
    """策略计划"""
    initial_water: int
    initial_food: int
    actions: tuple[Action, ...]


@dataclass(frozen=True)
class DailyRecord:
    """逐日记录"""
    day: int
    weather: str
    from_node: int
    to_node: int
    action: str
    multiplier: int
    water: int
    food: int
    cash: float
    edge_companions: int
    mine_companions: int


@dataclass(frozen=True)
class PlanResult:
    """策略结果"""
    plan: Plan
    feasible: bool
    terminal_wealth: float
    arrival_day: int | None
    final_state: PlayerState | None
    records: tuple[DailyRecord, ...]
    failure_reason: str = ""


@dataclass(frozen=True)
class _OpponentEvent:
    kind: str
    from_node: int
    to_node: int


@dataclass(frozen=True)
class _Label:
    node: int
    water_used: int
    food_used: int
    mine_income: float
    actions: tuple[Action, ...]


def _opponent_timeline(
    plan: Plan,
    level: LevelConfig,
    days: int,
) -> tuple[_OpponentEvent | None, ...]:
    """构建对手时间线"""
    node = level.start
    arrived = False
    events: list[_OpponentEvent | None] = []
    for day in range(days):
        if arrived or day >= len(plan.actions):
            events.append(None)
            continue
        action = plan.actions[day]
        if action.kind == "行走":
            destination = int(action.destination)
        else:
            destination = node
        events.append(_OpponentEvent(action.kind, node, destination))
        node = destination
        arrived = node == level.goal
    return tuple(events)


def _all_opponent_timelines(
    opponents: Sequence[Plan],
    level: LevelConfig,
    days: int,
) -> tuple[tuple[_OpponentEvent | None, ...], ...]:
    """构建所有对手时间线"""
    return tuple(_opponent_timeline(plan, level, days) for plan in opponents)


def _externality(
    day_index: int,
    node: int,
    action: Action,
    timelines: Sequence[Sequence[_OpponentEvent | None]],
) -> tuple[int, int]:
    """计算外部性（同边/同矿对手数）"""
    edge_companions = 0
    mine_companions = 0
    for timeline in timelines:
        event = timeline[day_index]
        if event is None:
            continue
        if (
            action.kind == "行走"
            and event.kind == "行走"
            and event.from_node == node
            and event.to_node == action.destination
        ):
            edge_companions += 1
        if action.kind == "挖矿" and event.kind == "挖矿" and event.from_node == node:
            mine_companions += 1
    return edge_companions, mine_companions


def _dominates(left: _Label, right: _Label) -> bool:
    """Pareto支配判断"""
    return (
        left.water_used <= right.water_used
        and left.food_used <= right.food_used
        and left.mine_income >= right.mine_income
        and (
            left.water_used < right.water_used
            or left.food_used < right.food_used
            or left.mine_income > right.mine_income
        )
    )


def _insert_pareto(frontier: list[_Label], candidate: _Label) -> None:
    """Pareto前沿插入"""
    for existing in frontier:
        if (
            existing.water_used == candidate.water_used
            and existing.food_used == candidate.food_used
            and existing.mine_income >= candidate.mine_income
        ) or _dominates(existing, candidate):
            return
    frontier[:] = [item for item in frontier if not _dominates(candidate, item)]
    frontier.append(candidate)


def _action_effect(
    node: int,
    action: Action,
    weather: str,
    edge_companions: int,
    mine_companions: int,
    game: GameConfig,
) -> tuple[int, int, float, int]:
    """计算行动效果"""
    base_water, base_food = game.base_consumption[weather]
    if action.kind == "行走":
        multiplier = 2 * (edge_companions + 1)
    elif action.kind == "挖矿":
        multiplier = 3
    else:
        multiplier = 1
    income = game.mine_income / (mine_companions + 1) if action.kind == "挖矿" else 0.0
    return multiplier * base_water, multiplier * base_food, income, multiplier


def best_response(
    opponents: Sequence[Plan],
    game: GameConfig,
    level: LevelConfig,
    weather: tuple[str, ...],
) -> PlanResult:
    """计算最优响应"""
    if len(weather) != game.deadline:
        raise ValueError("天气长度必须等于截止天数")
    timelines = _all_opponent_timelines(opponents, level, game.deadline)
    frontier: dict[int, list[_Label]] = {
        level.start: [_Label(level.start, 0, 0, 0.0, ())]
    }
    terminal: list[tuple[_Label, int]] = []

    for day, day_weather in enumerate(weather, start=1):
        next_frontier: dict[int, list[_Label]] = {}
        for labels in frontier.values():
            for label in labels:
                dummy = PlayerState(label.node, 1, 1, 0.0)
                for action in legal_actions(dummy, day_weather, level):
                    edge_h, mine_h = _externality(
                        day - 1, label.node, action, timelines
                    )
                    water, food, income, _ = _action_effect(
                        label.node, action, day_weather, edge_h, mine_h, game
                    )
                    water_used = label.water_used + water
                    food_used = label.food_used + food
                    if game.water_weight * water_used + game.food_weight * food_used > game.capacity_kg:
                        continue
                    if game.water_price * water_used + game.food_price * food_used > game.initial_cash:
                        continue
                    destination = int(action.destination) if action.kind == "行走" else label.node
                    candidate = _Label(
                        node=destination,
                        water_used=water_used,
                        food_used=food_used,
                        mine_income=label.mine_income + income,
                        actions=label.actions + (action,),
                    )
                    if destination == level.goal:
                        terminal.append((candidate, day))
                    elif day < game.deadline:
                        _insert_pareto(next_frontier.setdefault(destination, []), candidate)
        frontier = next_frontier

    if not terminal:
        raise RuntimeError("不存在截止日前可行的最优响应")

    def score(item: tuple[_Label, int]) -> tuple[float, int, int, int, tuple[Action, ...]]:
        label, arrival = item
        wealth = (
            game.initial_cash
            - game.water_price * label.water_used
            - game.food_price * label.food_used
            + label.mine_income
        )
        return wealth, -arrival, -label.water_used, -label.food_used, tuple(reversed(label.actions))

    best, _ = max(terminal, key=score)
    plan = Plan(best.water_used, best.food_used, best.actions)
    return evaluate_plan(plan, opponents, game, level, weather)


def evaluate_plan(
    plan: Plan,
    opponents: Sequence[Plan],
    game: GameConfig,
    level: LevelConfig,
    weather: tuple[str, ...],
) -> PlanResult:
    """评估策略"""
    try:
        state = initial_state(plan.initial_water, plan.initial_food, game, level)
    except ValueError as exc:
        return PlanResult(plan, False, -inf, None, None, (), str(exc))
    timelines = _all_opponent_timelines(opponents, level, game.deadline)
    records: list[DailyRecord] = []
    for day, day_weather in enumerate(weather, start=1):
        if state.arrived:
            break
        if day > len(plan.actions):
            return PlanResult(
                plan, False, -inf, None, state, tuple(records), f"第{day}天缺少锁定动作"
            )
        action = plan.actions[day - 1]
        if action not in legal_actions(state, day_weather, level):
            return PlanResult(
                plan, False, -inf, None, state, tuple(records), f"第{day}天非法行动"
            )
        edge_h, mine_h = _externality(day - 1, state.node, action, timelines)
        water_used, food_used, income, multiplier = _action_effect(
            state.node, action, day_weather, edge_h, mine_h, game
        )
        water = state.water - water_used
        food = state.food - food_used
        if water < 0 or food < 0:
            return PlanResult(
                plan,
                False,
                -inf,
                None,
                state,
                tuple(records),
                f"第{day}天行动所需资源不足",
            )
        destination = int(action.destination) if action.kind == "行走" else state.node
        arrived = destination == level.goal
        if not arrived and (water < 1 or food < 1):
            return PlanResult(
                plan,
                False,
                -inf,
                None,
                state,
                tuple(records),
                f"第{day}天未到终点时资源必须保持为正",
            )
        previous_node = state.node
        state = PlayerState(destination, water, food, state.cash + income, arrived)
        records.append(
            DailyRecord(
                day=day,
                weather=day_weather,
                from_node=previous_node,
                to_node=destination,
                action=action.kind,
                multiplier=multiplier,
                water=water,
                food=food,
                cash=state.cash,
                edge_companions=edge_h,
                mine_companions=mine_h,
            )
        )
        if arrived:
            return PlanResult(
                plan,
                True,
                terminal_wealth(state, game),
                day,
                state,
                tuple(records),
            )
    return PlanResult(
        plan,
        False,
        -inf,
        None,
        state,
        tuple(records),
        "截止日前未到达终点",
    )


print("单玩家DP求解器加载完成")
print()

# game_open_loop - 双玩家开环Nash均衡

print()
print("game_open_loop - 双玩家开环Nash均衡求解")
print()


@dataclass(frozen=True)
class EquilibriumResult:
    """均衡结果"""
    kind: str
    profile: tuple[Plan, ...]
    player_results: tuple[PlanResult, ...]
    exploitability: float
    iterations: int
    converged: bool
    cycle_detected: bool
    generated_strategies: tuple[tuple[Plan, ...], ...] = ()
    mixed_row_probabilities: tuple[float, ...] | None = None
    mixed_column_probabilities: tuple[float, ...] | None = None


@dataclass(frozen=True)
class MixedEquilibriumResult:
    """混合均衡结果"""
    row_probabilities: tuple[float, ...]
    column_probabilities: tuple[float, ...]
    row_value: float
    column_value: float
    restricted_epsilon: float


def _opponents(profile: Sequence[Plan], player: int) -> tuple[Plan, ...]:
    """获取指定玩家的所有对手策略"""
    return tuple(plan for index, plan in enumerate(profile) if index != player)


def _evaluate_profile(
    profile: Sequence[Plan],
    game: GameConfig,
    level: LevelConfig,
    weather: tuple[str, ...],
) -> tuple[PlanResult, ...]:
    """评估策略配置"""
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
    """计算全局偏离收益"""
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
    enable_mixed_fallback: bool = True,
) -> EquilibriumResult:
    """求解纯策略Nash均衡"""
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

    # 若纯Nash不收敛，尝试混合均衡
    results = _evaluate_profile(profile, game, level, weather)
    gains = _global_gains(profile, results, game, level, weather)
    unresolved_epsilon = max(gains, default=float("inf"))

    if (
        enable_mixed_fallback
        and game.player_count == 2
        and generated[0]
        and generated[1]
    ):
        try:
            mixed = solve_restricted_mixed(
                tuple(generated[0]),
                tuple(generated[1]),
                game,
                level,
                weather,
            )
            return EquilibriumResult(
                kind="mixed",
                profile=tuple(profile),
                player_results=results,
                exploitability=mixed.restricted_epsilon,
                iterations=min(max_iterations, len(seen)),
                converged=True,
                cycle_detected=cycle,
                generated_strategies=tuple(tuple(items) for items in generated),
                mixed_row_probabilities=mixed.row_probabilities,
                mixed_column_probabilities=mixed.column_probabilities,
            )
        except (RuntimeError, ImportError):
            pass

    return EquilibriumResult(
        kind="unresolved",
        profile=tuple(profile),
        player_results=results,
        exploitability=unresolved_epsilon,
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
    """求解两人受限战略式博弈的混合均衡"""
    try:
        import nashpy as nash
    except ImportError as exc:
        raise RuntimeError("混合均衡兜底需要安装nashpy") from exc

    row_payoff = np.empty((len(row_strategies), len(column_strategies)))
    column_payoff = np.empty_like(row_payoff)
    for r, row in enumerate(row_strategies):
        for c, column in enumerate(column_strategies):
            row_payoff[r, c] = evaluate_plan(row, (column,), game, level, weather).terminal_wealth
            column_payoff[r, c] = evaluate_plan(column, (row,), game, level, weather).terminal_wealth
    candidates = list(nash.Game(row_payoff, column_payoff).support_enumeration())
    if not candidates:
        raise RuntimeError("受限博弈未找到混合均衡")
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


print("双玩家开环Nash均衡求解器加载完成")
print()

# validator - 验证器

print()
print("validator - 验证器")
print()


@dataclass(frozen=True)
class PlayerDeviation:
    """玩家偏离"""
    player: int
    current_wealth: float
    best_response_wealth: float
    gain: float


@dataclass(frozen=True)
class ExploitabilityReport:
    """可exploitability报告"""
    epsilon: float
    players: tuple[PlayerDeviation, ...]


@dataclass(frozen=True)
class AuditReport:
    """审计报告"""
    check_count: int
    violation_count: int
    max_abs_residual: float
    messages: tuple[str, ...]


def exploitability(
    profile: Sequence[Plan],
    game: GameConfig,
    level: LevelConfig,
    weather: tuple[str, ...],
) -> ExploitabilityReport:
    """计算均衡的exploitability"""
    rows: list[PlayerDeviation] = []
    for player in range(game.player_count):
        opponents = tuple(plan for index, plan in enumerate(profile) if index != player)
        current = evaluate_plan(profile[player], opponents, game, level, weather)
        response = best_response(opponents, game, level, weather)
        gain = max(0.0, response.terminal_wealth - current.terminal_wealth)
        rows.append(
            PlayerDeviation(
                player=player + 1,
                current_wealth=current.terminal_wealth,
                best_response_wealth=response.terminal_wealth,
                gain=gain,
            )
        )
    return ExploitabilityReport(max((row.gain for row in rows), default=0.0), tuple(rows))


def _opponent_events(
    opponents: Sequence[Plan],
    level: LevelConfig,
    days: int,
) -> tuple[tuple[tuple[str, int, int] | None, ...], ...]:
    """构建对手事件序列"""
    all_rows = []
    for plan in opponents:
        node = level.start
        arrived = False
        rows: list[tuple[str, int, int] | None] = []
        for day in range(days):
            if arrived or day >= len(plan.actions):
                rows.append(None)
                continue
            action = plan.actions[day]
            destination = int(action.destination) if action.kind == "行走" else node
            rows.append((action.kind, node, destination))
            node = destination
            arrived = node == level.goal
        all_rows.append(tuple(rows))
    return tuple(all_rows)


def audit_plan_result(
    result: PlanResult,
    opponents: Sequence[Plan],
    game: GameConfig,
    level: LevelConfig,
    weather: tuple[str, ...],
) -> AuditReport:
    """审计策略结果"""
    messages: list[str] = []
    residuals: list[float] = []
    water = result.plan.initial_water
    food = result.plan.initial_food
    cash = float(game.initial_cash - game.water_price * water - game.food_price * food)
    node = level.start
    timelines = _opponent_events(opponents, level, game.deadline)

    for index, record in enumerate(result.records):
        action = result.plan.actions[index]
        edge_h = 0
        mine_h = 0
        for timeline in timelines:
            event = timeline[index]
            if event is None:
                continue
            kind, from_node, to_node = event
            if action.kind == "行走" and kind == "行走" and from_node == node and to_node == action.destination:
                edge_h += 1
            if action.kind == "挖矿" and kind == "挖矿" and from_node == node:
                mine_h += 1
        if action.kind == "行走":
            multiplier = 2 * (edge_h + 1)
            if weather[index] == "沙暴" or action.destination not in level.neighbors[node]:
                messages.append(f"第{index + 1}天移动非法")
            destination = int(action.destination)
        elif action.kind == "挖矿":
            multiplier = 3
            destination = node
            if node not in level.mines:
                messages.append(f"第{index + 1}天不在矿山挖矿")
        else:
            multiplier = 1
            destination = node
        base_water, base_food = game.base_consumption[weather[index]]
        water -= multiplier * base_water
        food -= multiplier * base_food
        if action.kind == "挖矿":
            cash += game.mine_income / (mine_h + 1)
        residuals.extend(
            (
                record.water - water,
                record.food - food,
                record.cash - cash,
                record.to_node - destination,
                record.multiplier - multiplier,
                record.edge_companions - edge_h,
                record.mine_companions - mine_h,
            )
        )
        if water < 0 or food < 0 or cash < 0:
            messages.append(f"第{index + 1}天资源或资金为负")
        if destination != level.goal and (water < 1 or food < 1):
            messages.append(f"第{index + 1}天未到终点时资源耗尽")
        node = destination

    nonzero = sum(value != 0 for value in residuals)
    return AuditReport(
        check_count=len(residuals),
        violation_count=nonzero + len(messages),
        max_abs_residual=max((abs(value) for value in residuals), default=0.0),
        messages=tuple(messages),
    )


print("验证器加载完成")
print()

# sensitivity - 灵敏性分析

print()
print("sensitivity - 灵敏性分析")
print()


def _strategy_signature(result) -> str:
    """策略签名"""
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
    """求解单行灵敏度分析"""
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
    """扫描参数灵敏度"""
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


print("灵敏性分析加载完成")
print()

# data_loader - 数据加载

print()
print("data_loader - 数据加载")
print()


@dataclass(frozen=True)
class GraphAudit:
    """图审计结果"""
    symmetric: bool
    connected: bool
    key_nodes_reachable: bool
    duplicate_edge_count: int


def load_level5() -> tuple[GameConfig, LevelConfig, tuple[str, ...]]:
    """加载第五关配置"""
    normalized = tuple(sorted((min(u, v), max(u, v)) for u, v in LEVEL5_EDGES))
    level = make_level(
        name="第五关",
        node_count=13,
        edges=normalized,
        start=1,
        goal=13,
        villages=frozenset(),
        mines=frozenset({9}),
    )
    audit = audit_graph(level)
    if not (audit.symmetric and audit.connected and audit.key_nodes_reachable):
        raise ValueError(f"第五关地图审计失败：{audit}")
    if audit.duplicate_edge_count:
        raise ValueError("第五关邻接表存在重复边")
    return LEVEL5_GAME, level, LEVEL5_WEATHER


def audit_graph(level: LevelConfig) -> GraphAudit:
    """审计地图配置"""
    symmetric = all(
        u in level.neighbors[v] and v in level.neighbors[u]
        for u, v in level.edges
    )
    duplicate_edge_count = len(level.edges) - len(set(level.edges))
    reached = {level.start}
    queue = deque([level.start])
    while queue:
        node = queue.popleft()
        for neighbor in level.neighbors[node]:
            if neighbor not in reached:
                reached.add(neighbor)
                queue.append(neighbor)
    key_nodes = {level.start, level.goal, *level.villages, *level.mines}
    return GraphAudit(
        symmetric=symmetric,
        connected=len(reached) == level.node_count,
        key_nodes_reachable=key_nodes <= reached,
        duplicate_edge_count=duplicate_edge_count,
    )


print("数据加载器加载完成")
print()

# export - 结果导出

print()
print("export - 结果导出")
print()


def write_json(path: Path, payload: Mapping[str, object]) -> None:
    """写入JSON文件"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def write_csv(path: Path, rows: Iterable[Mapping[str, object]]) -> None:
    """写入CSV文件"""
    materialized = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not materialized:
        path.write_text("", encoding="utf-8-sig")
        return
    fieldnames = list(materialized[0].keys())
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(materialized)


print("结果导出器加载完成")
print()

# run - 主流程

print()
print("run - 主流程")
print()


def _daily_rows(equilibrium) -> list[dict[str, object]]:
    """生成逐日策略行"""
    rows: list[dict[str, object]] = []
    for player, result in enumerate(equilibrium.player_results, start=1):
        for record in result.records:
            rows.append(
                {
                    "玩家": player,
                    "日期": record.day,
                    "天气": record.weather,
                    "出发节点": record.from_node,
                    "到达节点": record.to_node,
                    "行动": record.action,
                    "消耗倍率": record.multiplier,
                    "同向同行对手数": record.edge_companions,
                    "同矿对手数": record.mine_companions,
                    "剩余水": record.water,
                    "剩余食物": record.food,
                    "剩余现金": record.cash,
                }
            )
    return rows


def main() -> dict[str, object]:
    """主函数"""
    print()
    print("整合所有模块运行")
    print()

    print("运行地图验证...")
    game, level, weather = load_level5()
    graph_audit = audit_graph(level)
    print(f"  地图验证完成：{level.name}，{level.node_count}节点，{len(level.edges)}条边")

    print()
    print("运行求解器...")
    print("  求解 第五关（双玩家博弈均衡）...")
    equilibrium = find_pure_ne(game, level, weather)
    deviation = exploitability(equilibrium.profile, game, level, weather)
    audits = tuple(
        audit_plan_result(
            equilibrium.player_results[player],
            (equilibrium.profile[1 - player],),
            game,
            level,
            weather,
        )
        for player in range(2)
    )
    if equilibrium.kind != "pure" or deviation.epsilon != 0:
        raise RuntimeError(f"第五关未取得经全局偏离检验的纯均衡：{equilibrium}")
    if any(audit.violation_count for audit in audits):
        raise RuntimeError(f"第五关独立规则审计失败：{audits}")
    print(f"  求解完成：均衡类型={equilibrium.kind}，迭代次数={equilibrium.iterations}，epsilon={deviation.epsilon}")
    print(f"  玩家1：财富={equilibrium.player_results[0].terminal_wealth:.0f}，第{equilibrium.player_results[0].arrival_day}天到达")
    print(f"  玩家2：财富={equilibrium.player_results[1].terminal_wealth:.0f}，第{equilibrium.player_results[1].arrival_day}天到达")

    summary = {
        "模型": "完全信息开环有限动态博弈 + Pareto-DP最优响应",
        "均衡类型": equilibrium.kind,
        "迭代次数": equilibrium.iterations,
        "epsilon": deviation.epsilon,
        "图审计": {
            "对称": graph_audit.symmetric,
            "连通": graph_audit.connected,
            "关键节点可达": graph_audit.key_nodes_reachable,
            "重复边数": graph_audit.duplicate_edge_count,
        },
        "玩家": [
            {
                "玩家": player + 1,
                "初始水": result.plan.initial_water,
                "初始食物": result.plan.initial_food,
                "到达日": result.arrival_day,
                "终端现金": result.final_state.cash,
                "剩余水": result.final_state.water,
                "剩余食物": result.final_state.food,
                "终端财富": result.terminal_wealth,
                "路线": [record.from_node for record in result.records]
                + [result.records[-1].to_node],
                "行动": [record.action for record in result.records],
            }
            for player, result in enumerate(equilibrium.player_results)
        ],
    }
    validation = {
        "全局单边偏离": [
            {
                "玩家": row.player,
                "当前财富": row.current_wealth,
                "最优响应财富": row.best_response_wealth,
                "盈利偏离": row.gain,
            }
            for row in deviation.players
        ],
        "epsilon": deviation.epsilon,
        "规则审计": [
            {
                "玩家": player + 1,
                "检查数": audit.check_count,
                "违规数": audit.violation_count,
                "最大绝对残差": audit.max_abs_residual,
                "消息": list(audit.messages),
            }
            for player, audit in enumerate(audits)
        ],
    }

    print()
    print("运行灵敏度分析...")
    print("  [01] 基准场景 玩家1路线")
    print("  [02] 基准场景 玩家2路线")
    print("  [03] 负载敏感性")
    print("  [04] 初始资金敏感性")
    print("  灵敏性分析完成")

    QUESTION_ROOT = Path(__file__).resolve().parent.parent
    OUTPUT_DIR = QUESTION_ROOT / "结果输出" / "第五关"
    VALIDATION_DIR = QUESTION_ROOT / "结果验证" / "第五关"

    print()
    print("保存结果文件...")
    write_csv(OUTPUT_DIR / "第五关玩家逐日策略.csv", _daily_rows(equilibrium))
    write_json(OUTPUT_DIR / "第五关均衡摘要.json", summary)
    write_json(VALIDATION_DIR / "第五关模型检验.json", validation)
    write_csv(
        VALIDATION_DIR / "第五关灵敏度分析.csv",
        scan_sensitivity(game, level, weather),
    )
    print("  结果文件已保存")

    print()
    print("【最终结果】")
    print()
    print("第五关（双玩家博弈均衡）：")
    print(f"  模型：完全信息开环有限动态博弈 + Pareto-DP最优响应")
    print(f"  均衡类型：{equilibrium.kind}")
    print(f"  迭代次数：{equilibrium.iterations}")
    print(f"  Epsilon：{deviation.epsilon}")
    print(f"  玩家1：财富={equilibrium.player_results[0].terminal_wealth:.0f}，第{equilibrium.player_results[0].arrival_day}天到达")
    print(f"  玩家2：财富={equilibrium.player_results[1].terminal_wealth:.0f}，第{equilibrium.player_results[1].arrival_day}天到达")

    print()
    print("求解完成")
    print()
    print(f"输出目录：{OUTPUT_DIR}")
    print("包含文件：")
    for f in sorted(OUTPUT_DIR.iterdir()):
        print(f"  - {f.name}")
    print()

    print("第五关求解完成")
    print(f"均衡类型={equilibrium.kind}，epsilon={deviation.epsilon}")


if __name__ == "__main__":
    main()
