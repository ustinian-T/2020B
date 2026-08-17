from __future__ import annotations

import csv
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import numpy as np

from .config import GameConfig, LevelConfig
from .robust_dp_q4 import (
    HighSafetyPlan,
    SafeBaselinePlan,
    build_safe_baseline,
    simulate_high_safety,
    simulate_safe_baseline,
)
from .transition import initial_state
from .weather_markov import (
    HISTORICAL_WEATHER,
    WEATHER_STATES,
    empirical_initial_probabilities,
    nominal_transition_probabilities,
)


@dataclass(frozen=True)
class StrategyMetrics:
    strategy: str
    trials: int
    success_count: int
    success_rate: float
    mean_wealth: float
    minimum_wealth: float
    q05_wealth: float
    mean_arrival_day: float
    mean_regret: float
    maximum_regret: float


@dataclass(frozen=True)
class TrialResult:
    trial: int
    strategy: str
    weather: str
    storm_count_before_arrival: int
    success: bool
    arrival_day: int | None
    final_wealth: float | None
    oracle_wealth: float | None
    regret: float | None


def _scaled_weather_model(storm_factor: float) -> tuple[np.ndarray, np.ndarray]:
    if storm_factor <= 0:
        raise ValueError("沙暴概率倍率必须为正")
    states, transition = nominal_transition_probabilities()
    initial_map = empirical_initial_probabilities(HISTORICAL_WEATHER, states)
    initial = np.asarray([initial_map[state] for state in states], dtype=float)
    storm_index = states.index("沙暴")
    transition[:, storm_index] *= storm_factor
    transition /= transition.sum(axis=1, keepdims=True)
    initial[storm_index] *= storm_factor
    initial /= initial.sum()
    return initial, transition


def generate_markov_weather(
    trials: int,
    days: int,
    seed: int,
    storm_factor: float = 1.0,
) -> tuple[tuple[str, ...], ...]:
    if trials <= 0 or days <= 0:
        raise ValueError("模拟次数和天数必须为正")
    initial, transition = _scaled_weather_model(storm_factor)
    rng = np.random.default_rng(seed)
    scenarios: list[tuple[str, ...]] = []
    for _ in range(trials):
        state_index = int(rng.choice(len(WEATHER_STATES), p=initial))
        sequence = [WEATHER_STATES[state_index]]
        for _day in range(1, days):
            state_index = int(rng.choice(len(WEATHER_STATES), p=transition[state_index]))
            sequence.append(WEATHER_STATES[state_index])
        scenarios.append(tuple(sequence))
    return tuple(scenarios)


def _requirements_until_goal(
    sequence: Sequence[str], steps: int, game: GameConfig
) -> tuple[int, int, int, int] | None:
    water = food = moves = storms = 0
    for day, weather in enumerate(sequence, start=1):
        base_water, base_food = game.base_consumption[weather]
        if weather == "沙暴":
            water += base_water
            food += base_food
            storms += 1
        else:
            water += 2 * base_water
            food += 2 * base_food
            moves += 1
            if moves == steps:
                return water, food, day, storms
    return None


def build_first_question_fixed_plan(
    level: LevelConfig, game: GameConfig
) -> SafeBaselinePlan:
    template = build_safe_baseline(level, game, gamma=0)
    requirement = _requirements_until_goal(
        HISTORICAL_WEATHER, template.shortest_steps, game
    )
    if requirement is None:
        raise RuntimeError("第一问历史天气下无法完成最短路径")
    water, food, _arrival, _storms = requirement
    state = initial_state(game, level, water, food)
    return replace(
        template,
        gamma=game.deadline,
        initial_state=state,
        guaranteed_wealth=float(state.cash),
        model_role="第一问已知历史天气下确定的固定采购方案",
    )


