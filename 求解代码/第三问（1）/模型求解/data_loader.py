from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from .config import (
    LEVEL5_EDGES,
    LEVEL5_GAME,
    LEVEL5_WEATHER,
    GameConfig,
    LevelConfig,
    make_level,
)


@dataclass(frozen=True)
class GraphAudit:
    symmetric: bool
    connected: bool
    key_nodes_reachable: bool
    duplicate_edge_count: int


def load_level5() -> tuple[GameConfig, LevelConfig, tuple[str, ...]]:
    normalized = tuple(sorted((min(u, v), max(u, v)) for u, v in LEVEL5_EDGES))
    level = make_level(
        name="第五关",
        node_count=13,
        edges=normalized,
        start=1,
        goal=13,
        villages=frozenset(),
        mines=frozenset({9}),
    )
    audit = audit_graph(level)
    if not (audit.symmetric and audit.connected and audit.key_nodes_reachable):
        raise ValueError(f"第五关地图审计失败：{audit}")
    if audit.duplicate_edge_count:
        raise ValueError("第五关邻接表存在重复边")
    return LEVEL5_GAME, level, LEVEL5_WEATHER


def audit_graph(level: LevelConfig) -> GraphAudit:
    symmetric = all(
        u in level.neighbors[v] and v in level.neighbors[u]
        for u, v in level.edges
    )
    duplicate_edge_count = len(level.edges) - len(set(level.edges))
    reached = {level.start}
    queue = deque([level.start])
    while queue:
        node = queue.popleft()
        for neighbor in level.neighbors[node]:
            if neighbor not in reached:
                reached.add(neighbor)
                queue.append(neighbor)
    key_nodes = {level.start, level.goal, *level.villages, *level.mines}
    return GraphAudit(
        symmetric=symmetric,
        connected=len(reached) == level.node_count,
        key_nodes_reachable=key_nodes <= reached,
        duplicate_edge_count=duplicate_edge_count,
    )
