from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


Weather = str


@dataclass(frozen=True)
class GameConfig:
    capacity_kg: int
    initial_cash: int
    deadline: int
    mine_income: int
    water_weight: int
    food_weight: int
    water_price: int
    food_price: int
    base_consumption: Mapping[Weather, tuple[int, int]]


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


BASE_CONSUMPTION = {"晴朗": (3, 4), "高温": (9, 9), "沙暴": (10, 10)}

LEVEL_THREE_GAME = GameConfig(
    capacity_kg=1200,
    initial_cash=10000,
    deadline=10,
    mine_income=200,
    water_weight=3,
    food_weight=2,
    water_price=5,
    food_price=10,
    base_consumption=BASE_CONSUMPTION,
)

LEVEL_FOUR_GAME = GameConfig(
    capacity_kg=1200,
    initial_cash=10000,
    deadline=30,
    mine_income=1000,
    water_weight=3,
    food_weight=2,
    water_price=5,
    food_price=10,
    base_consumption=BASE_CONSUMPTION,
)

LEVEL_THREE_EDGES = (
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


def _grid_edges(rows: int, cols: int) -> tuple[tuple[int, int], ...]:
    edges: list[tuple[int, int]] = []
    for node in range(1, rows * cols + 1):
        row, col = divmod(node - 1, cols)
        if col + 1 < cols:
            edges.append((node, node + 1))
        if row + 1 < rows:
            edges.append((node, node + cols))
    return tuple(edges)


LEVEL_FOUR_EDGES = _grid_edges(5, 5)


def _make_level(
    name: str,
    node_count: int,
    edges: tuple[tuple[int, int], ...],
    start: int,
    goal: int,
    villages: frozenset[int],
    mines: frozenset[int],
) -> LevelConfig:
    normalized = tuple(sorted((min(i, j), max(i, j)) for i, j in edges))
    adjacency = {node: set() for node in range(1, node_count + 1)}
    for i, j in normalized:
        adjacency[i].add(j)
        adjacency[j].add(i)
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


def build_level_three() -> LevelConfig:
    return _make_level(
        "第三关", 13, LEVEL_THREE_EDGES, 1, 13, frozenset(), frozenset({9})
    )


def build_level_four() -> LevelConfig:
    return _make_level(
        "第四关", 25, LEVEL_FOUR_EDGES, 1, 25, frozenset({14}), frozenset({18})
    )