def _oracle_wealth(
    sequence: Sequence[str], steps: int, game: GameConfig
) -> tuple[float, int, int] | None:
    requirement = _requirements_until_goal(sequence, steps, game)
    if requirement is None:
        return None
    water, food, arrival, storms = requirement
    if game.water_weight * water + game.food_weight * food > game.capacity_kg:
        return None
    wealth = game.initial_cash - game.water_price * water - game.food_price * food
    if wealth < 0:
        return None
    return float(wealth), arrival, storms


def _simulate_plan(plan, scenario):
    """根据 plan 类型路由到对应的仿真函数。"""
    if isinstance(plan, HighSafetyPlan):
        return simulate_high_safety(plan, scenario)
    return simulate_safe_baseline(plan, scenario)


def evaluate_strategies(
    plans: Mapping[str, object],
    scenarios: Sequence[tuple[str, ...]],
) -> tuple[tuple[StrategyMetrics, ...], tuple[TrialResult, ...]]:
    if not plans:
        raise ValueError("至少需要一个待检验策略")
    first_plan = next(iter(plans.values()))
    trials: list[TrialResult] = []
    metric_rows: list[StrategyMetrics] = []
    for strategy, plan in plans.items():
        successes: list[tuple[float, int, float]] = []
        for number, scenario in enumerate(scenarios, start=1):
            oracle = _oracle_wealth(scenario, plan.shortest_steps, plan.game)
            simulation = _simulate_plan(plan, scenario)
            oracle_wealth = oracle[0] if oracle else None
            storm_count = oracle[2] if oracle else scenario.count("沙暴")
            regret = (
                oracle_wealth - simulation.final_wealth
                if simulation.success and oracle_wealth is not None and simulation.final_wealth is not None
                else None
            )
            if simulation.success and simulation.final_wealth is not None and regret is not None:
                successes.append((simulation.final_wealth, simulation.arrival_day or 0, regret))
            trials.append(
                TrialResult(
                    trial=number,
                    strategy=strategy,
                    weather="".join({"晴朗": "S", "高温": "H", "沙暴": "X"}[w] for w in scenario),
                    storm_count_before_arrival=storm_count,
                    success=simulation.success,
                    arrival_day=simulation.arrival_day,
                    final_wealth=simulation.final_wealth,
                    oracle_wealth=oracle_wealth,
                    regret=regret,
                )
            )
        wealth = np.asarray([item[0] for item in successes], dtype=float)
        arrivals = np.asarray([item[1] for item in successes], dtype=float)
        regrets = np.asarray([item[2] for item in successes], dtype=float)
        success_count = len(successes)
        metric_rows.append(
            StrategyMetrics(
                strategy=strategy,
                trials=len(scenarios),
                success_count=success_count,
                success_rate=success_count / len(scenarios),
                mean_wealth=float(np.mean(wealth)) if success_count else 0.0,
                minimum_wealth=float(np.min(wealth)) if success_count else 0.0,
                q05_wealth=float(np.quantile(wealth, 0.05)) if success_count else 0.0,
                mean_arrival_day=float(np.mean(arrivals)) if success_count else 0.0,
                mean_regret=float(np.mean(regrets)) if success_count else 0.0,
                maximum_regret=float(np.max(regrets)) if success_count else 0.0,
            )
        )
    if any(plan.level != first_plan.level or plan.game != first_plan.game for plan in plans.values()):
        raise ValueError("对比策略必须使用相同关卡与参数")
    return tuple(metric_rows), tuple(trials)


def gamma_sensitivity(
    level: LevelConfig,
    game: GameConfig,
    scenarios: Sequence[tuple[str, ...]],
    gammas: Iterable[int] = range(0, 10),
) -> tuple[dict, ...]:
    rows = []
    for gamma in gammas:
        plan = build_safe_baseline(level, game, gamma)
        metrics, _ = evaluate_strategies({f"Gamma={gamma}": plan}, scenarios)
        item = metrics[0]
        rows.append(
            {
                "Gamma": gamma,
                "初购水": plan.initial_state.water,
                "初购食物": plan.initial_state.food,
                "初购后现金": plan.initial_state.cash,
                "成功率": item.success_rate,
                "成功样本平均财富": item.mean_wealth,
                "5%分位财富": item.q05_wealth,
                "平均Regret": item.mean_regret,
            }
        )
    return tuple(rows)


