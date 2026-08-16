from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .config import GameConfig, LevelConfig
from .single_dp import Plan, PlanResult, best_response, evaluate_plan


@dataclass(frozen=True)
class PlayerDeviation:
    player: int
    current_wealth: float
    best_response_wealth: float
    gain: float


@dataclass(frozen=True)
class ExploitabilityReport:
    epsilon: float
    players: tuple[PlayerDeviation, ...]


@dataclass(frozen=True)
class AuditReport:
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
