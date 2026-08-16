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
    return game.water_weight * state.water + game.food_weight * state.food


def terminal_wealth(state: PlayerState, game: GameConfig) -> float:
    if not state.arrived:
        raise ValueError("仅到达终点的状态可以清算")
    return state.cash + 0.5 * game.water_price * state.water + 0.5 * game.food_price * state.food


def initial_state(
    water: int, food: int, game: GameConfig, level: LevelConfig
) -> PlayerState:
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