def storm_probability_sensitivity(
    plan: SafeBaselinePlan,
    trials: int,
    seed: int,
    factors: Iterable[float] = (0.7, 0.85, 1.0, 1.15, 1.3),
) -> tuple[dict, ...]:
    rows = []
    for index, factor in enumerate(factors):
        scenarios = generate_markov_weather(
            trials, plan.game.deadline, seed + index, factor
        )
        metrics, _ = evaluate_strategies({"鲁棒决策模型": plan}, scenarios)
        item = metrics[0]
        rows.append(
            {
                "沙暴概率倍率": factor,
                "成功率": item.success_rate,
                "成功样本平均财富": item.mean_wealth,
                "5%分位财富": item.q05_wealth,
                "平均到达日": item.mean_arrival_day,
                "平均Regret": item.mean_regret,
            }
        )
    return tuple(rows)


def write_rows(path: Path, rows: Iterable[object]) -> None:
    materialized = list(rows)
    if not materialized:
        raise ValueError("没有可写出的数据")
    normalized = [item.__dict__ if hasattr(item, "__dict__") else item for item in materialized]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(normalized[0].keys()))
        writer.writeheader()
        writer.writerows(normalized)


# ─────────────────────────────────────────────────────────────────────────────
# 参数灵敏度（手册 §8.4）
# 扫描 M (容量), C₀ (初始资金), R (挖矿收益), T (截止日)
# ─────────────────────────────────────────────────────────────────────────────


CAPACITY_SWEEP = (1080, 1140, 1260, 1320)
INITIAL_CASH_SWEEP = (9000, 9500, 10500, 11000)
MINE_INCOME_SWEEP = (900, 950, 1050, 1100)
DEADLINE_SWEEP = (28, 29, 31, 32)


def parameter_sensitivity(
    level: LevelConfig,
    base_game: GameConfig,
    scenarios: Sequence[tuple[str, ...]],
    gamma: int = 6,
) -> tuple[dict, ...]:
    """对手册 §8.4 列出的关键参数做局部扰动灵敏度分析。

    对每个扰动值，重新构造对应 GameConfig + 安全下界，
    在同一 Monte Carlo 测试集上评估成功率与财富分布。

    返回 dict 列表（含参数名、参数值、初购、成功率、平均财富、5%分位、平均 Regret）。
    """
    rows: list[dict] = []
    for capacity in CAPACITY_SWEEP:
        game = replace(base_game, capacity_kg=capacity)
        plan = build_safe_baseline(level, game, gamma)
        metrics, _ = evaluate_strategies({f"M={capacity}": plan}, scenarios)
        item = metrics[0]
        rows.append(
            {
                "参数": "负重M",
                "参数值": capacity,
                "初购水": plan.initial_state.water,
                "初购食物": plan.initial_state.food,
                "初购后现金": plan.initial_state.cash,
                "成功率": item.success_rate,
                "成功样本平均财富": item.mean_wealth,
                "5%分位财富": item.q05_wealth,
                "平均Regret": item.mean_regret,
            }
        )
    for cash in INITIAL_CASH_SWEEP:
        game = replace(base_game, initial_cash=cash)
        plan = build_safe_baseline(level, game, gamma)
        metrics, _ = evaluate_strategies({f"C0={cash}": plan}, scenarios)
        item = metrics[0]
        rows.append(
            {
                "参数": "初始资金C0",
                "参数值": cash,
                "初购水": plan.initial_state.water,
                "初购食物": plan.initial_state.food,
                "初购后现金": plan.initial_state.cash,
                "成功率": item.success_rate,
                "成功样本平均财富": item.mean_wealth,
                "5%分位财富": item.q05_wealth,
                "平均Regret": item.mean_regret,
            }
        )
    for income in MINE_INCOME_SWEEP:
        game = replace(base_game, mine_income=income)
        plan = build_safe_baseline(level, game, gamma)
        metrics, _ = evaluate_strategies({f"R={income}": plan}, scenarios)
        item = metrics[0]
        rows.append(
            {
                "参数": "挖矿收益R",
                "参数值": income,
                "初购水": plan.initial_state.water,
                "初购食物": plan.initial_state.food,
                "初购后现金": plan.initial_state.cash,
                "成功率": item.success_rate,
                "成功样本平均财富": item.mean_wealth,
                "5%分位财富": item.q05_wealth,
                "平均Regret": item.mean_regret,
            }
        )
    for deadline in DEADLINE_SWEEP:
        # 重新生成匹配新截止日长度的 Monte Carlo 场景
        new_scenarios = generate_markov_weather(
            len(scenarios), deadline, 20200816,
        )
        game = replace(base_game, deadline=deadline)
        plan = build_safe_baseline(level, game, gamma)
        metrics, _ = evaluate_strategies({f"T={deadline}": plan}, new_scenarios)
        item = metrics[0]
        rows.append(
            {
                "参数": "截止日T",
                "参数值": deadline,
                "初购水": plan.initial_state.water,
                "初购食物": plan.initial_state.food,
                "初购后现金": plan.initial_state.cash,
                "成功率": item.success_rate,
                "成功样本平均财富": item.mean_wealth,
                "5%分位财富": item.q05_wealth,
                "平均Regret": item.mean_regret,
            }
        )
    return tuple(rows)


