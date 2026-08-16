from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Sequence

from .config import GameConfig
from .game_rolling import RollingConfig, RollingSimulation, choose_actions, rolling_simulation
from .transition import terminal_wealth, total_weight


@dataclass(frozen=True)
class AuditReport:
    check_count: int
    violation_count: int
    max_abs_residual: float
    messages: tuple[str, ...]


@dataclass(frozen=True)
class ConflictLoss:
    move: float
    mine: float
    village: float
    total: float


@dataclass(frozen=True)
class RegretRow:
    player: int
    online_wealth: float
    oracle_upper_bound: float
    regret: float


def audit_simulation(
    simulation: RollingSimulation,
    config: RollingConfig,
) -> AuditReport:
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
    """给出可复核的宽松事后上界；不会把它表述为完整 MPE。"""
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

