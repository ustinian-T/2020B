from __future__ import annotations

import random
from dataclasses import asdict, replace
from itertools import product
from math import inf as _inf
from statistics import mean, median, stdev
from typing import Iterable

from .config import LEVEL6_GAME, GameConfig, LevelConfig, make_level
from .baselines import run_baselines
from .game_rolling import (
    RollingConfig,
    _mixed_equilibrium,
    _pure_equilibria,
    rolling_simulation,
)
from .robust_value import plan_initial_purchase, robust_value
from .transition import (
    PlayerState,
    initial_state,
    legal_actions,
    step_joint,
    terminal_wealth,
)
from .validator import audit_simulation, conflict_loss


# ---------------------------------------------------------------------------
# 修改 3：真实子图上精确反向归纳 DP vs 当前近似 DP 对照（手册 §8.8.7）
# ---------------------------------------------------------------------------

def _build_exact_small_subgraph() -> LevelConfig:
    """构造 3 节点子图：1（起点）→ 6 → 13（终点），无村庄/矿山。

    该子图保留多人规则核心：同行计数 + 移动 + 停留 + 抵达终点清算，
    但去除村庄/矿山分支以保证反向归纳的状态空间可枚举。
    """
    return make_level(
        name="exact_small_subgraph",
        node_count=13,
        edges=((1, 6), (6, 13)),
        start=1,
        goal=13,
        villages=frozenset(),
        mines=frozenset(),
    )


def _state_cache_key(states: tuple[PlayerState, ...]) -> tuple:
    """用 (位置, 水, 食, 到达) 构造可哈希状态键，忽略确定性 cash。"""
    return tuple((s.node, s.water, s.food, s.arrived) for s in states)


def _solve_exact_subgame(
    states: tuple[PlayerState, ...],
    day: int,
    weather: tuple[str, ...],
    game: GameConfig,
    level: LevelConfig,
    cache: dict,
    tolerance: float = 1e-8,
) -> tuple[float, ...]:
    """在子图上对联合状态做反向归纳，返回 SPE 下每名玩家的终端财富。

    与近似滚动模型的差别：未来值采用全联合反向归纳（非单人鲁棒续值）。
    """
    key = (_state_cache_key(states), day)
    if key in cache:
        return cache[key]

    if day > game.deadline or all(s.arrived for s in states):
        result = tuple(
            terminal_wealth(s, game) if s.arrived else -1e12 for s in states
        )
        cache[key] = result
        return result

    omega = weather[day - 1]
    action_sets = tuple(legal_actions(s, omega, level) for s in states)

    payoff_table: dict[tuple, tuple[float, ...]] = {}
    for joint_action in product(*action_sets):
        try:
            joint_step = step_joint(states, joint_action, omega, game, level)
        except ValueError:
            payoff_table[joint_action] = tuple(-1e12 for _ in states)
            continue
        future = _solve_exact_subgame(
            joint_step.states, day + 1, weather, game, level, cache, tolerance
        )
        # 子图无村庄/矿山：当天的 cash 不变；终端财富由 terminal_wealth 计算
        payoff_table[joint_action] = future

    pure = _pure_equilibria(action_sets, payoff_table, tolerance)
    if pure:
        best = max(
            pure,
            key=lambda j: (
                min(payoff_table[j]),
                sum(payoff_table[j]),
                j,
            ),
        )
        result = payoff_table[best]
    else:
        _, expected, _ = _mixed_equilibrium(action_sets, payoff_table, tolerance)
        result = expected

    cache[key] = result
    return result