# ─────────────────────────────────────────────────────────────────────────────
# 策略稳定区识别（手册 §6.3 第 3 条）
# 识别连续 Γ 区间内"初购 + 关键动作完全相同"的稳定段
# ─────────────────────────────────────────────────────────────────────────────


def strategy_stability_region(
    q4_plans: Sequence[SafeBaselinePlan],
) -> tuple[dict, ...]:
    """对安全下界方案（按 Γ 排序）做稳定区识别。

    判定准则：
    - 相邻 Γ 的初始采购 (water, food, cash) 完全相同
    - 最短路径（隐含决策规则）完全相同

    返回 dict 列表，每个 dict 对应一个稳定区间：
    - Γ_min / Γ_max: 区间端点
    - 区间长度: Γ_max - Γ_min + 1
    - 初购水/食物/现金
    - 最短路径
    """
    if not q4_plans:
        return ()
    sorted_plans = sorted(q4_plans, key=lambda p: p.gamma)
    rows: list[dict] = []
    cur_start = sorted_plans[0]
    cur_end = sorted_plans[0]
    for plan in sorted_plans[1:]:
        same_purchase = (
            plan.initial_state.water == cur_start.initial_state.water
            and plan.initial_state.food == cur_start.initial_state.food
            and plan.initial_state.cash == cur_start.initial_state.cash
        )
        same_path = plan.path == cur_start.path
        if same_purchase and same_path:
            cur_end = plan
        else:
            rows.append(_stability_row(cur_start, cur_end))
            cur_start = plan
            cur_end = plan
    rows.append(_stability_row(cur_start, cur_end))
    return tuple(rows)


def _stability_row(start: SafeBaselinePlan, end: SafeBaselinePlan) -> dict:
    return {
        "Γ_min": start.gamma,
        "Γ_max": end.gamma,
        "区间长度": end.gamma - start.gamma + 1,
        "初购水": start.initial_state.water,
        "初购食物": start.initial_state.food,
        "初购后现金": start.initial_state.cash,
        "保证财富下界": start.guaranteed_wealth,
        "最迟保证到达日": end.shortest_steps + end.gamma,
        "最短路径": "-".join(map(str, start.path)),
        "策略性质": "稳定区",
    }
