from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Mapping, Sequence

from .config import GameConfig, LevelConfig


@dataclass(frozen=True, order=True)
class PlayerState:
    node: int
    water: int
    food: int
    cash: float
    arrived: bool = False


@dataclass(frozen=True, order=True)
class Action:
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
    states: tuple[PlayerState, ...]
    edge_counts: Mapping[tuple[int, int], int]
    mine_counts: Mapping[int, int]
    village_counts: Mapping[int, int]
    water_consumption: tuple[int, ...]
    food_consumption: tuple[int, ...]
    mine_income: tuple[float, ...]


def total_weight(state: PlayerState, game: GameConfig) -> int:
    return game.water_weight * state.water + game.food_weight * state.food


def terminal_wealth(state: PlayerState, game: GameConfig) -> float:
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
        next_state = PlayerState(
            node=destination,
            water=water,
            food=food,
            cash=state.cash + income,
            arrived=arrived,
        )
        if next_state.cash < 0:
            raise ValueError("资金不能为负")
        if total_weight(next_state, game) > game.capacity_kg:
            raise ValueError("负重超过上限")
        next_states.append(next_state)
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