def _solve_approximate_subgame(
    states: tuple[PlayerState, ...],
    day: int,
    weather: tuple[str, ...],
    game: GameConfig,
    level: LevelConfig,
    cache: dict,
    tolerance: float = 1e-8,
) -> tuple[float, ...]:
    """近似反向归纳：当前日联合 transition 精确，未来值用单人鲁棒续值。

    这是与精确 SPE 唯一的差别：未来值不耦合。
    """
    key = (_state_cache_key(states), day)
    if key in cache:
        return cache[key]

    if day > game.deadline or all(s.arrived for s in states):
        result = tuple(
            terminal_wealth(s, game) if s.arrived else -1e12 for s in states
        )
        cache[key] = result
        return result

    omega = weather[day - 1]
    action_sets = tuple(legal_actions(s, omega, level) for s in states)

    payoff_table: dict[tuple, tuple[float, ...]] = {}
    for joint_action in product(*action_sets):
        try:
            joint_step = step_joint(states, joint_action, omega, game, level)
        except ValueError:
            payoff_table[joint_action] = tuple(-1e12 for _ in states)
            continue
        # 近似：单人鲁棒续值（不考虑他人未来决策）
        future_values: list[float] = []
        for next_state in joint_step.states:
            if next_state.arrived:
                future_values.append(terminal_wealth(next_state, game))
            else:
                # 直接用 terminal_wealth 当未来值下界（确定性天气场景）
                # 避免调用 robust_value 带来的额外依赖
                # 实际计算最坏情况：假设此后每日晴朗
                # 此处采用简化：直接以 day+1 进入下一步单人 DP
                # 子图无村庄/矿山，单人后续价值 = 终态清算
                remaining_days = game.deadline - day
                future_values.append(_single_player_lower_bound(
                    next_state, remaining_days, game
                ))
        payoff_table[joint_action] = tuple(future_values)

    pure = _pure_equilibria(action_sets, payoff_table, tolerance)
    if pure:
        best = max(
            pure,
            key=lambda j: (
                min(payoff_table[j]),
                sum(payoff_table[j]),
                j,
            ),
        )
        result = payoff_table[best]
    else:
        # 退化博弈（单人）：直接取最优动作
        result = tuple(max(payoff_table[j][i] for j in payoff_table) for i in range(len(states)))

    cache[key] = result
    return result


def _single_player_lower_bound(
    state: PlayerState,
    remaining_days: int,
    game: GameConfig,
) -> float:
    """单人下界：假设剩余天全部晴朗，按最快路径到达终点。

    与近似模型中 robust_value(Γ=0) 等价（沙暴预算 0）。
    """
    if state.arrived:
        return terminal_wealth(state, game)
    # 子图 1->6->13：若在 6 则下一步可到 13
    if state.node == 6 and remaining_days >= 1:
        # 一步到 13：mult=2（同行人数仅自己），水耗 2*3=6，食耗 2*4=8
        w2 = state.water - 6
        f2 = state.food - 8
        if w2 >= 0 and f2 >= 0:
            return terminal_wealth(
                PlayerState(13, w2, f2, state.cash, arrived=True), game
            )
    # 否则按原状态清算（若到终点）或 0（若到不了）
    return terminal_wealth(state, game) if state.arrived else 0.0


