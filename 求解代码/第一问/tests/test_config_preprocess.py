from pathlib import Path
import sys

import pytest


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT))

from 模型求解.config import GAME, build_level_one, build_level_two
from 模型求解.preprocess import bfs_distances, validate_level


def test_common_weather_and_parameters_match_attachment():
    assert len(GAME.weather) == 30
    assert set(GAME.weather) == {"晴朗", "高温", "沙暴"}
    assert GAME.capacity_kg == 1200
    assert GAME.initial_cash == 10000
    assert GAME.deadline == 30
    assert GAME.mine_income == 1000
    assert GAME.base_consumption["晴朗"] == (5, 7)
    assert GAME.base_consumption["高温"] == (8, 6)
    assert GAME.base_consumption["沙暴"] == (10, 10)


@pytest.mark.parametrize(
    ("builder", "node_count", "edge_count", "start", "goal", "villages", "mines"),
    [
        (build_level_one, 27, 53, 1, 27, frozenset({15}), frozenset({12})),
        (build_level_two, 64, 161, 1, 64, frozenset({39, 62}), frozenset({30, 55})),
    ],
)
def test_level_graph_is_valid_and_connected(
    builder, node_count, edge_count, start, goal, villages, mines
):
    level = builder()
    report = validate_level(level)

    assert report.ok, report.errors
    assert level.node_count == node_count
    assert len(level.edges) == edge_count
    assert level.start == start
    assert level.goal == goal
    assert level.villages == villages
    assert level.mines == mines

    distances = bfs_distances(level, goal)
    assert distances[start] < node_count
    for i, j in level.edges:
        assert j in level.neighbors[i]
        assert i in level.neighbors[j]


def test_second_level_hex_grid_selected_neighbors():
    level = build_level_two()

    assert level.neighbors[1] == frozenset({2, 9})
    assert level.neighbors[8] == frozenset({7, 15, 16})
    assert level.neighbors[9] == frozenset({1, 2, 10, 17, 18})
    assert level.neighbors[64] == frozenset({56, 63})
