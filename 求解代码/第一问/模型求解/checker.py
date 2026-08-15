from __future__ import annotations

from dataclasses import dataclass

from .config import GameConfig, LevelConfig
from .rules import action_consumption, legal_action


@dataclass(frozen=True)
class InitialPurchase:
    water: int
    food: int


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


@dataclass(frozen=True)
class CheckResult:
    ok: bool
    errors: tuple[str, ...]
    final_wealth: float | None


def replay_strategy(
    level: LevelConfig,
    game: GameConfig,
    initial_purchase: InitialPurchase,
    daily_records: list[DailyRecord],
) -> CheckResult:
    errors: list[str] = []
    water = initial_purchase.water
    food = initial_purchase.food
    cash = game.initial_cash - game.water_price * water - game.food_price * food
    node = level.start

    if min(water, food, cash) < 0:
        errors.append("第0天采购导致库存或现金为负")
    if game.water_weight * water + game.food_weight * food > game.capacity_kg:
        errors.append("第0天采购超过负重上限")

    reached_goal = False
    for expected_day, record in enumerate(daily_records, start=1):
        if reached_goal:
            errors.append(f"第{record.day}天：到达终点后仍有行动")
            break
        if record.day != expected_day or record.day > game.deadline:
            errors.append(f"第{record.day}天：日期不连续或超过截止日")
        expected_weather = game.weather[record.day - 1]
        if record.weather != expected_weather:
            errors.append(f"第{record.day}天：天气记录不一致")
        if record.from_node != node:
            errors.append(f"第{record.day}天：行动起点与上一日位置不一致")
        if not legal_action(level, expected_weather, node, record.to_node, record.action):
            errors.append(f"第{record.day}天：{record.action}行动不合法")

        consume_water, consume_food = action_consumption(game, expected_weather, record.action)
        water -= consume_water
        food -= consume_food
        if water < 0 or food < 0:
            errors.append(f"第{record.day}天：行动途中资源不足")
        if record.action == "挖矿":
            cash += game.mine_income

        node = record.to_node
        if record.buy_water < 0 or record.buy_food < 0:
            errors.append(f"第{record.day}天：采购量必须为非负整数")
        if record.buy_water or record.buy_food:
            if node not in level.villages:
                errors.append(f"第{record.day}天：非村庄节点发生采购")
            cash -= 2 * (
                game.water_price * record.buy_water + game.food_price * record.buy_food
            )
            water += record.buy_water
            food += record.buy_food

        if cash < 0:
            errors.append(f"第{record.day}天：现金为负")
        if game.water_weight * water + game.food_weight * food > game.capacity_kg:
            errors.append(f"第{record.day}天：负重超过上限")
        if node != level.goal and (water <= 0 or food <= 0):
            errors.append(f"第{record.day}天：未到终点前资源耗尽")
        if (record.cash, record.water, record.food) != (cash, water, food):
            errors.append(f"第{record.day}天：记录值与独立复算不一致")
        reached_goal = node == level.goal

    if not reached_goal:
        errors.append("策略未在截止日前到达终点")
        final_wealth = None
    else:
        final_wealth = (
            cash + 0.5 * game.water_price * water + 0.5 * game.food_price * food
        )
    return CheckResult(not errors, tuple(errors), final_wealth)
