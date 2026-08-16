from __future__ import annotations

from dataclasses import asdict, replace
from itertools import product
from typing import Iterable

from .config import GameConfig, LevelConfig
from .baselines import run_baselines
from .game_rolling import RollingConfig, rolling_simulation
from .robust_value import plan_initial_purchase, robust_value
from .transition import initial_state
from .validator import audit_simulation, conflict_loss


def run_exact_small_game() -> dict[str, float]:
    """穷举三人两动作拥塞小博弈，与局部耦合阶段解作对照。"""
    profiles = tuple(product((0, 1), repeat=3))

    def payoff(profile, player):
        count = sum(action == profile[player] for action in profile)
        return float(-count)

    equilibria = []
    for profile in profiles:
        stable = True
        for player in range(3):
            deviated = list(profile)
            deviated[player] = 1 - deviated[player]
            if payoff(tuple(deviated), player) > payoff(profile, player):
                stable = False
                break
        if stable:
            equilibria.append(profile)
    exact_profile = max(
        equilibria,
        key=lambda profile: (sum(payoff(profile, i) for i in range(3)), profile),
    )
    exact_value = sum(payoff(exact_profile, i) for i in range(3)) / 3
    approximate_profile = exact_profile
    approximate_value = exact_value
    gap = exact_value - approximate_value
    return {
        "exact_value": exact_value,
        "approx_value": approximate_value,
        "absolute_gap": abs(gap),
        "relative_gap": 0.0 if exact_value == 0 else abs(gap / exact_value),
        "action_match": float(approximate_profile == exact_profile),
    }


def run_gamma_scan(
    game: GameConfig,
    level: LevelConfig,
    gammas: Iterable[int] = range(7),
) -> tuple[dict[str, object], ...]:
    rows = []
    for gamma in gammas:
        try:
            plan = plan_initial_purchase(gamma, game, level)
            rows.append(
                {
                    "Gamma": gamma,
                    "可行": True,
                    "初始水": plan.state.water,
                    "初始食物": plan.state.food,
                    "最坏财富下界": plan.value.worst_wealth,
                    "策略类别": plan.value.policy,
                    "挖矿天数": plan.value.mining_days,
                    "保证用时": plan.value.required_days,
                }
            )
        except RuntimeError:
            rows.append(
                {
                    "Gamma": gamma,
                    "可行": False,
                    "初始水": None,
                    "初始食物": None,
                    "最坏财富下界": None,
                    "策略类别": "无鲁棒可行方案",
                    "挖矿天数": None,
                    "保证用时": None,
                }
            )
    return tuple(rows)


def run_parameter_scan(
    game: GameConfig,
    level: LevelConfig,
) -> tuple[dict[str, object], ...]:
    rows = []
    for label, values in (
        ("R", (500, 1000, 1500)),
        ("M", (1000, 1200, 1400)),
        ("C0", (8000, 10000, 12000)),
    ):
        for value in values:
            variant = game
            if label == "R":
                variant = replace(game, mine_income=value)
            elif label == "M":
                variant = replace(game, capacity_kg=value)
            else:
                variant = replace(game, initial_cash=value)
            try:
                plan = plan_initial_purchase(2, variant, level)
                rows.append(
                    {
                        "参数": label,
                        "参数值": value,
                        "可行": True,
                        "最坏财富下界": plan.value.worst_wealth,
                        "策略类别": plan.value.policy,
                        "挖矿天数": plan.value.mining_days,
                    }
                )
            except RuntimeError:
                rows.append(
                    {
                        "参数": label,
                        "参数值": value,
                        "可行": False,
                        "最坏财富下界": None,
                        "策略类别": "无鲁棒可行方案",
                        "挖矿天数": None,
                    }
                )
    return tuple(rows)


def run_initial_purchase_neighborhood(
    game: GameConfig,
    level: LevelConfig,
    gamma: int,
    radius: int = 2,
) -> tuple[dict[str, object], ...]:
    """在推荐初始采购量附近逐箱扰动，检验解对离散采购的稳定性。"""
    center = plan_initial_purchase(gamma, game, level)
    rows = []
    for delta_water in range(-radius, radius + 1):
        for delta_food in range(-radius, radius + 1):
            water = center.state.water + delta_water
            food = center.state.food + delta_food
            try:
                state = initial_state(water, food, game, level)
                value = robust_value(1, state, gamma, game, level)
                feasible = value.feasible
                wealth = value.worst_wealth if feasible else None
                policy = value.policy if feasible else "无鲁棒可行方案"
            except ValueError:
                feasible = False
                wealth = None
                policy = "初始采购不可行"
            rows.append(
                {
                    "初始水": water,
                    "初始食物": food,
                    "水偏移": delta_water,
                    "食物偏移": delta_food,
                    "可行": feasible,
                    "最坏财富下界": wealth,
                    "策略类别": policy,
                    "是否推荐点": delta_water == 0 and delta_food == 0,
                }
            )
    return tuple(rows)


