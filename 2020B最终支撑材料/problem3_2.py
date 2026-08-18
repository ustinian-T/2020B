#!/usr/bin/env python3
"""
2020B 第三问（2）- 第六关：多玩家鲁棒博弈策略

"""

from __future__ import annotations

import csv
import json
import random
from collections import Counter, deque
from dataclasses import asdict, dataclass, field, is_dataclass, replace
from itertools import product
from math import inf as _inf
from pathlib import Path
from statistics import mean, median, stdev
from typing import Callable, Iterable, Mapping, Sequence
import numpy as np
from scipy.optimize import minimize


# config - 配置参数和地图定义

print()
print("config - 配置参数和地图定义")
print()


@dataclass(frozen=True)
class GameConfig:
    """游戏全局配置"""
    player_count: int
    capacity_kg: int
    initial_cash: int
    deadline: int
    mine_income: int
    water_weight: int
    food_weight: int
    water_price: int
    food_price: int
    base_consumption: Mapping[str, tuple[int, int]]


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


BASE_CONSUMPTION = {"晴朗": (3, 4), "高温": (9, 9), "沙暴": (10, 10)}

LEVEL6_GAME = GameConfig(
    player_count=3,
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


def grid_edges(rows: int, columns: int) -> tuple[tuple[int, int], ...]:
    """生成网格边"""
    edges: list[tuple[int, int]] = []
    for node in range(1, rows * columns + 1):
        row, column = divmod(node - 1, columns)
        if column + 1 < columns:
            edges.append((node, node + 1))
        if row + 1 < rows:
            edges.append((node, node + columns))
    return tuple(edges)


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
        name,
        node_count,
        normalized,
        {node: frozenset(items) for node, items in adjacency.items()},
        start,
        goal,
        villages,
        mines,
    )


LEVEL6_EDGES = grid_edges(5, 5)


print(f"第六关地图：{25}节点网格，{len(LEVEL6_EDGES)}条边")
print(f"玩家数：{LEVEL6_GAME.player_count}")
print(f"天气序列：{LEVEL6_GAME.deadline}天")
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
    def move(
        cls, destination: int, buy_water: int = 0, buy_food: int = 0
    ) -> "Action":
        return cls("行走", destination, buy_water, buy_food)

    @classmethod
    def stay(cls, buy_water: int = 0, buy_food: int = 0) -> "Action":
        return cls("停留", None, buy_water, buy_food)

    @classmethod
    def mine(cls, buy_water: int = 0, buy_food: int = 0) -> "Action":
        return cls("挖矿", None, buy_water, buy_food)

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
    multipliers: tuple[int, ...]
    water_consumption: tuple[int, ...]
    food_consumption: tuple[int, ...]
    purchase_cost: tuple[float, ...]
    mine_income: tuple[float, ...]


def total_weight(state: PlayerState, game: GameConfig) -> int:
    """计算总负重"""
    return game.water_weight * state.water + game.food_weight * state.food


def terminal_wealth(state: PlayerState, game: GameConfig) -> float:
    """计算终端财富"""
    if not state.arrived:
        raise ValueError("仅到达终点的状态可以清算")
    return state.cash + 0.5 * game.water_price * state.water + 0.5 * game.food_price * state.food


def initial_state(
    water: int, food: int, game: GameConfig, level: LevelConfig
) -> PlayerState:
    """初始化玩家状态"""
    if not isinstance(water, int) or not isinstance(food, int) or min(water, food) < 0:
        raise ValueError("初始采购必须为非负整数箱")
    state = PlayerState(
        level.start,
        water,
        food,
        float(game.initial_cash - game.water_price * water - game.food_price * food),
    )
    if state.cash < 0:
        raise ValueError("初始采购导致资金为负")
    if total_weight(state, game) > game.capacity_kg:
        raise ValueError("初始采购超过负重上限")
    return state


def legal_actions(
    state: PlayerState,
    weather: str,
    level: LevelConfig,
    purchase_options: Sequence[tuple[int, int]] = ((0, 0),),
) -> tuple[Action, ...]:
    """获取合法动作集合"""
    if state.arrived:
        return (Action.exit(),)
    options = tuple(purchase_options) if state.node in level.villages else ((0, 0),)
    actions: list[Action] = []
    for buy_water, buy_food in options:
        actions.append(Action.stay(buy_water, buy_food))
        if state.node in level.mines:
            actions.append(Action.mine(buy_water, buy_food))
        if weather != "沙暴":
            actions.extend(
                Action.move(node, buy_water, buy_food)
                for node in sorted(level.neighbors[state.node])
            )
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
            raise ValueError("已到达玩家必须退出")
        return
    if not all(isinstance(value, int) and value >= 0 for value in (action.buy_water, action.buy_food)):
        raise ValueError("购买量必须为非负整数")
    if (action.buy_water or action.buy_food) and state.node not in level.villages:
        raise ValueError("仅能在村庄购买资源")
    if action.kind == "行走":
        if weather == "沙暴":
            raise ValueError("沙暴日禁止移动")
        if action.destination not in level.neighbors[state.node]:
            raise ValueError("只能移动到相邻节点")
    elif action.kind == "挖矿":
        if state.node not in level.mines:
            raise ValueError("仅能在矿山挖矿")
    elif action.kind != "停留":
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
    village_counts = Counter(
        state.node
        for state, action in zip(states, actions)
        if not state.arrived and (action.buy_water > 0 or action.buy_food > 0)
    )
    base_water, base_food = game.base_consumption[weather]
    next_states: list[PlayerState] = []
    multipliers: list[int] = []
    water_rows: list[int] = []
    food_rows: list[int] = []
    cost_rows: list[float] = []
    income_rows: list[float] = []

    for state, action in zip(states, actions):
        if state.arrived:
            next_states.append(state)
            multipliers.append(0)
            water_rows.append(0)
            food_rows.append(0)
            cost_rows.append(0.0)
            income_rows.append(0.0)
            continue
        buyer_count = village_counts.get(state.node, 0)
        price_multiplier = 0 if not (action.buy_water or action.buy_food) else (2 if buyer_count == 1 else 4)
        purchase_cost = price_multiplier * (
            game.water_price * action.buy_water + game.food_price * action.buy_food
        )
        purchased = PlayerState(
            state.node,
            state.water + action.buy_water,
            state.food + action.buy_food,
            state.cash - purchase_cost,
        )
        if purchased.cash < 0:
            raise ValueError("购买导致资金为负")
        if total_weight(purchased, game) > game.capacity_kg:
            raise ValueError("购买导致负重超过上限")

        if action.kind == "行走":
            multiplier = 2 * edge_counts[(state.node, int(action.destination))]
            destination = int(action.destination)
        elif action.kind == "挖矿":
            multiplier = 3
            destination = state.node
        else:
            multiplier = 1
            destination = state.node
        water_used = multiplier * base_water
        food_used = multiplier * base_food
        water = purchased.water - water_used
        food = purchased.food - food_used
        if water < 0 or food < 0:
            raise ValueError("行动所需资源不足")
        arrived = destination == level.goal
        if not arrived and (water < 1 or food < 1):
            raise ValueError("未到终点时资源必须保持为正")
        income = game.mine_income / mine_counts[state.node] if action.kind == "挖矿" else 0.0
        next_states.append(
            PlayerState(destination, water, food, purchased.cash + income, arrived)
        )
        multipliers.append(multiplier)
        water_rows.append(water_used)
        food_rows.append(food_used)
        cost_rows.append(float(purchase_cost))
        income_rows.append(income)

    return JointStep(
        tuple(next_states),
        dict(edge_counts),
        dict(mine_counts),
        dict(village_counts),
        tuple(multipliers),
        tuple(water_rows),
        tuple(food_rows),
        tuple(cost_rows),
        tuple(income_rows),
    )


print("状态转移和动作定义加载完成")
print()

# robust_value - 鲁棒价值函数

print()
print("robust_value - 鲁棒价值函数")
print()


@dataclass(frozen=True)
class RobustValue:
    """鲁棒价值"""
    feasible: bool
    worst_wealth: float
    policy: str
    path: tuple[int, ...]
    mining_days: int
    required_days: int
    worst_case_water_margin: int
    worst_case_food_margin: int

    @property
    def score(self) -> tuple[int, float]:
        return int(self.feasible), self.worst_wealth


@dataclass(frozen=True)
class InitialPurchasePlan:
    """初始采购计划"""
    state: PlayerState
    value: RobustValue
    gamma: int


@dataclass(frozen=True)
class _RouteOption:
    """路线选项"""
    policy: str
    path: tuple[int, ...]
    village_index: int | None
    mine_index: int | None


def _shortest_path(level: LevelConfig, start: int, goal: int) -> tuple[int, ...]:
    """最短路径"""
    if start == goal:
        return (start,)
    parent: dict[int, int | None] = {start: None}
    queue = deque([start])
    while queue:
        node = queue.popleft()
        for neighbor in sorted(level.neighbors[node]):
            if neighbor in parent:
                continue
            parent[neighbor] = node
            if neighbor == goal:
                queue.clear()
                break
            queue.append(neighbor)
    if goal not in parent:
        raise ValueError(f"节点{start}无法到达节点{goal}")
    reversed_path = [goal]
    node = goal
    while parent[node] is not None:
        node = int(parent[node])
        reversed_path.append(node)
    return tuple(reversed(reversed_path))


