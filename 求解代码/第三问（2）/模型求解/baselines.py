from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from itertools import product
from math import inf
from statistics import mean
from typing import Callable, Sequence

from .game_rolling import (
    RollingConfig,
    RollingDay,
    RollingSimulation,
    StageEquilibrium,
    rolling_simulation,
)
from .robust_value import plan_initial_purchase, robust_value
from .transition import Action, PlayerState, legal_actions, step_joint, terminal_wealth
from .validator import ConflictLoss, conflict_loss


@dataclass(frozen=True)
class BaselineResult:
    name: str
    definition: str
    weather_days: int
    success: bool
    executed_days: int
    mean_terminal_wealth: float | None
    minimum_terminal_wealth: float | None
    epsilon_max: float | None
    conflict_loss: ConflictLoss
    failure_reason: str
    simulation: RollingSimulation


def _shortest_next(config: RollingConfig, start: int) -> int:
    if start == config.level.goal:
        return start
    parent = {start: None}
    queue = deque([start])
    while queue:
        node = queue.popleft()
        for neighbor in sorted(config.level.neighbors[node]):
            if neighbor in parent:
                continue
            parent[neighbor] = node
            if neighbor == config.level.goal:
                queue.clear()
                break
            queue.append(neighbor)
    node = config.level.goal
    path = [node]
    while parent[node] is not None:
        node = int(parent[node])
        path.append(node)
    path.reverse()
    return path[1]


Policy = Callable[[int, str, tuple[PlayerState, ...], int], tuple[tuple[Action, ...], float]]


def _simulate_policy(
    name: str,
    weather_sequence: Sequence[str],
    gamma: int,
    config: RollingConfig,
    policy: Policy,
) -> RollingSimulation:
    initial = plan_initial_purchase(gamma, config.game, config.level).state
    states = tuple(initial for _ in range(config.game.player_count))
    original = states
    days: list[RollingDay] = []
    storms_seen = 0
    failure = ""
    for day, weather in enumerate(weather_sequence, start=1):
        if day > config.game.deadline or all(state.arrived for state in states):
            break
        if weather == "沙暴":
            storms_seen += 1
        remaining = max(0, gamma - storms_seen)
        actions, epsilon = policy(day, weather, states, remaining)
        try:
            transition = step_joint(states, actions, weather, config.game, config.level)
        except ValueError as exc:
            failure = f"第{day}天：{exc}"
            break
        payoffs = tuple(
            terminal_wealth(state, config.game)
            if state.arrived
            else state.cash
            + 0.5 * config.game.water_price * state.water
            + 0.5 * config.game.food_price * state.food
            for state in transition.states
        )
        equilibrium = StageEquilibrium(
            kind=name,
            actions=actions,
            payoffs=payoffs,
            epsilon=epsilon,
            player_gains=tuple(epsilon for _ in states),
            pure_equilibria=(),
            mixed_probabilities=(),
            action_sets=(),
            payoff_rows=(),
        )
        days.append(
            RollingDay(
                day,
                weather,
                states,
                actions,
                transition.states,
                equilibrium,
                tuple(sorted(transition.edge_counts.items())),
                tuple(sorted(transition.mine_counts.items())),
                tuple(sorted(transition.village_counts.items())),
                transition.multipliers,
                transition.water_consumption,
                transition.food_consumption,
                transition.purchase_cost,
                transition.mine_income,
            )
        )
        states = transition.states
    success = all(state.arrived for state in states)
    if not success and not failure and len(weather_sequence) >= config.game.deadline:
        failure = "截止日前未全部到达终点"
    return RollingSimulation(
        gamma,
        original,
        tuple(days),
        states,
        success,
        tuple(terminal_wealth(state, config.game) if state.arrived else None for state in states),
        failure,
    )


def _b0_policy(config: RollingConfig) -> Policy:
    def policy(day, weather, states, gamma_remaining):
        actions = []
        for state in states:
            if state.arrived:
                actions.append(Action.exit())
            elif weather == "沙暴":
                actions.append(Action.stay())
            else:
                actions.append(Action.move(_shortest_next(config, state.node)))
        return tuple(actions), 0.0

    return policy


