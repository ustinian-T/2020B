from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from .config import LevelConfig


@dataclass(frozen=True)
class ValidationReport:
    ok: bool
    errors: tuple[str, ...]


def bfs_distances(level: LevelConfig, target: int) -> dict[int, int]:
    if target not in level.neighbors:
        raise ValueError(f"目标节点 {target} 超出地图范围")
    distances = {target: 0}
    queue = deque([target])
    while queue:
        node = queue.popleft()
        for neighbor in level.neighbors[node]:
            if neighbor not in distances:
                distances[neighbor] = distances[node] + 1
                queue.append(neighbor)
    return distances


def validate_level(level: LevelConfig) -> ValidationReport:
    errors: list[str] = []
    valid_nodes = set(range(1, level.node_count + 1))
    if level.start not in valid_nodes or level.goal not in valid_nodes:
        errors.append("起点或终点超出节点范围")
    if not level.villages <= valid_nodes or not level.mines <= valid_nodes:
        errors.append("村庄或矿山节点超出节点范围")
    if len(level.edges) != len(set(level.edges)):
        errors.append("邻接边存在重复")
    for i, j in level.edges:
        if i == j:
            errors.append(f"存在自环 {i}-{j}")
        if i not in valid_nodes or j not in valid_nodes:
            errors.append(f"边 {i}-{j} 超出节点范围")
        elif j not in level.neighbors[i] or i not in level.neighbors[j]:
            errors.append(f"邻接关系 {i}-{j} 不对称")
    if level.start in valid_nodes and level.goal in valid_nodes:
        if level.goal not in bfs_distances(level, level.start):
            errors.append("起点与终点不连通")
    return ValidationReport(not errors, tuple(errors))