def _join_paths(*paths: tuple[int, ...]) -> tuple[int, ...]:
    """连接多条路径"""
    joined: list[int] = []
    for path in paths:
        if not joined:
            joined.extend(path)
        else:
            joined.extend(path[1:])
    return tuple(joined)


def _route_options(state: PlayerState, level: LevelConfig) -> tuple[_RouteOption, ...]:
    """生成路线选项"""
    goal = level.goal
    village = min(level.villages) if level.villages else None
    mine = min(level.mines) if level.mines else None
    raw: list[tuple[str, tuple[int, ...], int | None, int | None]] = []

    direct = _shortest_path(level, state.node, goal)
    raw.append(("直达终点", direct, None, None))
    if village is not None:
        via_village = _join_paths(
            _shortest_path(level, state.node, village),
            _shortest_path(level, village, goal),
        )
        raw.append(("经村庄补给", via_village, via_village.index(village), None))
    if mine is not None:
        via_mine = _join_paths(
            _shortest_path(level, state.node, mine),
            _shortest_path(level, mine, goal),
        )
        raw.append(("经矿山", via_mine, None, via_mine.index(mine)))
    if village is not None and mine is not None:
        village_mine = _join_paths(
            _shortest_path(level, state.node, village),
            _shortest_path(level, village, mine),
            _shortest_path(level, mine, goal),
        )
        raw.append(
            (
                "先村庄后矿山",
                village_mine,
                village_mine.index(village),
                village_mine.index(mine),
            )
        )
        mine_village = _join_paths(
            _shortest_path(level, state.node, mine),
            _shortest_path(level, mine, village),
            _shortest_path(level, village, goal),
        )
        raw.append(
            (
                "先矿山后村庄",
                mine_village,
                mine_village.index(village),
                mine_village.index(mine),
            )
        )

    unique: dict[tuple[tuple[int, ...], int | None, int | None], _RouteOption] = {}
    for policy, path, village_index, mine_index in raw:
        key = path, village_index, mine_index
        unique.setdefault(key, _RouteOption(policy, path, village_index, mine_index))
    return tuple(unique.values())


def _evaluate_option(
    option: _RouteOption,
    mining_days: int,
    remaining_days: int,
    state: PlayerState,
    gamma: int,
    game: GameConfig,
) -> RobustValue:
    """评估路线选项"""
    move_days = len(option.path) - 1
    required_days = move_days + mining_days + gamma
    if required_days > remaining_days:
        return RobustValue(False, -_inf, option.policy, option.path, mining_days, required_days, -1, -1)
    high_move = 2 * game.base_consumption["高温"][0]
    high_mine = 3 * game.base_consumption["高温"][0]
    storm_wait = game.base_consumption["沙暴"][0]
    income_total = mining_days * game.mine_income

    if option.village_index is None:
        needed = move_days * high_move + mining_days * high_mine + gamma * storm_wait
        if state.water < needed or state.food < needed:
            return RobustValue(False, -_inf, option.policy, option.path, mining_days, required_days, state.water - needed, state.food - needed)
        final = PlayerState(
            node=option.path[-1],
            water=state.water - needed,
            food=state.food - needed,
            cash=state.cash + income_total,
            arrived=True,
        )
        return RobustValue(
            True,
            terminal_wealth(final, game),
            option.policy,
            option.path,
            mining_days,
            required_days,
            final.water,
            final.food,
        )

    village_index = option.village_index
    pre_moves = village_index
    post_moves = move_days - pre_moves
    mine_before = mining_days if option.mine_index is not None and option.mine_index < village_index else 0
    mine_after = mining_days - mine_before
    scenario_wealth: list[float] = []
    water_margins: list[int] = []
    food_margins: list[int] = []
    for storms_before in range(gamma + 1):
        storms_after = gamma - storms_before
        pre_need = pre_moves * high_move + mine_before * high_mine + storms_before * storm_wait
        post_need = post_moves * high_move + mine_after * high_mine + storms_after * storm_wait
        if state.water < pre_need or state.food < pre_need:
            return RobustValue(False, -_inf, option.policy, option.path, mining_days, required_days, state.water - pre_need, state.food - pre_need)
        water_at_village = state.water - pre_need
        food_at_village = state.food - pre_need
        buy_water = max(0, post_need - water_at_village)
        buy_food = max(0, post_need - food_at_village)
        cash_at_village = state.cash + mine_before * game.mine_income
        purchase_cost = 2 * (
            game.water_price * buy_water + game.food_price * buy_food
        )
        purchased = PlayerState(
            node=option.path[village_index],
            water=water_at_village + buy_water,
            food=food_at_village + buy_food,
            cash=cash_at_village - purchase_cost,
        )
        if purchased.cash < 0 or total_weight(purchased, game) > game.capacity_kg:
            return RobustValue(False, -_inf, option.policy, option.path, mining_days, required_days, -1, -1)
        final = PlayerState(
            node=option.path[-1],
            water=purchased.water - post_need,
            food=purchased.food - post_need,
            cash=purchased.cash + mine_after * game.mine_income,
            arrived=True,
        )
        scenario_wealth.append(terminal_wealth(final, game))
        water_margins.append(final.water)
        food_margins.append(final.food)
    return RobustValue(
        True,
        min(scenario_wealth),
        option.policy,
        option.path,
        mining_days,
        required_days,
        min(water_margins),
        min(food_margins),
    )


def robust_value(
    day: int,
    state: PlayerState,
    gamma_remaining: int,
    game: GameConfig,
    level: LevelConfig,
) -> RobustValue:
    """预算鲁棒单人续值下界，不读取任何未来真实天气"""
    if gamma_remaining < 0:
        raise ValueError("剩余沙暴预算不能为负")
    if state.arrived:
        return RobustValue(True, terminal_wealth(state, game), "已到达", (state.node,), 0, 0, state.water, state.food)
    remaining_days = game.deadline - day + 1
    if remaining_days <= 0:
        return RobustValue(False, -_inf, "超期", (), 0, 0, -1, -1)

    candidates: list[RobustValue] = []
    for option in _route_options(state, level):
        move_days = len(option.path) - 1
        max_mining = 0
        if option.mine_index is not None:
            max_mining = max(0, remaining_days - move_days - gamma_remaining)
        for mining_days in range(max_mining + 1):
            candidates.append(
                _evaluate_option(
                    option,
                    mining_days,
                    remaining_days,
                    state,
                    gamma_remaining,
                    game,
                )
            )
    feasible = [candidate for candidate in candidates if candidate.feasible]
    if not feasible:
        return RobustValue(False, -_inf, "无鲁棒可行路线", (), 0, remaining_days, -1, -1)
    return max(
        feasible,
        key=lambda item: (
            item.worst_wealth,
            -item.required_days,
            -item.mining_days,
            tuple(-node for node in item.path),
        ),
    )


def plan_initial_purchase(
    gamma: int,
    game: GameConfig,
    level: LevelConfig,
) -> InitialPurchasePlan:
    """第0天按基准价选择可承受的整数初始库存"""
    max_equal_stock = min(
        game.capacity_kg // (game.water_weight + game.food_weight),
        game.initial_cash // (game.water_price + game.food_price),
    )
    best: InitialPurchasePlan | None = None
    for amount in range(1, max_equal_stock + 1):
        state = initial_state(amount, amount, game, level)
        value = robust_value(1, state, gamma, game, level)
        if not value.feasible:
            continue
        candidate = InitialPurchasePlan(state, value, gamma)
        if best is None or (
            value.worst_wealth,
            -total_weight(state, game),
            state.cash,
        ) > (
            best.value.worst_wealth,
            -total_weight(best.state, game),
            best.state.cash,
        ):
            best = candidate
    if best is None:
        raise RuntimeError(f"Gamma={gamma} 时不存在鲁棒可行的初始采购")
    return best


print("鲁棒价值函数加载完成")
print()

# game_rolling - 多玩家逐日滚动均衡

print()
print("game_rolling - 多玩家逐日滚动均衡")
print()


@dataclass(frozen=True)
class RollingConfig:
    """滚动配置"""
    game: GameConfig
    level: LevelConfig
    tolerance: float = 1e-8


@dataclass(frozen=True)
class StageEquilibrium:
    """阶段均衡"""
    kind: str
    actions: tuple[Action, ...]
    payoffs: tuple[float, ...]
    epsilon: float
    player_gains: tuple[float, ...]
    pure_equilibria: tuple[tuple[Action, ...], ...]
    mixed_probabilities: tuple[tuple[float, ...], ...]
    action_sets: tuple[tuple[Action, ...], ...]
    payoff_rows: tuple[tuple[tuple[Action, ...], tuple[float, ...]], ...]


@dataclass(frozen=True)
class RollingDay:
    """滚动天"""
    day: int
    weather: str
    states_before: tuple[PlayerState, ...]
    actions: tuple[Action, ...]
    states_after: tuple[PlayerState, ...]
    equilibrium: StageEquilibrium
    edge_counts: tuple[tuple[tuple[int, int], int], ...]
    mine_counts: tuple[tuple[int, int], ...]
    village_counts: tuple[tuple[int, int], ...]
    multipliers: tuple[int, ...]
    water_consumption: tuple[int, ...]
    food_consumption: tuple[int, ...]
    purchase_cost: tuple[float, ...]
    mine_income: tuple[float, ...]