def _b1_policy(config: RollingConfig) -> Policy:
    def policy(day, weather, states, gamma_remaining):
        actions = []
        for state in states:
            if state.arrived:
                actions.append(Action.exit())
                continue
            continuation = robust_value(
                day, state, gamma_remaining, config.game, config.level
            )
            if weather == "沙暴":
                actions.append(Action.stay())
            elif state.node in config.level.mines and continuation.mining_days > 0:
                actions.append(Action.mine())
            elif len(continuation.path) >= 2:
                actions.append(Action.move(continuation.path[1]))
            else:
                actions.append(Action.stay())
        return tuple(actions), 0.0

    return policy


def _b2_policy(config: RollingConfig) -> Policy:
    def policy(day, weather, states, gamma_remaining):
        action_sets = tuple(
            legal_actions(state, weather, config.level) for state in states
        )
        table = {}
        for joint in product(*action_sets):
            try:
                transition = step_joint(
                    states, joint, weather, config.game, config.level
                )
            except ValueError:
                table[tuple(joint)] = tuple(-inf for _ in states)
                continue
            table[tuple(joint)] = tuple(
                state.cash
                + 0.5 * config.game.water_price * state.water
                + 0.5 * config.game.food_price * state.food
                for state in transition.states
            )
        pure = []
        for joint, values in table.items():
            if any(value == -inf for value in values):
                continue
            stable = True
            for player, alternatives in enumerate(action_sets):
                for action in alternatives:
                    deviated = list(joint)
                    deviated[player] = action
                    if table[tuple(deviated)][player] > values[player] + 1e-8:
                        stable = False
                        break
                if not stable:
                    break
            if stable:
                pure.append(joint)
        if pure:
            selected = max(
                pure, key=lambda joint: (min(table[joint]), sum(table[joint]), joint)
            )
            return selected, 0.0
        selected = max(
            table,
            key=lambda joint: (min(table[joint]), sum(table[joint]), joint),
        )
        values = table[selected]
        epsilon = 0.0
        for player, alternatives in enumerate(action_sets):
            best = values[player]
            for action in alternatives:
                deviated = list(selected)
                deviated[player] = action
                best = max(best, table[tuple(deviated)][player])
            epsilon = max(epsilon, best - values[player])
        return selected, epsilon

    return policy


def _result(
    name: str,
    definition: str,
    weather_days: int,
    simulation: RollingSimulation,
    config: RollingConfig,
    epsilon_is_meaningful: bool,
) -> BaselineResult:
    wealths = [value for value in simulation.terminal_wealths if value is not None]
    epsilon = (
        max((day.equilibrium.epsilon for day in simulation.days), default=0.0)
        if epsilon_is_meaningful
        else None
    )
    return BaselineResult(
        name,
        definition,
        weather_days,
        simulation.success,
        len(simulation.days),
        mean(wealths) if wealths else None,
        min(wealths) if wealths else None,
        epsilon,
        conflict_loss(simulation, config.game),
        simulation.failure_reason,
        simulation,
    )


def run_baselines(
    weather_sequence: Sequence[str],
    gamma: int,
    config: RollingConfig,
) -> tuple[BaselineResult, ...]:
    weather = tuple(weather_sequence)
    b0 = _simulate_policy("B0", weather, gamma, config, _b0_policy(config))
    b1 = _simulate_policy("B1", weather, gamma, config, _b1_policy(config))
    b2 = _simulate_policy("B2", weather, gamma, config, _b2_policy(config))
    full = rolling_simulation(weather, gamma, config)
    return (
        _result("B0", "最短可行路，不主动挖矿或博弈避让", len(weather), b0, config, False),
        _result("B1", "独立单人鲁棒续值，忽略竞争后联合执行", len(weather), b1, config, False),
        _result("B2", "只使用当天即时价值的短视阶段博弈", len(weather), b2, config, True),
        _result("Full", "当前耦合精确、Gamma鲁棒续值、阶段Nash、每日滚动", len(weather), full, config, True),
    )