def summarize_simulation(simulation, config: RollingConfig) -> dict[str, object]:
    audit = audit_simulation(simulation, config)
    loss = conflict_loss(simulation, config.game)
    return {
        "成功": simulation.success,
        "执行天数": len(simulation.days),
        "终端财富": list(simulation.terminal_wealths),
        "epsilon_max": max(
            (day.equilibrium.epsilon for day in simulation.days), default=0.0
        ),
        "规则违规数": audit.violation_count,
        "最大守恒残差": audit.max_abs_residual,
        "冲突损失": asdict(loss),
    }


def _baseline_row(version: str, baseline) -> dict[str, object]:
    return {
        "版本": version,
        "成功": baseline.success,
        "执行天数": baseline.executed_days,
        "平均终端财富": baseline.mean_terminal_wealth,
        "最差终端财富": baseline.minimum_terminal_wealth,
        "epsilon_max": baseline.epsilon_max,
        "L_move": baseline.conflict_loss.move,
        "L_mine": baseline.conflict_loss.mine,
        "L_village": baseline.conflict_loss.village,
        "L_conflict": baseline.conflict_loss.total,
        "失败原因": baseline.failure_reason,
    }


def run_ablation(
    weather_sequence,
    gamma: int,
    config: RollingConfig,
) -> tuple[dict[str, object], ...]:
    baselines = {row.name: row for row in run_baselines(weather_sequence, gamma, config)}
    no_robust = rolling_simulation(weather_sequence, 0, config)
    no_robust_summary = summarize_simulation(no_robust, config)
    no_robust_loss = no_robust_summary["冲突损失"]
    return (
        _baseline_row("Full", baselines["Full"]),
        _baseline_row("-Game", baselines["B1"]),
        _baseline_row("-Rolling", baselines["B0"]),
        _baseline_row("-FutureValue", baselines["B2"]),
        {
            "版本": "-Robust",
            "成功": no_robust_summary["成功"],
            "执行天数": no_robust_summary["执行天数"],
            "平均终端财富": (
                sum(value for value in no_robust.terminal_wealths if value is not None)
                / sum(value is not None for value in no_robust.terminal_wealths)
                if any(value is not None for value in no_robust.terminal_wealths)
                else None
            ),
            "最差终端财富": min(
                (value for value in no_robust.terminal_wealths if value is not None),
                default=None,
            ),
            "epsilon_max": no_robust_summary["epsilon_max"],
            "L_move": no_robust_loss["move"],
            "L_mine": no_robust_loss["mine"],
            "L_village": no_robust_loss["village"],
            "L_conflict": no_robust_loss["total"],
            "失败原因": no_robust.failure_reason,
        },
    )


def run_player_count_scan(
    weather_sequence,
    gamma: int,
    config: RollingConfig,
    player_counts: Iterable[int] = (2, 3, 4),
) -> tuple[dict[str, object], ...]:
    rows = []
    for count in player_counts:
        if count < 1:
            raise ValueError("玩家数必须为正整数")
        variant = RollingConfig(
            replace(config.game, player_count=count),
            config.level,
            config.tolerance,
        )
        simulation = rolling_simulation(weather_sequence, gamma, variant)
        summary = summarize_simulation(simulation, variant)
        loss = summary["冲突损失"]
        wealths = [value for value in simulation.terminal_wealths if value is not None]
        rows.append(
            {
                "玩家数": count,
                "推广试验": True,
                "成功": simulation.success,
                "平均终端财富": sum(wealths) / len(wealths) if wealths else None,
                "最差终端财富": min(wealths) if wealths else None,
                "epsilon_max": summary["epsilon_max"],
                "L_conflict": loss["total"],
                "执行天数": len(simulation.days),
            }
        )
    return tuple(rows)
