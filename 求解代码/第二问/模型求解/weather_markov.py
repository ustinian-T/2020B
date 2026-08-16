from __future__ import annotations

from itertools import product
from typing import Iterable, Sequence

import numpy as np


WEATHER_STATES = ("晴朗", "高温", "沙暴")
HISTORICAL_WEATHER = (
    "高温", "高温", "晴朗", "沙暴", "晴朗", "高温", "沙暴", "晴朗", "高温", "高温",
    "沙暴", "高温", "晴朗", "高温", "高温", "高温", "沙暴", "沙暴", "高温", "高温",
    "晴朗", "晴朗", "高温", "晴朗", "沙暴", "高温", "晴朗", "晴朗", "高温", "高温",
)


def estimate_transition_counts(
    weather: Sequence[str], states: tuple[str, ...] = WEATHER_STATES
) -> tuple[tuple[str, ...], np.ndarray]:
    if len(weather) < 2:
        raise ValueError("至少需要两天天气才能统计转移")
    index = {state: i for i, state in enumerate(states)}
    unknown = set(weather) - set(states)
    if unknown:
        raise ValueError(f"存在未知天气状态：{sorted(unknown)}")
    counts = np.zeros((len(states), len(states)), dtype=int)
    for current, following in zip(weather, weather[1:]):
        counts[index[current], index[following]] += 1
    return states, counts


def nominal_transition_probabilities(
    weather: Sequence[str] = HISTORICAL_WEATHER,
    allowed_states: tuple[str, ...] = WEATHER_STATES,
) -> tuple[tuple[str, ...], np.ndarray]:
    states, counts = estimate_transition_counts(weather)
    source_index = {state: i for i, state in enumerate(states)}
    selected = np.asarray(
        [[counts[source_index[i], source_index[j]] for j in allowed_states] for i in allowed_states],
        dtype=float,
    )
    row_sums = selected.sum(axis=1)
    if np.any(row_sums == 0):
        raise ValueError("允许天气集合中存在没有历史转移的状态")
    return allowed_states, selected / row_sums[:, None]


def empirical_initial_probabilities(
    weather: Sequence[str], allowed_states: tuple[str, ...]
) -> dict[str, float]:
    counts = {state: sum(item == state for item in weather) for state in allowed_states}
    total = sum(counts.values())
    if total == 0:
        probability = 1.0 / len(allowed_states)
        return {state: probability for state in allowed_states}
    return {state: count / total for state, count in counts.items()}


def enumerate_weather_scenarios(
    days: int, states: Iterable[str]
) -> tuple[tuple[str, ...], ...]:
    if days < 0:
        raise ValueError("天数不能为负")
    state_tuple = tuple(states)
    if not state_tuple:
        raise ValueError("天气状态集合不能为空")
    return tuple(product(state_tuple, repeat=days))
