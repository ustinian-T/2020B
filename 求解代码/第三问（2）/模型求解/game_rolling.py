from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from itertools import product
from math import inf
from typing import Mapping, Sequence

import numpy as np
from scipy.optimize import minimize

from .config import GameConfig, LevelConfig
from .robust_value import robust_value
from .transition import Action, PlayerState, legal_actions, step_joint, terminal_wealth


@dataclass(frozen=True)
class RollingConfig:
    game: GameConfig
    level: LevelConfig
    tolerance: float = 1e-8


@dataclass(frozen=True)
class StageEquilibrium:
    kind: str
    actions: tuple[Action, ...]
    payoffs: tuple[float, ...]
    epsilon: float
    player_gains: tuple[float, ...]
    pure_equilibria: tuple[tuple[Action, ...], ...]
    mixed_probabilities: tuple[tuple[float, ...], ...]
    action_sets: tuple[tuple[Action, ...], ...]
    payoff_rows: tuple[tuple[tuple[Action, ...], tuple[float, ...]], ...]


def _distance(level: LevelConfig, start: int, goal: int) -> int:
    queue = deque([(start, 0)])
    reached = {start}
    while queue:
        node, distance = queue.popleft()
        if node == goal:
            return distance
        for neighbor in level.neighbors[node]:
            if neighbor not in reached:
                reached.add(neighbor)
                queue.append((neighbor, distance + 1))
    raise ValueError("图不连通")


def _purchase_options(
    state: PlayerState,
    gamma_remaining: int,
    game: GameConfig,
    level: LevelConfig,
) -> tuple[tuple[int, int], ...]:
    if state.node not in level.villages:
        return ((0, 0),)
    distance = _distance(level, state.node, level.goal)
    target = distance * 2 * game.base_consumption["高温"][0] + gamma_remaining * game.base_consumption["沙暴"][0]
    max_equal = game.capacity_kg // (game.water_weight + game.food_weight)
    targets = {target, min(max_equal, target + 40), max_equal}
    options = {(0, 0)}
    for stock in sorted(targets):
        buy_water = max(0, stock - state.water)
        buy_food = max(0, stock - state.food)
        cost_at_four = 4 * (game.water_price * buy_water + game.food_price * buy_food)
        if cost_at_four <= state.cash:
            options.add((buy_water, buy_food))
    return tuple(sorted(options))


def _candidate_actions(
    state: PlayerState,
    weather: str,
    gamma_remaining: int,
    config: RollingConfig,
) -> tuple[Action, ...]:
    options = _purchase_options(
        state, gamma_remaining, config.game, config.level
    )
    candidates = legal_actions(state, weather, config.level, options)
    feasible: list[Action] = []
    for action in candidates:
        if state.arrived:
            feasible.append(action)
            continue
        price = 4 if (action.buy_water or action.buy_food) else 0
        cash = state.cash - price * (
            config.game.water_price * action.buy_water
            + config.game.food_price * action.buy_food
        )
        water = state.water + action.buy_water
        food = state.food + action.buy_food
        if cash < 0:
            continue
        if config.game.water_weight * water + config.game.food_weight * food > config.game.capacity_kg:
            continue
        feasible.append(action)
    return tuple(feasible)


def _payoff_table(
    day: int,
    current_weather: str,
    public_states: Sequence[PlayerState],
    gamma_remaining: int,
    config: RollingConfig,
    action_sets: Sequence[Sequence[Action]],
) -> dict[tuple[Action, ...], tuple[float, ...]]:
    table: dict[tuple[Action, ...], tuple[float, ...]] = {}
    for joint in product(*action_sets):
        try:
            transition = step_joint(
                public_states, joint, current_weather, config.game, config.level
            )
        except ValueError:
            table[tuple(joint)] = tuple(-inf for _ in public_states)
            continue
        payoffs: list[float] = []
        for state in transition.states:
            if state.arrived:
                payoffs.append(terminal_wealth(state, config.game))
                continue
            continuation = robust_value(
                day + 1,
                state,
                gamma_remaining,
                config.game,
                config.level,
            )
            payoffs.append(continuation.worst_wealth if continuation.feasible else -inf)
        table[tuple(joint)] = tuple(payoffs)
    return table


def _unilateral_gains(
    joint: tuple[Action, ...],
    action_sets: Sequence[Sequence[Action]],
    payoffs: Mapping[tuple[Action, ...], tuple[float, ...]],
) -> tuple[float, ...]:
    current = payoffs[joint]
    gains: list[float] = []
    for player, alternatives in enumerate(action_sets):
        best = current[player]
        for action in alternatives:
            deviated = list(joint)
            deviated[player] = action
            best = max(best, payoffs[tuple(deviated)][player])
        gains.append(max(0.0, best - current[player]))
    return tuple(gains)