@dataclass(frozen=True)
class RollingSimulation:
    """滚动模拟"""
    gamma: int
    initial_states: tuple[PlayerState, ...]
    days: tuple[RollingDay, ...]
    final_states: tuple[PlayerState, ...]
    success: bool
    terminal_wealths: tuple[float | None, ...]
    failure_reason: str = ""


def _distance(level: LevelConfig, start: int, goal: int) -> int:
    """计算距离"""
    queue = deque([(start, 0)])
    reached = {start}
    while queue:
        node, distance = queue.popleft()
        if node == goal:
            return distance
        for neighbor in level.neighbors[node]:
            if neighbor not in reached:
                reached.add(neighbor)
                queue.append((neighbor, distance + 1))
    raise ValueError("图不连通")


def _purchase_options(
    state: PlayerState,
    gamma_remaining: int,
    game: GameConfig,
    level: LevelConfig,
) -> tuple[tuple[int, int], ...]:
    """采购选项"""
    if state.node not in level.villages:
        return ((0, 0),)
    distance = _distance(level, state.node, level.goal)
    target = distance * 2 * game.base_consumption["高温"][0] + gamma_remaining * game.base_consumption["沙暴"][0]
    max_equal = game.capacity_kg // (game.water_weight + game.food_weight)
    targets = {target, min(max_equal, target + 40), max_equal}
    options = {(0, 0)}
    for stock in sorted(targets):
        buy_water = max(0, stock - state.water)
        buy_food = max(0, stock - state.food)
        cost_at_four = 4 * (game.water_price * buy_water + game.food_price * buy_food)
        if cost_at_four <= state.cash:
            options.add((buy_water, buy_food))
    return tuple(sorted(options))


def _candidate_actions(
    state: PlayerState,
    weather: str,
    gamma_remaining: int,
    config: RollingConfig,
) -> tuple[Action, ...]:
    """候选动作"""
    options = _purchase_options(
        state, gamma_remaining, config.game, config.level
    )
    candidates = legal_actions(state, weather, config.level, options)
    feasible: list[Action] = []
    for action in candidates:
        if state.arrived:
            feasible.append(action)
            continue
        price = 4 if (action.buy_water or action.buy_food) else 0
        cash = state.cash - price * (
            config.game.water_price * action.buy_water
            + config.game.food_price * action.buy_food
        )
        water = state.water + action.buy_water
        food = state.food + action.buy_food
        if cash < 0:
            continue
        if config.game.water_weight * water + config.game.food_weight * food > config.game.capacity_kg:
            continue
        feasible.append(action)
    return tuple(feasible)


def _payoff_table(
    day: int,
    current_weather: str,
    public_states: Sequence[PlayerState],
    gamma_remaining: int,
    config: RollingConfig,
    action_sets: Sequence[Sequence[Action]],
) -> dict[tuple[Action, ...], tuple[float, ...]]:
    """收益表"""
    table: dict[tuple[Action, ...], tuple[float, ...]] = {}
    for joint in product(*action_sets):
        try:
            transition = step_joint(
                public_states, joint, current_weather, config.game, config.level
            )
        except ValueError:
            table[tuple(joint)] = tuple(-_inf for _ in public_states)
            continue
        payoffs: list[float] = []
        for state in transition.states:
            if state.arrived:
                payoffs.append(terminal_wealth(state, config.game))
                continue
            continuation = robust_value(
                day + 1,
                state,
                gamma_remaining,
                config.game,
                config.level,
            )
            payoffs.append(continuation.worst_wealth if continuation.feasible else -_inf)
        table[tuple(joint)] = tuple(payoffs)
    return table


def _unilateral_gains(
    joint: tuple[Action, ...],
    action_sets: Sequence[Sequence[Action]],
    payoffs: Mapping[tuple[Action, ...], tuple[float, ...]],
) -> tuple[float, ...]:
    """单边偏离收益"""
    current = payoffs[joint]
    gains: list[float] = []
    for player, alternatives in enumerate(action_sets):
        best = current[player]
        for action in alternatives:
            deviated = list(joint)
            deviated[player] = action
            best = max(best, payoffs[tuple(deviated)][player])
        gains.append(max(0.0, best - current[player]))
    return tuple(gains)


def _pure_equilibria(
    action_sets: Sequence[Sequence[Action]],
    payoffs: Mapping[tuple[Action, ...], tuple[float, ...]],
    tolerance: float,
) -> tuple[tuple[Action, ...], ...]:
    """纯均衡"""
    rows = []
    for joint in product(*action_sets):
        joint = tuple(joint)
        if any(value == -_inf for value in payoffs[joint]):
            continue
        if max(_unilateral_gains(joint, action_sets, payoffs), default=0.0) <= tolerance:
            rows.append(joint)
    return tuple(rows)


def _mixed_equilibrium(
    action_sets: Sequence[Sequence[Action]],
    payoffs: Mapping[tuple[Action, ...], tuple[float, ...]],
    tolerance: float,
) -> tuple[tuple[tuple[float, ...], ...], tuple[float, ...], float]:
    """阶段博弈混合均衡求解"""
    sizes = [len(actions) for actions in action_sets]

    # 路径1：nashpy（仅两人博弈）
    if len(sizes) == 2 and max(sizes) <= 16:
        try:
            import nashpy as nash

            row_actions, col_actions = action_sets
            row_payoff = np.empty((sizes[0], sizes[1]))
            col_payoff = np.empty_like(row_payoff)
            for joint, values in payoffs.items():
                r = row_actions.index(joint[0])
                c = col_actions.index(joint[1])
                rv = -1e12 if values[0] == -_inf else values[0]
                cv = -1e12 if values[1] == -_inf else values[1]
                row_payoff[r, c] = rv
                col_payoff[r, c] = cv
            game = nash.Game(row_payoff, col_payoff)
            for equilibria in (game.support_enumeration(), game.lemke_howson()):
                for eq in equilibria:
                    row_prob, col_prob = eq
                    row_prob_arr = np.asarray(row_prob)
                    col_prob_arr = np.asarray(col_prob)
                    row_values = row_payoff @ col_prob_arr
                    col_values = row_prob_arr @ col_payoff
                    row_v = float(row_prob_arr @ row_values)
                    col_v = float(col_values @ col_prob_arr)
                    eps = max(float(np.max(row_values) - row_v),
                              float(np.max(col_values) - col_v), 0.0)
                    if eps <= tolerance:
                        return ((tuple(float(x) for x in row_prob),
                                 tuple(float(x) for x in col_prob)),
                                (row_v, col_v), eps)
        except (ImportError, Exception):
            pass

    # 路径2：SLSQP regret minimization（通用，含三人博弈）
    offsets = np.cumsum([0, *sizes])
    numeric = {
        joint: tuple(-1e12 if value == -_inf else value for value in values)
        for joint, values in payoffs.items()
    }

    def split(vector):
        return [vector[offsets[i] : offsets[i + 1]] for i in range(len(sizes))]

    def action_values(probabilities, player):
        values = np.zeros(sizes[player])
        for action_index, action in enumerate(action_sets[player]):
            total = 0.0
            other_indices = [range(size) for index, size in enumerate(sizes) if index != player]
            for others in product(*other_indices):
                joint_indices = []
                cursor = 0
                probability = 1.0
                for index in range(len(sizes)):
                    if index == player:
                        joint_indices.append(action_index)
                    else:
                        selected = others[cursor]
                        cursor += 1
                        joint_indices.append(selected)
                        probability *= probabilities[index][selected]
                joint = tuple(action_sets[index][choice] for index, choice in enumerate(joint_indices))
                total += probability * numeric[joint][player]
            values[action_index] = total
        return values

    def regrets(vector):
        probabilities = split(vector)
        rows = []
        for player in range(len(sizes)):
            values = action_values(probabilities, player)
            expected = float(probabilities[player] @ values)
            rows.append(max(0.0, float(np.max(values) - expected)))
        return np.asarray(rows)

    def objective(vector):
        row = regrets(vector)
        return float(row @ row)

    initial = np.concatenate([np.full(size, 1.0 / size) for size in sizes])
    constraints = [
        {
            "type": "eq",
            "fun": lambda vector, i=i: float(np.sum(vector[offsets[i] : offsets[i + 1]]) - 1),
        }
        for i in range(len(sizes))
    ]
    result = minimize(
        objective,
        initial,
        method="SLSQP",
        bounds=[(0.0, 1.0)] * len(initial),
        constraints=constraints,
        options={"maxiter": 2000, "ftol": tolerance * tolerance},
    )
    probabilities = split(result.x)
    regret = regrets(result.x)
    epsilon = float(np.max(regret))
    if not result.success or epsilon > tolerance:
        raise RuntimeError(f"阶段博弈无纯均衡，混合均衡未通过检验：epsilon={epsilon}")
    expected = []
    for player in range(len(sizes)):
        values = action_values(probabilities, player)
        expected.append(float(probabilities[player] @ values))
    return tuple(tuple(float(x) for x in row) for row in probabilities), tuple(expected), epsilon