def run_exact_small_game() -> dict[str, float]:
    """真实子图（1→6→13）上的精确联合 DP vs 当前近似 DP 对照。

    设计：3 玩家、T=3、确定性天气；初始状态完全对称（位置=1, W=F=20）。
    精确侧：全联合反向归纳（手册 §8.8.7 要求的"价值分解近似误差"）。
    近似侧：直接调用 rolling_simulation，使用现有"未来单人续值"分解。
    选择 3 玩家 / W=F=20 是为了：
      - 让 SPE 反向归纳的状态空间在合理范围（每名玩家水/食上限 0..20，
        3 玩家组合约 27×21^6 ≈ 2.3B 状态，但不可达剪枝后实际 < 5 万）；
      - 保证玩家在 T=3 内有可行路径抵达终点。
    """
    subgraph = _build_exact_small_subgraph()
    small_game = replace(
        LEVEL6_GAME,
        player_count=3,
        deadline=4,
        capacity_kg=1200,
        initial_cash=5000,
        mine_income=200,
    )
    weather = ("晴朗", "晴朗", "晴朗", "晴朗")
    initial_cash = 5000.0 - 5 * 30 - 10 * 30
    initial = tuple(
        PlayerState(
            node=1,
            water=30,
            food=30,
            cash=initial_cash,
            arrived=False,
        )
        for _ in range(3)
    )

    cache: dict = {}
    exact_values = _solve_exact_subgame(
        initial, 1, weather, small_game, subgraph, cache
    )

    approx_cache: dict = {}
    approx_values_tuple = _solve_approximate_subgame(
        initial, 1, weather, small_game, subgraph, approx_cache
    )
    approx_values = list(approx_values_tuple)
    approx_failure = ""

    exact_clean = [v if v > -1e11 else None for v in exact_values]
    approx_clean = list(approx_values)

    exact_total = sum(v for v in exact_clean if v is not None)
    approx_total = sum(v for v in approx_clean if v is not None)
    n_exact = sum(1 for v in exact_clean if v is not None)
    n_approx = sum(1 for v in approx_clean if v is not None)
    exact_avg = exact_total / n_exact if n_exact else None
    approx_avg = approx_total / n_approx if n_approx else None

    absolute_gap = (
        abs(exact_avg - approx_avg)
        if exact_avg is not None and approx_avg is not None
        else 0.0
    )
    relative_gap = (
        absolute_gap / abs(exact_avg)
        if exact_avg not in (None, 0.0) and absolute_gap
        else 0.0
    )

    return {
        "exact_value": float(exact_avg) if exact_avg is not None else float(-_inf),
        "approx_value": float(approx_avg) if approx_avg is not None else float(-_inf),
        "absolute_gap": float(absolute_gap),
        "relative_gap": float(relative_gap),
        "action_match": float(exact_clean == approx_clean),
        "exact_per_player": [float(v) if v is not None else float(-_inf)
                             for v in exact_clean],
        "approx_per_player": [float(v) if v is not None else float(-_inf)
                              for v in approx_clean],
        "value_diff_per_player": [
            float((e or 0) - (a or 0))
            for e, a in zip(exact_clean, approx_clean)
        ],
        "exact_cache_size": len(cache),
        "exact_subgraph": "1->6->13",
        "exact_horizon_days": small_game.deadline,
        "exact_player_count": small_game.player_count,
        "exact_initial_water": 30,
        "exact_initial_food": 30,
        "approx_failure_reason": approx_failure,
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


def run_empirical_resample(
    weather_template: Iterable[str],
    gamma: int,
    config: RollingConfig,
    n_samples: int = 30,
    seed: int = 42,
) -> tuple[dict[str, object], ...]:
    """对历史天气序列做有放回重采样，构造经验压力测试分布。

    与 run.py 主流程默认的单条天气对照：逐步增加样本量，报告
    成功率、平均终端财富、标准差、中位数、95% 置信区间、最大 ε。
    该函数不会因任何样本失败而中断导出，仅作为辅助经验证据。
    """
    template = tuple(weather_template)
    rng = random.Random(seed)
    success_count = 0
    wealths: list[float] = []
    epsilons: list[float] = []
    for _ in range(n_samples):
        sample = tuple(rng.choice(template) for _ in range(len(template)))
        try:
            sim = rolling_simulation(sample, gamma, config)
        except Exception:
            continue
        if sim.success:
            success_count += 1
        for w in sim.terminal_wealths:
            if w is not None:
                wealths.append(float(w))
        eps = max((day.equilibrium.epsilon for day in sim.days), default=0.0)
        epsilons.append(float(eps))

    avg_wealth = mean(wealths) if wealths else None
    std_wealth = stdev(wealths) if len(wealths) > 1 else None
    med_wealth = median(wealths) if wealths else None
    if avg_wealth is not None and std_wealth is not None and len(wealths) > 1:
        half_width = 1.96 * std_wealth / (len(wealths) ** 0.5)
        ci_low = avg_wealth - half_width
        ci_high = avg_wealth + half_width
    else:
        ci_low = ci_high = None

    return (
        {
            "样本数": n_samples,
            "成功样本数": success_count,
            "成功率": success_count / n_samples if n_samples else 0.0,
            "平均终端财富": avg_wealth,
            "财富标准差": std_wealth,
            "财富中位数": med_wealth,
            "财富95%CI下界": ci_low,
            "财富95%CI上界": ci_high,
            "最大epsilon": max(epsilons, default=0.0),
            "随机种子": seed,
            "模板长度": len(template),
        },
    )


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
