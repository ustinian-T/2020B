from __future__ import annotations

from dataclasses import dataclass
from math import inf
from typing import Sequence

from .config import GameConfig, LevelConfig
from .transition import Action, PlayerState, initial_state, legal_actions, terminal_wealth


@dataclass(frozen=True)
class Plan:
    initial_water: int
    initial_food: int
    actions: tuple[Action, ...]


@dataclass(frozen=True)
class DailyRecord:
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
    return tuple(_opponent_timeline(plan, level, days) for plan in opponents)


def _externality(
    day_index: int,
    node: int,
    action: Action,
    timelines: Sequence[Sequence[_OpponentEvent | None]],
) -> tuple[int, int]:
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
