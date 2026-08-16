from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class GameConfig:
    player_count: int
    capacity_kg: int
    initial_cash: int
    deadline: int
    mine_income: int
    water_weight: int
    food_weight: int
    water_price: int
    food_price: int
    base_consumption: Mapping[str, tuple[int, int]]


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

LEVEL6_GAME = GameConfig(
    player_count=3,
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


def grid_edges(rows: int, columns: int) -> tuple[tuple[int, int], ...]:
    edges: list[tuple[int, int]] = []
    for node in range(1, rows * columns + 1):
        row, column = divmod(node - 1, columns)
        if column + 1 < columns:
            edges.append((node, node + 1))
        if row + 1 < rows:
            edges.append((node, node + columns))
    return tuple(edges)


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
        name,
        node_count,
        normalized,
        {node: frozenset(items) for node, items in adjacency.items()},
        start,
        goal,
        villages,
        mines,
    )


LEVEL6_EDGES = grid_edges(5, 5)

