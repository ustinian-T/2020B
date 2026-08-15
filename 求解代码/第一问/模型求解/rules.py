from __future__ import annotations

from .config import GameConfig, LevelConfig


ACTION_MULTIPLIER = {"停留": 1, "行走": 2, "挖矿": 3}


def action_consumption(
    game: GameConfig, weather: str, action: str
) -> tuple[int, int]:
    if action not in ACTION_MULTIPLIER:
        raise ValueError(f"未知行动：{action}")
    water, food = game.base_consumption[weather]
    multiplier = ACTION_MULTIPLIER[action]
    return water * multiplier, food * multiplier


def legal_action(
    level: LevelConfig, weather: str, from_node: int, to_node: int, action: str
) -> bool:
    if action == "行走":
        return weather != "沙暴" and to_node in level.neighbors[from_node]
    if action == "停留":
        return from_node == to_node
    if action == "挖矿":
        return from_node == to_node and from_node in level.mines
    return False
