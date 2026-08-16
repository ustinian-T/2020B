from __future__ import annotations

from dataclasses import asdict, replace
from itertools import product
from typing import Iterable

from .config import GameConfig, LevelConfig
from .game_rolling import RollingConfig, rolling_simulation
from .robust_value import plan_initial_purchase
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
