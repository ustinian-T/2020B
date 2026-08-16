from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

import numpy as np

from .oracle_dp import solve_oracle
from .scenario_tree_milp import (
    ScenarioTreeSolution,
    simulate_tree_policy,
)
from .weather_markov import enumerate_weather_scenarios


@dataclass(frozen=True)
class ScenarioEvaluation:
    scenario: tuple[str, ...]
    success: bool
    terminal_wealth: float
    arrival_day: int
    oracle_wealth: float
    regret: float


@dataclass(frozen=True)
class LevelThreeValidationReport:
    scenario_count: int
    success_count: int
    failure_count: int
    worst_wealth: float
    mean_wealth: float
    q05_wealth: float
    minimum_regret: float
    mean_regret: float
    median_regret: float
    maximum_regret: float
    arrival_distribution: dict[int, int]
    nonanticipativity_ok: bool
    rule_check_ok: bool
    evaluations: tuple[ScenarioEvaluation, ...]


def validate_level_three(
    solution: ScenarioTreeSolution,
) -> LevelThreeValidationReport:
    scenarios = enumerate_weather_scenarios(
        solution.game.deadline, solution.weather_states
    )
    evaluations: list[ScenarioEvaluation] = []
    rule_check_ok = True
    for scenario in scenarios:
        online = simulate_tree_policy(solution, scenario)
        if not online.success or online.final_wealth is None or online.arrival_day is None:
            rule_check_ok = False
            evaluations.append(
                ScenarioEvaluation(scenario, False, float("-inf"), 0, float("nan"), float("nan"))
            )
            continue
        if any(
            record.water < 0
            or record.food < 0
            or record.cash < 0
            or record.weight > solution.game.capacity_kg
            for record in online.records
        ):
            rule_check_ok = False
        oracle = solve_oracle(solution.level, solution.game, scenario)
        regret = oracle.final_wealth - online.final_wealth
        evaluations.append(
            ScenarioEvaluation(
                scenario=scenario,
                success=True,
                terminal_wealth=online.final_wealth,
                arrival_day=online.arrival_day,
                oracle_wealth=oracle.final_wealth,
                regret=regret,
            )
        )

    successful = [item for item in evaluations if item.success]
    wealth = np.asarray([item.terminal_wealth for item in successful], dtype=float)
    regrets = np.asarray([item.regret for item in successful], dtype=float)
    actions_by_prefix: dict[tuple[str, ...], set] = {}
    for scenario in scenarios:
        online = simulate_tree_policy(solution, scenario)
        for record in online.records:
            prefix = scenario[: record.day]
            actions_by_prefix.setdefault(prefix, set()).add(
                (record.action, record.to_node, record.buy_water, record.buy_food)
            )
    nonanticipativity_ok = all(
        len(actions) == 1 for actions in actions_by_prefix.values()
    )
    return LevelThreeValidationReport(
        scenario_count=len(scenarios),
        success_count=len(successful),
        failure_count=len(scenarios) - len(successful),
        worst_wealth=float(np.min(wealth)),
        mean_wealth=float(np.mean(wealth)),
        q05_wealth=float(np.quantile(wealth, 0.05)),
        minimum_regret=float(np.min(regrets)),
        mean_regret=float(np.mean(regrets)),
        median_regret=float(np.median(regrets)),
        maximum_regret=float(np.max(regrets)),
        arrival_distribution=dict(sorted(Counter(item.arrival_day for item in successful).items())),
        nonanticipativity_ok=nonanticipativity_ok,
        rule_check_ok=rule_check_ok,
        evaluations=tuple(evaluations),
    )
