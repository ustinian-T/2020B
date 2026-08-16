"""官方参数、天气序列与两关地图的无向图封装。

地图拓扑与功能节点来自题目附件；邻接按"公共边界"建立
（仅共享顶点不连边），详见报告 5.1 节。
"""

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
    weather: tuple[Weather, ...]
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


WEATHER = (
    "高温", "高温", "晴朗", "沙暴", "晴朗", "高温", "沙暴", "晴朗", "高温", "高温",
    "沙暴", "高温", "晴朗", "高温", "高温", "高温", "沙暴", "沙暴", "高温", "高温",
    "晴朗", "晴朗", "高温", "晴朗", "沙暴", "高温", "晴朗", "晴朗", "高温", "高温",
)


GAME = GameConfig(
    capacity_kg=1200,
    initial_cash=10000,
    deadline=30,
    mine_income=1000,
    water_weight=3,
    food_weight=2,
    water_price=5,
    food_price=10,
    weather=WEATHER,
    base_consumption={"晴朗": (5, 7), "高温": (8, 6), "沙暴": (10, 10)},
)


LEVEL_ONE_EDGES = (
    (1, 2), (1, 25), (2, 3), (3, 4), (3, 25), (4, 5), (4, 24), (4, 25),
    (5, 6), (5, 24), (6, 7), (6, 23), (6, 24), (7, 8), (7, 22), (8, 9),
    (8, 22), (9, 10), (9, 15), (9, 16), (9, 17), (9, 21), (9, 22), (10, 11),
    (10, 13), (10, 15), (11, 12), (11, 13), (12, 13), (12, 14), (13, 14),
    (13, 15), (14, 15), (14, 16), (15, 16), (16, 17), (16, 18), (17, 18),
    (17, 21), (18, 19), (18, 20), (19, 20), (20, 21), (21, 22), (21, 23),
    (21, 27), (22, 23), (23, 24), (23, 26), (24, 25), (24, 26), (25, 26),
    (26, 27),
)


def _make_level(
    name: str,
    node_count: int,
    edges: tuple[tuple[int, int], ...],
    start: int,
    goal: int,
    villages: frozenset[int],
    mines: frozenset[int],
) -> LevelConfig:
    adjacency = {node: set() for node in range(1, node_count + 1)}
    normalized = tuple(sorted((min(i, j), max(i, j)) for i, j in edges))
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

def build_level_one() -> LevelConfig:
    return _make_level("第一关", 27, LEVEL_ONE_EDGES, 1, 27, frozenset({15}), frozenset({12}))


def build_level_two() -> LevelConfig:
    rows = cols = 8
    odd_deltas = ((-1, -1), (-1, 0), (0, -1), (0, 1), (1, -1), (1, 0))
    even_deltas = ((-1, 0), (-1, 1), (0, -1), (0, 1), (1, 0), (1, 1))
    edges: list[tuple[int, int]] = []
    for node in range(1, rows * cols + 1):
        row = (node - 1) // cols + 1
        col = (node - 1) % cols + 1
        deltas = odd_deltas if row % 2 else even_deltas
        for d_row, d_col in deltas:
            next_row, next_col = row + d_row, col + d_col
            if 1 <= next_row <= rows and 1 <= next_col <= cols:
                neighbor = (next_row - 1) * cols + next_col
                if node < neighbor:
                    edges.append((node, neighbor))
    return _make_level(
        "第二关", 64, tuple(edges), 1, 64, frozenset({39, 62}), frozenset({30, 55})
    )