def _pure_equilibria(
    action_sets: Sequence[Sequence[Action]],
    payoffs: Mapping[tuple[Action, ...], tuple[float, ...]],
    tolerance: float,
) -> tuple[tuple[Action, ...], ...]:
    rows = []
    for joint in product(*action_sets):
        joint = tuple(joint)
        if any(value == -inf for value in payoffs[joint]):
            continue
        if max(_unilateral_gains(joint, action_sets, payoffs), default=0.0) <= tolerance:
            rows.append(joint)
    return tuple(rows)


def _mixed_equilibrium(
    action_sets: Sequence[Sequence[Action]],
    payoffs: Mapping[tuple[Action, ...], tuple[float, ...]],
    tolerance: float,
) -> tuple[tuple[tuple[float, ...], ...], tuple[float, ...], float]:
    sizes = [len(actions) for actions in action_sets]
    offsets = np.cumsum([0, *sizes])
    numeric = {
        joint: tuple(-1e12 if value == -inf else value for value in values)
        for joint, values in payoffs.items()
    }

    def split(vector):
        return [vector[offsets[i] : offsets[i + 1]] for i in range(len(sizes))]

    def action_values(probabilities, player):
        values = np.zeros(sizes[player])
        for action_index, action in enumerate(action_sets[player]):
            total = 0.0
            other_indices = [range(size) for index, size in enumerate(sizes) if index != player]
            for others in product(*other_indices):
                joint_indices = []
                cursor = 0
                probability = 1.0
                for index in range(len(sizes)):
                    if index == player:
                        joint_indices.append(action_index)
                    else:
                        selected = others[cursor]
                        cursor += 1
                        joint_indices.append(selected)
                        probability *= probabilities[index][selected]
                joint = tuple(action_sets[index][choice] for index, choice in enumerate(joint_indices))
                total += probability * numeric[joint][player]
            values[action_index] = total
        return values

    def regrets(vector):
        probabilities = split(vector)
        rows = []
        for player in range(len(sizes)):
            values = action_values(probabilities, player)
            expected = float(probabilities[player] @ values)
            rows.append(max(0.0, float(np.max(values) - expected)))
        return np.asarray(rows)

    def objective(vector):
        row = regrets(vector)
        return float(row @ row)

    initial = np.concatenate([np.full(size, 1.0 / size) for size in sizes])
    constraints = [
        {
            "type": "eq",
            "fun": lambda vector, i=i: float(np.sum(vector[offsets[i] : offsets[i + 1]]) - 1),
        }
        for i in range(len(sizes))
    ]
    result = minimize(
        objective,
        initial,
        method="SLSQP",
        bounds=[(0.0, 1.0)] * len(initial),
        constraints=constraints,
        options={"maxiter": 2000, "ftol": tolerance * tolerance},
    )
    probabilities = split(result.x)
    regret = regrets(result.x)
    epsilon = float(np.max(regret))
    if not result.success or epsilon > tolerance:
        raise RuntimeError(f"阶段博弈无纯均衡，混合均衡未通过检验：epsilon={epsilon}")
    expected = []
    for player in range(len(sizes)):
        values = action_values(probabilities, player)
        expected.append(float(probabilities[player] @ values))
    return tuple(tuple(float(x) for x in row) for row in probabilities), tuple(expected), epsilon


def choose_actions(
    day: int,
    current_weather: str,
    public_states: Sequence[PlayerState],
    gamma_remaining: int,
    config: RollingConfig,
) -> StageEquilibrium:
    if len(public_states) != config.game.player_count:
        raise ValueError("公开状态数量必须等于玩家数")
    action_sets = tuple(
        _candidate_actions(state, current_weather, gamma_remaining, config)
        for state in public_states
    )
    table = _payoff_table(
        day,
        current_weather,
        public_states,
        gamma_remaining,
        config,
        action_sets,
    )
    pure = _pure_equilibria(action_sets, table, config.tolerance)
    payoff_rows = tuple(sorted(table.items(), key=lambda item: item[0]))
    if pure:
        selected = max(
            pure,
            key=lambda joint: (
                min(table[joint]),
                sum(table[joint]),
                joint,
            ),
        )
        gains = _unilateral_gains(selected, action_sets, table)
        return StageEquilibrium(
            "pure",
            selected,
            table[selected],
            max(gains, default=0.0),
            gains,
            pure,
            (),
            action_sets,
            payoff_rows,
        )

    probabilities, expected, epsilon = _mixed_equilibrium(
        action_sets, table, config.tolerance
    )
    representative = tuple(
        actions[int(np.argmax(probability))]
        for actions, probability in zip(action_sets, probabilities)
    )
    return StageEquilibrium(
        "mixed",
        representative,
        expected,
        epsilon,
        tuple(epsilon for _ in public_states),
        (),
        probabilities,
        action_sets,
        payoff_rows,
    )