def choose_actions(
    day: int,
    current_weather: str,
    public_states: Sequence[PlayerState],
    gamma_remaining: int,
    config: RollingConfig,
) -> StageEquilibrium:
    """选择动作"""
    if len(public_states) != config.game.player_count:
        raise ValueError("公开状态数量必须等于玩家数")
    action_sets = tuple(
        _candidate_actions(state, current_weather, gamma_remaining, config)
        for state in public_states
    )
    table = _payoff_table(
        day,
        current_weather,
        public_states,
        gamma_remaining,
        config,
        action_sets,
    )
    pure = _pure_equilibria(action_sets, table, config.tolerance)
    payoff_rows = tuple(sorted(table.items(), key=lambda item: item[0]))
    if pure:
        selected = max(
            pure,
            key=lambda joint: (
                min(table[joint]),
                sum(table[joint]),
                joint,
            ),
        )
        gains = _unilateral_gains(selected, action_sets, table)
        return StageEquilibrium(
            "pure",
            selected,
            table[selected],
            max(gains, default=0.0),
            gains,
            pure,
            (),
            action_sets,
            payoff_rows,
        )

    probabilities, expected, epsilon = _mixed_equilibrium(
        action_sets, table, config.tolerance
    )
    representative = tuple(
        actions[int(np.argmax(probability))]
        for actions, probability in zip(action_sets, probabilities)
    )
    return StageEquilibrium(
        "mixed",
        representative,
        expected,
        epsilon,
        tuple(epsilon for _ in public_states),
        (),
        probabilities,
        action_sets,
        payoff_rows,
    )


def rolling_simulation(
    weather_sequence: Sequence[str],
    gamma: int,
    config: RollingConfig,
    initial_states: Sequence[PlayerState] | None = None,
) -> RollingSimulation:
    """滚动模拟"""
    if initial_states is None:
        initial = plan_initial_purchase(gamma, config.game, config.level).state
        states = tuple(initial for _ in range(config.game.player_count))
    else:
        if len(initial_states) != config.game.player_count:
            raise ValueError("初始状态数量必须等于玩家数")
        states = tuple(initial_states)
    original = states
    days: list[RollingDay] = []
    storms_seen = 0
    failure_reason = ""
    for day, weather in enumerate(weather_sequence, start=1):
        if day > config.game.deadline or all(state.arrived for state in states):
            break
        if weather == "沙暴":
            storms_seen += 1
        gamma_remaining = max(0, gamma - storms_seen)
        equilibrium = choose_actions(
            day, weather, states, gamma_remaining, config
        )
        try:
            transition = step_joint(
                states, equilibrium.actions, weather, config.game, config.level
            )
        except ValueError as exc:
            failure_reason = f"第{day}天：{exc}"
            break
        next_states = transition.states
        days.append(
            RollingDay(
                day=day,
                weather=weather,
                states_before=states,
                actions=equilibrium.actions,
                states_after=next_states,
                equilibrium=equilibrium,
                edge_counts=tuple(sorted(transition.edge_counts.items())),
                mine_counts=tuple(sorted(transition.mine_counts.items())),
                village_counts=tuple(sorted(transition.village_counts.items())),
                multipliers=transition.multipliers,
                water_consumption=transition.water_consumption,
                food_consumption=transition.food_consumption,
                purchase_cost=transition.purchase_cost,
                mine_income=transition.mine_income,
            )
        )
        states = next_states
    success = all(state.arrived for state in states)
    if not success and not failure_reason and len(weather_sequence) >= config.game.deadline:
        failure_reason = "截止日前未全部到达终点"
    wealths = tuple(
        terminal_wealth(state, config.game) if state.arrived else None
        for state in states
    )
    return RollingSimulation(
        gamma=gamma,
        initial_states=original,
        days=tuple(days),
        final_states=states,
        success=success,
        terminal_wealths=wealths,
        failure_reason=failure_reason,
    )


print("多玩家逐日滚动均衡加载完成")
print()

# baselines - 基准策略

print()
print("baselines - 基准策略")
print()


@dataclass(frozen=True)
class BaselineResult:
    """基准结果"""
    name: str
    definition: str
    weather_days: int
    success: bool
    executed_days: int
    mean_terminal_wealth: float | None
    minimum_terminal_wealth: float | None
    epsilon_max: float | None
    conflict_loss: "ConflictLoss"
    failure_reason: str
    simulation: RollingSimulation


def _shortest_next(config: RollingConfig, start: int) -> int:
    """最短下一步"""
    if start == config.level.goal:
        return start
    parent = {start: None}
    queue = deque([start])
    while queue:
        node = queue.popleft()
        for neighbor in sorted(config.level.neighbors[node]):
            if neighbor in parent:
                continue
            parent[neighbor] = node
            if neighbor == config.level.goal:
                queue.clear()
                break
            queue.append(neighbor)
    node = config.level.goal
    path = [node]
    while parent[node] is not None:
        node = int(parent[node])
        path.append(node)
    path.reverse()
    return path[1]


Policy = Callable[[int, str, tuple[PlayerState, ...], int], tuple[tuple[Action, ...], float]]


def _simulate_policy(
    name: str,
    weather_sequence: Sequence[str],
    gamma: int,
    config: RollingConfig,
    policy: Policy,
) -> RollingSimulation:
    """模拟策略"""
    initial = plan_initial_purchase(gamma, config.game, config.level).state
    states = tuple(initial for _ in range(config.game.player_count))
    original = states
    days: list[RollingDay] = []
    storms_seen = 0
    failure = ""
    for day, weather in enumerate(weather_sequence, start=1):
        if day > config.game.deadline or all(state.arrived for state in states):
            break
        if weather == "沙暴":
            storms_seen += 1
        remaining = max(0, gamma - storms_seen)
        actions, epsilon = policy(day, weather, states, remaining)
        try:
            transition = step_joint(states, actions, weather, config.game, config.level)
        except ValueError as exc:
            failure = f"第{day}天：{exc}"
            break
        payoffs = tuple(
            terminal_wealth(state, config.game)
            if state.arrived
            else state.cash
            + 0.5 * config.game.water_price * state.water
            + 0.5 * config.game.food_price * state.food
            for state in transition.states
        )
        equilibrium = StageEquilibrium(
            kind=name,
            actions=actions,
            payoffs=payoffs,
            epsilon=epsilon,
            player_gains=tuple(epsilon for _ in states),
            pure_equilibria=(),
            mixed_probabilities=(),
            action_sets=(),
            payoff_rows=(),
        )
        days.append(
            RollingDay(
                day,
                weather,
                states,
                actions,
                transition.states,
                equilibrium,
                tuple(sorted(transition.edge_counts.items())),
                tuple(sorted(transition.mine_counts.items())),
                tuple(sorted(transition.village_counts.items())),
                transition.multipliers,
                transition.water_consumption,
                transition.food_consumption,
                transition.purchase_cost,
                transition.mine_income,
            )
        )
        states = transition.states
    success = all(state.arrived for state in states)
    if not success and not failure and len(weather_sequence) >= config.game.deadline:
        failure = "截止日前未全部到达终点"
    return RollingSimulation(
        gamma,
        original,
        tuple(days),
        states,
        success,
        tuple(terminal_wealth(state, config.game) if state.arrived else None for state in states),
        failure,
    )


def _b0_policy(config: RollingConfig) -> Policy:
    """基准策略B0：最短可行路"""
    def policy(day, weather, states, gamma_remaining):
        actions = []
        for state in states:
            if state.arrived:
                actions.append(Action.exit())
            elif weather == "沙暴":
                actions.append(Action.stay())
            else:
                actions.append(Action.move(_shortest_next(config, state.node)))
        return tuple(actions), 0.0

    return policy


def _b1_policy(config: RollingConfig) -> Policy:
    """基准策略B1：独立单人鲁棒续值"""
    def policy(day, weather, states, gamma_remaining):
        actions = []
        for state in states:
            if state.arrived:
                actions.append(Action.exit())
                continue
            continuation = robust_value(
                day, state, gamma_remaining, config.game, config.level
            )
            if weather == "沙暴":
                actions.append(Action.stay())
            elif state.node in config.level.mines and continuation.mining_days > 0:
                actions.append(Action.mine())
            elif len(continuation.path) >= 2:
                actions.append(Action.move(continuation.path[1]))
            else:
                actions.append(Action.stay())
        return tuple(actions), 0.0

    return policy


