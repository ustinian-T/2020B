from __future__ import annotations

from dataclasses import dataclass

from .config import GameConfig, LevelConfig
from .robust_dp_q3 import DailyRecord
from .transition import (
    ACTION_MULTIPLIER,
    State,
    apply_action,
    feasible_actions,
    terminal_wealth,
    total_weight,
)


@dataclass(frozen=True)
class OracleResult:
    final_wealth: float
    initial_water: int
    initial_food: int
    arrival_day: int
    actions: tuple
    records: tuple[DailyRecord, ...]


@dataclass(frozen=True)
class _Label:
    node: int
    water_used: int
    food_used: int
    mine_income: int
    actions: tuple


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


def solve_oracle(
    level: LevelConfig, game: GameConfig, weather_sequence: tuple[str, ...]
) -> OracleResult:
    """给定完整天气，求完全信息玩家的精确 Pareto 标签 DP 上界。"""
    if len(weather_sequence) != game.deadline:
        raise ValueError("Oracle 天气序列长度必须等于关卡截止日")
    if level.villages:
        raise ValueError("当前 Oracle 精确入口适用于无村庄的第三关")

    frontier: dict[int, list[_Label]] = {
        level.start: [_Label(level.start, 0, 0, 0, ())]
    }
    terminal: list[tuple[_Label, int]] = []
    for day, weather in enumerate(weather_sequence, start=1):
        next_frontier: dict[int, list[_Label]] = {}
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
                    candidate = _Label(
                        node=action.destination,
                        water_used=water_used,
                        food_used=food_used,
                        mine_income=label.mine_income
                        + (game.mine_income if action.kind == "挖矿" else 0),
                        actions=label.actions + (action,),
                    )
                    if candidate.node == level.goal:
                        terminal.append((candidate, day))
                    elif day < game.deadline:
                        _insert_pareto(
                            next_frontier.setdefault(candidate.node, []), candidate
                        )
        frontier = next_frontier

    if not terminal:
        raise RuntimeError("给定天气情景下不存在截止日前可行的 Oracle 路径")

    def score(item: tuple[_Label, int]) -> tuple[float, int, int, int]:
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
    records: list[DailyRecord] = []
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
        arrival_day=arrival_day,
        actions=best.actions,
        records=tuple(records),
    )
