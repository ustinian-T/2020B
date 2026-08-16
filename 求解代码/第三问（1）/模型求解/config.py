from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


Weather = str


@dataclass(frozen=True)
class GameConfig:
    player_count: int
    capacity_kg: int
    initial_cash: int
    deadline: int
    mine_income: int
    water_weight: int = 3
    food_weight: int = 2
    water_price: int = 5
    food_price: int = 10
    base_consumption: Mapping[Weather, tuple[int, int]] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.base_consumption is None:
            object.__setattr__(
                self,
                "base_consumption",
                {"晴朗": (3, 4), "高温": (9, 9), "沙暴": (10, 10)},
            )


@dataclass(frozen=True)
class LevelConfig:
    name: str
    node_count: int
    edges: tuple[tuple[int, int], ...]
    neighbors: Mapping[int, frozenset[int]]
    start: int
    goal: int
    villages: frozenset[int]
    mines: frozenset[int]


LEVEL5_EDGES = (
    (1, 2), (1, 4), (1, 5),
    (2, 3), (2, 4),
    (3, 4), (3, 8), (3, 9),
    (4, 5), (4, 6), (4, 7),
    (5, 6),
    (6, 7), (6, 12), (6, 13),
    (7, 11), (7, 12),
    (8, 9),
    (9, 10), (9, 11),
    (10, 11), (10, 13),
    (11, 12), (11, 13),
    (12, 13),
)

LEVEL5_WEATHER = (
    "晴朗", "高温", "晴朗", "晴朗", "晴朗",
    "晴朗", "高温", "高温", "高温", "高温",
)

LEVEL5_GAME = GameConfig(
    player_count=2,
    capacity_kg=1200,
    initial_cash=10000,
    deadline=10,
    mine_income=200,
)


def make_level(
    name: str,
    node_count: int,
    edges: tuple[tuple[int, int], ...],
    start: int,
    goal: int,
    villages: frozenset[int],
    mines: frozenset[int],
) -> LevelConfig:
    normalized = tuple(sorted((min(u, v), max(u, v)) for u, v in edges))
    adjacency = {node: set() for node in range(1, node_count + 1)}
    for u, v in normalized:
        if u == v or u not in adjacency or v not in adjacency:
            raise ValueError(f"非法边：{u}-{v}")
        adjacency[u].add(v)
        adjacency[v].add(u)
    return LevelConfig(
        name=name,
        node_count=node_count,
        edges=normalized,
        neighbors={node: frozenset(items) for node, items in adjacency.items()},
        start=start,
        goal=goal,
        villages=villages,
        mines=mines,
    )

