from dataclasses import replace
from pathlib import Path
import sys


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT))

from 模型求解.checker import replay_strategy
from 模型求解.config import GameConfig, LevelConfig
from 模型求解.solver import SolveOptions, solve


def tiny_game(days):
    return GameConfig(
        capacity_kg=1200,
        initial_cash=10000,
        deadline=days,
        mine_income=1000,
        water_weight=3,
        food_weight=2,
        water_price=5,
        food_price=10,
        weather=tuple("晴朗" for _ in range(days)),
        base_consumption={"晴朗": (5, 7), "高温": (8, 6), "沙暴": (10, 10)},
    )


def tiny_level(mines=frozenset(), villages=frozenset()):
    return LevelConfig(
        name="测试关卡",
        node_count=3,
        edges=((1, 2), (2, 3)),
        neighbors={1: frozenset({2}), 2: frozenset({1, 3}), 3: frozenset({2})},
        start=1,
        goal=3,
        villages=villages,
        mines=mines,
    )


def test_solver_finds_direct_two_day_optimum():
    game = tiny_game(2)
    level = tiny_level()
    result = solve(level, game, SolveOptions(time_limit_seconds=30))

    assert result.optimal
    assert result.final_wealth == 9620
    assert result.arrival_day == 2
    assert [record.action for record in result.daily_records] == ["行走", "行走"]
    check = replay_strategy(level, game, result.initial_purchase, result.daily_records)
    assert check.ok, check.errors


def test_solver_chooses_profitable_mining_day():
    game = tiny_game(3)
    level = tiny_level(mines=frozenset({2}))
    result = solve(level, game, SolveOptions(time_limit_seconds=30))

    assert result.optimal
    assert result.final_wealth == 10335
    assert [record.action for record in result.daily_records] == ["行走", "挖矿", "行走"]
    check = replay_strategy(level, game, result.initial_purchase, result.daily_records)
    assert check.ok, check.errors


def test_solver_obeys_sandstorm_and_waits():
    game = replace(tiny_game(3), weather=("沙暴", "晴朗", "晴朗"))
    level = tiny_level()
    result = solve(level, game, SolveOptions(time_limit_seconds=30))

    assert result.optimal
    assert result.arrival_day == 3
    assert result.daily_records[0].action == "停留"
    check = replay_strategy(level, game, result.initial_purchase, result.daily_records)
    assert check.ok, check.errors


def test_solver_cannot_leave_goal_to_reach_mine():
    game = tiny_game(5)
    level = LevelConfig(
        name="终点吸收测试",
        node_count=3,
        edges=((1, 2), (2, 3)),
        neighbors={1: frozenset({2}), 2: frozenset({1, 3}), 3: frozenset({2})},
        start=1,
        goal=2,
        villages=frozenset(),
        mines=frozenset({3}),
    )
    result = solve(level, game, SolveOptions(time_limit_seconds=30))

    assert result.arrival_day == 1
    assert result.final_wealth == 9810
    assert result.statistics["terminal_cash"] == result.daily_records[-1].cash