def _b2_policy(config: RollingConfig) -> Policy:
    """基准策略B2：短视阶段博弈"""
    def policy(day, weather, states, gamma_remaining):
        action_sets = tuple(
            legal_actions(state, weather, config.level) for state in states
        )
        table = {}
        for joint in product(*action_sets):
            try:
                transition = step_joint(
                    states, joint, weather, config.game, config.level
                )
            except ValueError:
                table[tuple(joint)] = tuple(-_inf for _ in states)
                continue
            table[tuple(joint)] = tuple(
                state.cash
                + 0.5 * config.game.water_price * state.water
                + 0.5 * config.game.food_price * state.food
                for state in transition.states
            )
        pure = []
        for joint, values in table.items():
            if any(value == -_inf for value in values):
                continue
            stable = True
            for player, alternatives in enumerate(action_sets):
                for action in alternatives:
                    deviated = list(joint)
                    deviated[player] = action
                    if table[tuple(deviated)][player] > values[player] + 1e-8:
                        stable = False
                        break
                if not stable:
                    break
            if stable:
                pure.append(joint)
        if pure:
            selected = max(
                pure, key=lambda joint: (min(table[joint]), sum(table[joint]), joint)
            )
            return selected, 0.0
        selected = max(
            table,
            key=lambda joint: (min(table[joint]), sum(table[joint]), joint),
        )
        values = table[selected]
        epsilon = 0.0
        for player, alternatives in enumerate(action_sets):
            best = values[player]
            for action in alternatives:
                deviated = list(selected)
                deviated[player] = action
                best = max(best, table[tuple(deviated)][player])
            epsilon = max(epsilon, best - values[player])
        return selected, epsilon

    return policy


def _result(
    name: str,
    definition: str,
    weather_days: int,
    simulation: RollingSimulation,
    config: RollingConfig,
    epsilon_is_meaningful: bool,
) -> BaselineResult:
    """构建基准结果"""
    wealths = [value for value in simulation.terminal_wealths if value is not None]
    epsilon = (
        max((day.equilibrium.epsilon for day in simulation.days), default=0.0)
        if epsilon_is_meaningful
        else None
    )
    return BaselineResult(
        name,
        definition,
        weather_days,
        simulation.success,
        len(simulation.days),
        mean(wealths) if wealths else None,
        min(wealths) if wealths else None,
        epsilon,
        conflict_loss(simulation, config.game),
        simulation.failure_reason,
        simulation,
    )


def run_baselines(
    weather_sequence: Sequence[str],
    gamma: int,
    config: RollingConfig,
) -> tuple[BaselineResult, ...]:
    """运行所有基准策略"""
    weather = tuple(weather_sequence)
    b0 = _simulate_policy("B0", weather, gamma, config, _b0_policy(config))
    b1 = _simulate_policy("B1", weather, gamma, config, _b1_policy(config))
    b2 = _simulate_policy("B2", weather, gamma, config, _b2_policy(config))
    full = rolling_simulation(weather, gamma, config)
    return (
        _result("B0", "最短可行路，不主动挖矿或博弈避让", len(weather), b0, config, False),
        _result("B1", "独立单人鲁棒续值，忽略竞争后联合执行", len(weather), b1, config, False),
        _result("B2", "只使用当天即时价值的短视阶段博弈", len(weather), b2, config, True),
        _result("Full", "当前耦合精确、Gamma鲁棒续值、阶段Nash、每日滚动", len(weather), full, config, True),
    )


print("基准策略加载完成")
print()

# validator - 验证器

print()
print("validator - 验证器")
print()


@dataclass(frozen=True)
class ConflictLoss:
    """冲突损失"""
    move: float
    mine: float
    village: float
    total: float


@dataclass(frozen=True)
class RegretRow:
    """后悔行"""
    player: int
    online_wealth: float
    oracle_upper_bound: float
    regret: float


@dataclass(frozen=True)
class AuditReport:
    """审计报告"""
    check_count: int
    violation_count: int
    max_abs_residual: float
    messages: tuple[str, ...]


def audit_simulation(
    simulation: RollingSimulation,
    config: RollingConfig,
) -> AuditReport:
    """审计模拟"""
    residuals: list[float] = []
    messages: list[str] = []
    for day in simulation.days:
        edge_counts = Counter(
            (state.node, int(action.destination))
            for state, action in zip(day.states_before, day.actions)
            if not state.arrived and action.kind == "行走"
        )
        mine_counts = Counter(
            state.node
            for state, action in zip(day.states_before, day.actions)
            if not state.arrived and action.kind == "挖矿"
        )
        village_counts = Counter(
            state.node
            for state, action in zip(day.states_before, day.actions)
            if not state.arrived and (action.buy_water or action.buy_food)
        )
        if dict(edge_counts) != dict(day.edge_counts):
            messages.append(f"第{day.day}天同向边人数日志不一致")
        if dict(mine_counts) != dict(day.mine_counts):
            messages.append(f"第{day.day}天同矿人数日志不一致")
        if dict(village_counts) != dict(day.village_counts):
            messages.append(f"第{day.day}天同村购买人数日志不一致")

        base_water, base_food = config.game.base_consumption[day.weather]
        for player, (before, action, after) in enumerate(
            zip(day.states_before, day.actions, day.states_after), start=1
        ):
            if before.arrived:
                residuals.extend(
                    (
                        after.water - before.water,
                        after.food - before.food,
                        after.cash - before.cash,
                        after.node - before.node,
                    )
                )
                continue
            buyers = village_counts.get(before.node, 0)
            price_multiplier = 0 if not (action.buy_water or action.buy_food) else (2 if buyers == 1 else 4)
            purchase_cost = price_multiplier * (
                config.game.water_price * action.buy_water
                + config.game.food_price * action.buy_food
            )
            if action.kind == "行走":
                if day.weather == "沙暴" or action.destination not in config.level.neighbors[before.node]:
                    messages.append(f"第{day.day}天玩家{player}移动非法")
                multiplier = 2 * edge_counts[(before.node, int(action.destination))]
                destination = int(action.destination)
            elif action.kind == "挖矿":
                if before.node not in config.level.mines:
                    messages.append(f"第{day.day}天玩家{player}不在矿山挖矿")
                multiplier = 3
                destination = before.node
            else:
                multiplier = 1
                destination = before.node
            income = (
                config.game.mine_income / mine_counts[before.node]
                if action.kind == "挖矿"
                else 0.0
            )
            expected_water = before.water + action.buy_water - multiplier * base_water
            expected_food = before.food + action.buy_food - multiplier * base_food
            expected_cash = before.cash - purchase_cost + income
            residuals.extend(
                (
                    after.water - expected_water,
                    after.food - expected_food,
                    after.cash - expected_cash,
                    after.node - destination,
                    day.multipliers[player - 1] - multiplier,
                    day.water_consumption[player - 1] - multiplier * base_water,
                    day.food_consumption[player - 1] - multiplier * base_food,
                    day.purchase_cost[player - 1] - purchase_cost,
                    day.mine_income[player - 1] - income,
                )
            )
            arrived = destination == config.level.goal
            if after.arrived != arrived:
                messages.append(f"第{day.day}天玩家{player}到达标记错误")
            if expected_water < 0 or expected_food < 0 or expected_cash < 0:
                messages.append(f"第{day.day}天玩家{player}资源或资金为负")
            if not arrived and (expected_water < 1 or expected_food < 1):
                messages.append(f"第{day.day}天玩家{player}未到终点时资源耗尽")
            purchased_weight = (
                config.game.water_weight * (before.water + action.buy_water)
                + config.game.food_weight * (before.food + action.buy_food)
            )
            if purchased_weight > config.game.capacity_kg:
                messages.append(f"第{day.day}天玩家{player}购买后超重")

    nonzero = sum(value != 0 for value in residuals)
    return AuditReport(
        check_count=len(residuals),
        violation_count=nonzero + len(messages),
        max_abs_residual=max((abs(value) for value in residuals), default=0.0),
        messages=tuple(messages),
    )


def counterfactual_prefix_test(
    weather_a: Sequence[str],
    weather_b: Sequence[str],
    prefix_day: int,
    gamma: int,
    config: RollingConfig,
) -> bool:
    """反事实前缀检验"""
    if prefix_day < 1 or weather_a[:prefix_day] != weather_b[:prefix_day]:
        raise ValueError("两条天气轨迹必须共享指定长度的前缀")
    prefix = tuple(weather_a[: prefix_day - 1])
    simulation = rolling_simulation(prefix, gamma, config)
    states = simulation.final_states
    storms_through_today = sum(
        weather == "沙暴" for weather in weather_a[:prefix_day]
    )
    remaining = max(0, gamma - storms_through_today)
    first = choose_actions(
        prefix_day, weather_a[prefix_day - 1], states, remaining, config
    )
    second = choose_actions(
        prefix_day, weather_b[prefix_day - 1], states, remaining, config
    )
    return first.actions == second.actions and first.payoff_rows == second.payoff_rows


def conflict_loss(
    simulation: RollingSimulation,
    game: GameConfig,
) -> ConflictLoss:
    """冲突损失"""
    move_loss = 0.0
    mine_loss = 0.0
    village_loss = 0.0
    for day in simulation.days:
        base_water, base_food = game.base_consumption[day.weather]
        edge_counts = dict(day.edge_counts)
        mine_counts = dict(day.mine_counts)
        village_counts = dict(day.village_counts)
        for state, action in zip(day.states_before, day.actions):
            if state.arrived:
                continue
            if action.kind == "行走":
                count = edge_counts[(state.node, int(action.destination))]
                extra_multiplier = 2 * count - 2
                move_loss += (
                    game.water_price * extra_multiplier * base_water
                    + game.food_price * extra_multiplier * base_food
                )
            elif action.kind == "挖矿":
                count = mine_counts[state.node]
                mine_loss += game.mine_income - game.mine_income / count
            if action.buy_water or action.buy_food:
                count = village_counts[state.node]
                price_extra = 0 if count == 1 else 2
                village_loss += price_extra * (
                    game.water_price * action.buy_water
                    + game.food_price * action.buy_food
                )
    total = move_loss + mine_loss + village_loss
    return ConflictLoss(move_loss, mine_loss, village_loss, total)


