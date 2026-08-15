from pathlib import Path
import sys

import pytest


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT))

from 模型求解.checker import DailyRecord, InitialPurchase, replay_strategy
from 模型求解.config import GameConfig, LevelConfig
from 模型求解.rules import action_consumption, legal_action


def tiny_game(weather=("晴朗", "高温")):
    return GameConfig(
        capacity_kg=1200,
        initial_cash=10000,
        deadline=len(weather),
        mine_income=1000,
        water_weight=3,
        food_weight=2,
        water_price=5,
        food_price=10,
        weather=tuple(weather),
        base_consumption={"晴朗": (5, 7), "高温": (8, 6), "沙暴": (10, 10)},
    )


def tiny_level(villages=frozenset(), mines=frozenset()):
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


@pytest.mark.parametrize(
    ("weather", "action", "expected"),
    [
        ("晴朗", "停留", (5, 7)),
        ("高温", "行走", (16, 12)),
        ("沙暴", "挖矿", (30, 30)),
    ],
)
def test_action_consumption(weather, action, expected):
    assert action_consumption(tiny_game(), weather, action) == expected


def test_sandstorm_forbids_move_but_allows_mining():
    level = tiny_level(mines=frozenset({2}))
    assert not legal_action(level, "沙暴", 2, 3, "行走")
    assert legal_action(level, "沙暴", 2, 2, "挖矿")


def test_checker_replays_move_and_terminal_refund():
    game = tiny_game()
    level = tiny_level()
    initial = InitialPurchase(water=26, food=26)
    records = [
        DailyRecord(1, "晴朗", 1, 2, "行走", 0, 0, 9610, 16, 12),
        DailyRecord(2, "高温", 2, 3, "行走", 0, 0, 9610, 0, 0),
    ]
    result = replay_strategy(level, game, initial, records)
    assert result.ok, result.errors
    assert result.final_wealth == 9610


def test_checker_applies_village_purchase_after_consumption():
    game = tiny_game(("晴朗", "高温", "晴朗"))
    level = tiny_level(villages=frozenset({2}))
    initial = InitialPurchase(water=10, food=14)
    records = [
        DailyRecord(1, "晴朗", 1, 2, "行走", 20, 20, 9210, 20, 20),
        DailyRecord(2, "高温", 2, 2, "停留", 0, 0, 9210, 12, 14),
        DailyRecord(3, "晴朗", 2, 3, "行走", 0, 0, 9210, 2, 0),
    ]
    result = replay_strategy(level, game, initial, records)
    assert result.ok, result.errors
    assert result.final_wealth == 9215


def test_checker_rejects_mining_on_arrival_day():
    game = tiny_game(("晴朗",))
    level = tiny_level(mines=frozenset({2}))
    initial = InitialPurchase(water=30, food=30)
    bad = [DailyRecord(1, "晴朗", 1, 2, "挖矿", 0, 0, 9550, 15, 9)]
    result = replay_strategy(level, game, initial, bad)
    assert not result.ok
    assert any("挖矿" in error for error in result.errors)
