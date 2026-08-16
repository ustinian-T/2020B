from __future__ import annotations

from dataclasses import dataclass

from .config import GameConfig, LevelConfig


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