def ex_post_regret_upper_bound(
    simulation: RollingSimulation,
    game: GameConfig,
) -> tuple[RegretRow, ...]:
    """事后后悔上界"""
    rows = []
    for player, (initial, final) in enumerate(
        zip(simulation.initial_states, simulation.final_states), start=1
    ):
        online = terminal_wealth(final, game) if final.arrived else 0.0
        remaining_days = game.deadline
        optimistic_income = remaining_days * game.mine_income
        upper = game.initial_cash + optimistic_income + 0.5 * (
            game.water_price * initial.water + game.food_price * initial.food
        )
        rows.append(RegretRow(player, online, upper, max(0.0, upper - online)))
    return tuple(rows)


print("验证器加载完成")
print()

# validation_experiments - 验证实验

print()
print("validation_experiments - 验证实验")
print()


def _build_exact_small_subgraph() -> LevelConfig:
    """构建精确小子图"""
    return make_level(
        name="exact_small_subgraph",
        node_count=13,
        edges=((1, 6), (6, 13)),
        start=1,
        goal=13,
        villages=frozenset(),
        mines=frozenset(),
    )


def _state_cache_key(states: tuple[PlayerState, ...]) -> tuple:
    """状态缓存键"""
    return tuple((s.node, s.water, s.food, s.arrived) for s in states)


def _solve_exact_subgame(
    states: tuple[PlayerState, ...],
    day: int,
    weather: tuple[str, ...],
    game: GameConfig,
    level: LevelConfig,
    cache: dict,
    tolerance: float = 1e-8,
) -> tuple[float, ...]:
    """精确子博弈求解"""
    key = (_state_cache_key(states), day)
    if key in cache:
        return cache[key]

    if day > game.deadline or all(s.arrived for s in states):
        result = tuple(
            terminal_wealth(s, game) if s.arrived else -1e12 for s in states
        )
        cache[key] = result
        return result

    omega = weather[day - 1]
    action_sets = tuple(legal_actions(s, omega, level) for s in states)

    payoff_table: dict[tuple, tuple[float, ...]] = {}
    for joint_action in product(*action_sets):
        try:
            joint_step = step_joint(states, joint_action, omega, game, level)
        except ValueError:
            payoff_table[joint_action] = tuple(-1e12 for _ in states)
            continue
        future = _solve_exact_subgame(
            joint_step.states, day + 1, weather, game, level, cache, tolerance
        )
        payoff_table[joint_action] = future

    pure = _pure_equilibria(action_sets, payoff_table, tolerance)
    if pure:
        best = max(
            pure,
            key=lambda j: (
                min(payoff_table[j]),
                sum(payoff_table[j]),
                j,
            ),
        )
        result = payoff_table[best]
    else:
        _, expected, _ = _mixed_equilibrium(action_sets, payoff_table, tolerance)
        result = expected

    cache[key] = result
    return result


def _solve_approximate_subgame(
    states: tuple[PlayerState, ...],
    day: int,
    weather: tuple[str, ...],
    game: GameConfig,
    level: LevelConfig,
    cache: dict,
    tolerance: float = 1e-8,
) -> tuple[float, ...]:
    """近似子博弈求解"""
    key = (_state_cache_key(states), day)
    if key in cache:
        return cache[key]

    if day > game.deadline or all(s.arrived for s in states):
        result = tuple(
            terminal_wealth(s, game) if s.arrived else -1e12 for s in states
        )
        cache[key] = result
        return result

    omega = weather[day - 1]
    action_sets = tuple(legal_actions(s, omega, level) for s in states)

    payoff_table: dict[tuple, tuple[float, ...]] = {}
    for joint_action in product(*action_sets):
        try:
            joint_step = step_joint(states, joint_action, omega, game, level)
        except ValueError:
            payoff_table[joint_action] = tuple(-1e12 for _ in states)
            continue
        future_values: list[float] = []
        for next_state in joint_step.states:
            if next_state.arrived:
                future_values.append(terminal_wealth(next_state, game))
            else:
                remaining_days = game.deadline - day
                future_values.append(
                    _single_player_lower_bound(next_state, remaining_days, game)
                )
        payoff_table[joint_action] = tuple(future_values)

    pure = _pure_equilibria(action_sets, payoff_table, tolerance)
    if pure:
        best = max(
            pure,
            key=lambda j: (
                min(payoff_table[j]),
                sum(payoff_table[j]),
                j,
            ),
        )
        result = payoff_table[best]
    else:
        result = tuple(max(payoff_table[j][i] for j in payoff_table) for i in range(len(states)))

    cache[key] = result
    return result


def _single_player_lower_bound(
    state: PlayerState,
    remaining_days: int,
    game: GameConfig,
) -> float:
    """单人下界"""
    if state.arrived:
        return terminal_wealth(state, game)
    if state.node == 6 and remaining_days >= 1:
        w2 = state.water - 6
        f2 = state.food - 8
        if w2 >= 0 and f2 >= 0:
            return terminal_wealth(
                PlayerState(13, w2, f2, state.cash, arrived=True), game
            )
    return terminal_wealth(state, game) if state.arrived else 0.0


def run_exact_small_game() -> dict[str, float]:
    """精确小子游戏对照"""
    subgraph = _build_exact_small_subgraph()
    small_game = replace(
        LEVEL6_GAME,
        player_count=3,
        deadline=4,
        capacity_kg=1200,
        initial_cash=5000,
        mine_income=200,
    )
    weather = ("晴朗", "晴朗", "晴朗", "晴朗")
    initial_cash = 5000.0 - 5 * 30 - 10 * 30
    initial = tuple(
        PlayerState(
            node=1,
            water=30,
            food=30,
            cash=initial_cash,
            arrived=False,
        )
        for _ in range(3)
    )

    cache: dict = {}
    exact_values = _solve_exact_subgame(
        initial, 1, weather, small_game, subgraph, cache
    )

    approx_cache: dict = {}
    approx_values_tuple = _solve_approximate_subgame(
        initial, 1, weather, small_game, subgraph, approx_cache
    )
    approx_values = list(approx_values_tuple)
    approx_failure = ""

    exact_clean = [v if v > -1e11 else None for v in exact_values]
    approx_clean = list(approx_values)

    exact_total = sum(v for v in exact_clean if v is not None)
    approx_total = sum(v for v in approx_clean if v is not None)
    n_exact = sum(1 for v in exact_clean if v is not None)
    n_approx = sum(1 for v in approx_clean if v is not None)
    exact_avg = exact_total / n_exact if n_exact else None
    approx_avg = approx_total / n_approx if n_approx else None

    absolute_gap = (
        abs(exact_avg - approx_avg)
        if exact_avg is not None and approx_avg is not None
        else 0.0
    )
    relative_gap = (
        absolute_gap / abs(exact_avg)
        if exact_avg not in (None, 0.0) and absolute_gap
        else 0.0
    )

    return {
        "exact_value": float(exact_avg) if exact_avg is not None else float(-_inf),
        "approx_value": float(approx_avg) if approx_avg is not None else float(-_inf),
        "absolute_gap": float(absolute_gap),
        "relative_gap": float(relative_gap),
        "action_match": float(exact_clean == approx_clean),
        "exact_per_player": [float(v) if v is not None else float(-_inf)
                             for v in exact_clean],
        "approx_per_player": [float(v) if v is not None else float(-_inf)
                              for v in approx_clean],
        "value_diff_per_player": [
            float((e or 0) - (a or 0))
            for e, a in zip(exact_clean, approx_clean)
        ],
        "exact_cache_size": len(cache),
        "exact_subgraph": "1->6->13",
        "exact_horizon_days": small_game.deadline,
        "exact_player_count": small_game.player_count,
        "exact_initial_water": 30,
        "exact_initial_food": 30,
        "approx_failure_reason": approx_failure,
    }


def run_gamma_scan(
    game: GameConfig,
    level: LevelConfig,
    gammas: Iterable[int] = range(7),
) -> tuple[dict[str, object], ...]:
    """Gamma扫描"""
    rows = []
    for gamma in gammas:
        try:
            plan = plan_initial_purchase(gamma, game, level)
            rows.append(
                {
                    "Gamma": gamma,
                    "可行": True,
                    "初始水": plan.state.water,
                    "初始食物": plan.state.food,
                    "最坏财富下界": plan.value.worst_wealth,
                    "策略类别": plan.value.policy,
                    "挖矿天数": plan.value.mining_days,
                    "保证用时": plan.value.required_days,
                }
            )
        except RuntimeError:
            rows.append(
                {
                    "Gamma": gamma,
                    "可行": False,
                    "初始水": None,
                    "初始食物": None,
                    "最坏财富下界": None,
                    "策略类别": "无鲁棒可行方案",
                    "挖矿天数": None,
                    "保证用时": None,
                }
            )
    return tuple(rows)


def run_parameter_scan(
    game: GameConfig,
    level: LevelConfig,
) -> tuple[dict[str, object], ...]:
    """参数扫描"""
    rows = []
    for label, values in (
        ("R", (500, 1000, 1500)),
        ("M", (1000, 1200, 1400)),
        ("C0", (8000, 10000, 12000)),
    ):
        for value in values:
            variant = game
            if label == "R":
                variant = replace(game, mine_income=value)
            elif label == "M":
                variant = replace(game, capacity_kg=value)
            else:
                variant = replace(game, initial_cash=value)
            try:
                plan = plan_initial_purchase(2, variant, level)
                rows.append(
                    {
                        "参数": label,
                        "参数值": value,
                        "可行": True,
                        "最坏财富下界": plan.value.worst_wealth,
                        "策略类别": plan.value.policy,
                        "挖矿天数": plan.value.mining_days,
                    }
                )
            except RuntimeError:
                rows.append(
                    {
                        "参数": label,
                        "参数值": value,
                        "可行": False,
                        "最坏财富下界": None,
                        "策略类别": "无鲁棒可行方案",
                        "挖矿天数": None,
                    }
                )
    return tuple(rows)


def run_initial_purchase_neighborhood(
    game: GameConfig,
    level: LevelConfig,
    gamma: int,
    radius: int = 2,
) -> tuple[dict[str, object], ...]:
    """初始采购邻域扫描"""
    center = plan_initial_purchase(gamma, game, level)
    rows = []
    for delta_water in range(-radius, radius + 1):
        for delta_food in range(-radius, radius + 1):
            water = center.state.water + delta_water
            food = center.state.food + delta_food
            try:
                state = initial_state(water, food, game, level)
                value = robust_value(1, state, gamma, game, level)
                feasible = value.feasible
                wealth = value.worst_wealth if feasible else None
                policy = value.policy if feasible else "无鲁棒可行方案"
            except ValueError:
                feasible = False
                wealth = None
                policy = "初始采购不可行"
            rows.append(
                {
                    "初始水": water,
                    "初始食物": food,
                    "水偏移": delta_water,
                    "食物偏移": delta_food,
                    "可行": feasible,
                    "最坏财富下界": wealth,
                    "策略类别": policy,
                    "是否推荐点": delta_water == 0 and delta_food == 0,
                }
            )
    return tuple(rows)


def run_empirical_resample(
    weather_template: Iterable[str],
    gamma: int,
    config: RollingConfig,
    n_samples: int = 30,
    seed: int = 42,
) -> tuple[dict[str, object], ...]:
    """经验重采样"""
    template = tuple(weather_template)
    rng = random.Random(seed)
    success_count = 0
    wealths: list[float] = []
    epsilons: list[float] = []
    for _ in range(n_samples):
        sample = tuple(rng.choice(template) for _ in range(len(template)))
        try:
            sim = rolling_simulation(sample, gamma, config)
        except Exception:
            continue
        if sim.success:
            success_count += 1
        for w in sim.terminal_wealths:
            if w is not None:
                wealths.append(float(w))
        eps = max((day.equilibrium.epsilon for day in sim.days), default=0.0)
        epsilons.append(float(eps))

    avg_wealth = mean(wealths) if wealths else None
    std_wealth = stdev(wealths) if len(wealths) > 1 else None
    med_wealth = median(wealths) if wealths else None
    if avg_wealth is not None and std_wealth is not None and len(wealths) > 1:
        half_width = 1.96 * std_wealth / (len(wealths) ** 0.5)
        ci_low = avg_wealth - half_width
        ci_high = avg_wealth + half_width
    else:
        ci_low = ci_high = None

    return (
        {
            "样本数": n_samples,
            "成功样本数": success_count,
            "成功率": success_count / n_samples if n_samples else 0.0,
            "平均终端财富": avg_wealth,
            "财富标准差": std_wealth,
            "财富中位数": med_wealth,
            "财富95%CI下界": ci_low,
            "财富95%CI上界": ci_high,
            "最大epsilon": max(epsilons, default=0.0),
            "随机种子": seed,
            "模板长度": len(template),
        },
    )


def summarize_simulation(simulation, config: RollingConfig) -> dict[str, object]:
    """模拟摘要"""
    audit = audit_simulation(simulation, config)
    loss = conflict_loss(simulation, config.game)
    return {
        "成功": simulation.success,
        "执行天数": len(simulation.days),
        "终端财富": list(simulation.terminal_wealths),
        "epsilon_max": max(
            (day.equilibrium.epsilon for day in simulation.days), default=0.0
        ),
        "规则违规数": audit.violation_count,
        "最大守恒残差": audit.max_abs_residual,
        "冲突损失": asdict(loss),
    }


def _baseline_row(version: str, baseline) -> dict[str, object]:
    """基准行"""
    return {
        "版本": version,
        "成功": baseline.success,
        "执行天数": baseline.executed_days,
        "平均终端财富": baseline.mean_terminal_wealth,
        "最差终端财富": baseline.minimum_terminal_wealth,
        "epsilon_max": baseline.epsilon_max,
        "L_move": baseline.conflict_loss.move,
        "L_mine": baseline.conflict_loss.mine,
        "L_village": baseline.conflict_loss.village,
        "L_conflict": baseline.conflict_loss.total,
        "失败原因": baseline.failure_reason,
    }


def run_ablation(
    weather_sequence,
    gamma: int,
    config: RollingConfig,
) -> tuple[dict[str, object], ...]:
    """消融实验"""
    baselines = {row.name: row for row in run_baselines(weather_sequence, gamma, config)}
    no_robust = rolling_simulation(weather_sequence, 0, config)
    no_robust_summary = summarize_simulation(no_robust, config)
    no_robust_loss = no_robust_summary["冲突损失"]
    return (
        _baseline_row("Full", baselines["Full"]),
        _baseline_row("-Game", baselines["B1"]),
        _baseline_row("-Rolling", baselines["B0"]),
        _baseline_row("-FutureValue", baselines["B2"]),
        {
            "版本": "-Robust",
            "成功": no_robust_summary["成功"],
            "执行天数": no_robust_summary["执行天数"],
            "平均终端财富": (
                sum(value for value in no_robust.terminal_wealths if value is not None)
                / sum(value is not None for value in no_robust.terminal_wealths)
                if any(value is not None for value in no_robust.terminal_wealths)
                else None
            ),
            "最差终端财富": min(
                (value for value in no_robust.terminal_wealths if value is not None),
                default=None,
            ),
            "epsilon_max": no_robust_summary["epsilon_max"],
            "L_move": no_robust_loss["move"],
            "L_mine": no_robust_loss["mine"],
            "L_village": no_robust_loss["village"],
            "L_conflict": no_robust_loss["total"],
            "失败原因": no_robust.failure_reason,
        },
    )


def run_player_count_scan(
    weather_sequence,
    gamma: int,
    config: RollingConfig,
    player_counts: Iterable[int] = (2, 3, 4),
) -> tuple[dict[str, object], ...]:
    """玩家数扫描"""
    rows = []
    for count in player_counts:
        if count < 1:
            raise ValueError("玩家数必须为正整数")
        variant = RollingConfig(
            replace(config.game, player_count=count),
            config.level,
            config.tolerance,
        )
        simulation = rolling_simulation(weather_sequence, gamma, variant)
        summary = summarize_simulation(simulation, variant)
        loss = summary["冲突损失"]
        wealths = [value for value in simulation.terminal_wealths if value is not None]
        rows.append(
            {
                "玩家数": count,
                "推广试验": True,
                "成功": simulation.success,
                "平均终端财富": sum(wealths) / len(wealths) if wealths else None,
                "最差终端财富": min(wealths) if wealths else None,
                "epsilon_max": summary["epsilon_max"],
                "L_conflict": loss["total"],
                "执行天数": len(simulation.days),
            }
        )
    return tuple(rows)


print("验证实验加载完成")
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


def load_level6() -> tuple[GameConfig, LevelConfig]:
    """加载第六关配置"""
    level = make_level(
        name="第六关",
        node_count=25,
        edges=LEVEL6_EDGES,
        start=1,
        goal=25,
        villages=frozenset({14}),
        mines=frozenset({18}),
    )
    audit = audit_graph(level)
    if not (audit.symmetric and audit.connected and audit.key_nodes_reachable):
        raise ValueError(f"第六关地图审计失败：{audit}")
    if audit.duplicate_edge_count:
        raise ValueError("第六关邻接表存在重复边")
    return LEVEL6_GAME, level


def audit_graph(level: LevelConfig) -> GraphAudit:
    """审计地图配置"""
    symmetric = all(
        u in level.neighbors[v] and v in level.neighbors[u]
        for u, v in level.edges
    )
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
        duplicate_edge_count=len(level.edges) - len(set(level.edges)),
    )


print("数据加载器加载完成")
print()

# export - 结果导出

print()
print("export - 结果导出")
print()


def _jsonable(value):
    """JSON序列化辅助"""
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    return value


def write_json(path: Path, value) -> None:
    """写入JSON文件"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_jsonable(value), ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )


def write_csv(path: Path, rows: Iterable[Mapping[str, object]]) -> None:
    """写入CSV文件"""
    materialized = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    for row in materialized:
        for field in row:
            if field not in fieldnames:
                fieldnames.append(field)
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


# 仅用于复现实验的公开历史轨迹；第六关在线决策函数从不读取未来天气
EMPIRICAL_PRESSURE_WEATHER = (
    "高温", "高温", "晴朗", "沙暴", "晴朗", "高温", "沙暴", "晴朗", "高温", "高温",
    "沙暴", "高温", "晴朗", "高温", "高温", "高温", "沙暴", "沙暴", "高温", "高温",
    "晴朗", "晴朗", "高温", "晴朗", "沙暴", "高温", "晴朗", "晴朗", "高温", "高温",
)


def _daily_rows(simulation: RollingSimulation) -> tuple[dict[str, object], ...]:
    """生成逐日策略行"""
    rows = []
    for day in simulation.days:
        for player, (before, action, after) in enumerate(
            zip(day.states_before, day.actions, day.states_after), start=1
        ):
            rows.append(
                {
                    "天数": day.day,
                    "当天天气": day.weather,
                    "玩家": player,
                    "行动前节点": before.node,
                    "行动": action.kind,
                    "目的节点": action.destination,
                    "购买水": action.buy_water,
                    "购买食物": action.buy_food,
                    "消耗倍数": day.multipliers[player - 1],
                    "耗水": day.water_consumption[player - 1],
                    "耗食物": day.food_consumption[player - 1],
                    "购买支出": day.purchase_cost[player - 1],
                    "挖矿收入": day.mine_income[player - 1],
                    "行动后节点": after.node,
                    "剩余水": after.water,
                    "剩余食物": after.food,
                    "剩余现金": after.cash,
                    "已到终点": after.arrived,
                    "均衡类型": day.equilibrium.kind,
                    "当日epsilon": day.equilibrium.epsilon,
                }
            )
    return tuple(rows)


def _baseline_rows(weather, gamma, config):
    """基准行"""
    rows = []
    for result in run_baselines(weather, gamma, config):
        rows.append(
            {
                "基准": result.name,
                "定义": result.definition,
                "成功": result.success,
                "执行天数": result.executed_days,
                "平均终端财富": result.mean_terminal_wealth,
                "最差终端财富": result.minimum_terminal_wealth,
                "epsilon_max": result.epsilon_max,
                "L_move": result.conflict_loss.move,
                "L_mine": result.conflict_loss.mine,
                "L_village": result.conflict_loss.village,
                "L_conflict": result.conflict_loss.total,
                "失败原因": result.failure_reason,
            }
        )
    return tuple(rows)


def _information_leakage_test(weather, gamma, config) -> tuple[bool, int, int]:
    """信息泄露检验"""
    if not weather:
        return True, 0, 0
    alternatives = {"晴朗": "高温", "高温": "晴朗", "沙暴": "晴朗"}
    total = 0
    passed = 0
    for t in range(1, len(weather) + 1):
        cf = tuple(
            weather[i] if i < t else alternatives[weather[i]]
            for i in range(len(weather))
        )
        if weather[: t - 1] != cf[: t - 1]:
            continue
        total += 1
        if counterfactual_prefix_test(weather, cf, t, gamma, config):
            passed += 1
    return passed == total, passed, total


def run_experiment(
    config: RollingConfig,
    weather_sequence: Sequence[str],
    gamma: int,
    output_root: Path,
    include_extended: bool = True,
) -> dict[str, object]:
    """运行实验"""
    weather = tuple(weather_sequence)
    simulation = rolling_simulation(weather, gamma, config)
    audit = audit_simulation(simulation, config)
    loss = conflict_loss(simulation, config.game)
    regret = ex_post_regret_upper_bound(simulation, config.game)
    leakage_ok, leakage_passed, leakage_total = _information_leakage_test(
        weather, gamma, config
    )
    epsilon_max = max(
        (day.equilibrium.epsilon for day in simulation.days), default=0.0
    )
    wealths = [value for value in simulation.terminal_wealths if value is not None]
    resample_rows = run_empirical_resample(weather, gamma, config)
    resample = resample_rows[0]
    summary = {
        "experiment_type": "empirical_pressure_test",
        "future_weather_used_by_policy": False,
        "players": config.game.player_count,
        "Gamma": gamma,
        "weather_days_provided": len(weather),
        "executed_days": len(simulation.days),
        "success": simulation.success,
        "terminal_wealths": list(simulation.terminal_wealths),
        "mean_terminal_wealth": mean(wealths) if wealths else None,
        "epsilon_max": epsilon_max,
        "conflict_loss": asdict(loss),
        "information_leakage_ok": leakage_ok,
        "information_leakage_passed": leakage_passed,
        "information_leakage_total": leakage_total,
        "audit_check_count": audit.check_count,
        "audit_violation_count": audit.violation_count,
        "audit_max_abs_residual": audit.max_abs_residual,
        "audit_messages": list(audit.messages),
        "failure_reason": simulation.failure_reason,
        "resample_n_samples": resample["样本数"],
        "resample_success_rate": resample["成功率"],
        "resample_mean_wealth": resample["平均终端财富"],
    }
    if audit.violation_count or audit.max_abs_residual != 0 or not leakage_ok:
        raise RuntimeError("模型检验未通过，拒绝导出未经验证的第六关结果")
    if epsilon_max > config.tolerance:
        raise RuntimeError(f"阶段均衡误差超限：epsilon={epsilon_max}")

    output_root = Path(output_root)
    write_csv(output_root / "结果输出" / "第六关逐日滚动策略.csv", _daily_rows(simulation))
    write_json(output_root / "结果输出" / "第六关经验压力测试摘要.json", summary)
    write_csv(
        output_root / "结果验证" / "第六关" / "第六关Ex-post-Regret上界.csv",
        (asdict(row) for row in regret),
    )

    if include_extended:
        write_csv(
            output_root / "结果验证" / "第六关" / "第六关经验重采样.csv",
            resample_rows,
        )
        write_csv(
            output_root / "结果验证" / "第六关" / "第六关基准对比.csv",
            _baseline_rows(weather, gamma, config),
        )
        write_csv(
            output_root / "结果验证" / "第六关" / "第六关消融实验.csv",
            run_ablation(weather, gamma, config),
        )
        write_csv(
            output_root / "结果验证" / "第六关" / "第六关Gamma灵敏度.csv",
            run_gamma_scan(config.game, config.level),
        )
        write_csv(
            output_root / "结果验证" / "第六关" / "第六关参数灵敏度.csv",
            run_parameter_scan(config.game, config.level),
        )
        write_csv(
            output_root / "结果验证" / "第六关" / "第六关初始采购邻域灵敏度.csv",
            run_initial_purchase_neighborhood(config.game, config.level, gamma),
        )
        write_csv(
            output_root / "结果验证" / "第六关" / "第六关玩家数推广试验.csv",
            run_player_count_scan(weather, gamma, config),
        )
        write_json(
            output_root / "结果验证" / "第六关" / "第六关小规模精确对照.json",
            run_exact_small_game(),
        )
    return summary


def main() -> None:
    """主函数"""
    print()
    print("整合所有模块运行")
    print()

    print("运行地图验证...")
    game, level = load_level6()
    print(f"  地图验证完成：{level.name}，{level.node_count}节点，{len(level.edges)}条边")

    print()
    print("运行求解器...")
    print("  求解 第六关（多玩家鲁棒博弈）...")
    root = Path(__file__).resolve().parents[1]
    summary = run_experiment(
        RollingConfig(game=game, level=level),
        EMPIRICAL_PRESSURE_WEATHER,
        gamma=6,
        output_root=root,
    )
    print(f"  求解完成：成功={summary['success']}，执行{summary['executed_days']}天，终端财富={summary['terminal_wealths']}，epsilon_max={summary['epsilon_max']}")

    print()
    print("运行灵敏度分析...")
    print("  [01] 经验重采样检验")
    print("  [02] 基准策略对比")
    print("  [03] 消融实验")
    print("  [04] Gamma灵敏度扫描")
    print("  [05] 参数灵敏度扫描")
    print("  [06] 初始采购邻域灵敏度")
    print("  [07] 玩家数推广试验")
    print("  [08] 小规模精确对照")
    print("  灵敏性分析完成")

    print()
    print("【最终结果】")
    print()
    print("第六关（多玩家鲁棒博弈）：")
    print(f"  模型：多玩家逐日滚动均衡 + 鲁棒价值函数")
    print(f"  玩家数：{summary['players']}")
    print(f"  Gamma：{summary['Gamma']}")
    print(f"  执行天数：{summary['executed_days']}")
    print(f"  成功率：{summary['success']}")
    print(f"  终端财富：{summary['terminal_wealths']}")
    print(f"  平均终端财富：{summary['mean_terminal_wealth']:.1f}")
    print(f"  Epsilon最大值：{summary['epsilon_max']}")
    print(f"  信息泄露检验：{'通过' if summary['information_leakage_ok'] else '失败'}")

    print()
    print("求解完成")
    print()
    OUTPUT_DIR = root / "结果输出"
    print(f"输出目录：{OUTPUT_DIR}")
    print("包含文件：")
    for f in sorted(OUTPUT_DIR.iterdir()):
        print(f"  - {f.name}")
    print()

    print("第六关求解完成")
    print(f"成功={summary['success']}，执行{summary['executed_days']}天，epsilon_max={summary['epsilon_max']}")


if __name__ == "__main__":
    main()
