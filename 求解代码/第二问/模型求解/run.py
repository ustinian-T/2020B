from __future__ import annotations

import csv
from dataclasses import asdict
from pathlib import Path

from .config import LEVEL_FOUR_GAME, LEVEL_THREE_GAME, build_level_four, build_level_three
from .export_results import (
    validation_summary,
    write_daily_records,
    write_json,
    write_policy_tree,
    write_scenario_evaluations,
)
from .robust_dp_q4 import scan_safe_baselines, simulate_safe_baseline
from .scenario_tree_milp import simulate_tree_policy, solve_scenario_tree
from .validate_q2 import validate_level_three
from .validate_q4 import (
    build_first_question_fixed_plan,
    evaluate_strategies,
    gamma_sensitivity,
    generate_markov_weather,
    storm_probability_sensitivity,
    write_rows,
)


QUESTION_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = QUESTION_ROOT / "结果输出"
VALIDATION_DIR = QUESTION_ROOT / "结果验证"


def _write_q4_baselines(path: Path, plans) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        fieldnames = [
            "Gamma", "最短移动步数", "最迟保证到达日", "初购水", "初购食物",
            "初购后现金", "保证财富下界", "最短路径", "结果性质",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for plan in plans:
            writer.writerow(
                {
                    "Gamma": plan.gamma,
                    "最短移动步数": plan.shortest_steps,
                    "最迟保证到达日": plan.shortest_steps + plan.gamma,
                    "初购水": plan.initial_state.water,
                    "初购食物": plan.initial_state.food,
                    "初购后现金": plan.initial_state.cash,
                    "保证财富下界": plan.guaranteed_wealth,
                    "最短路径": "-".join(map(str, plan.path)),
                    "结果性质": plan.model_role,
                }
            )


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    VALIDATION_DIR.mkdir(parents=True, exist_ok=True)

    level_three = build_level_three()
    q3 = solve_scenario_tree(
        level_three, LEVEL_THREE_GAME, time_limit_seconds=300, disp=False
    )
    if not q3.optimal or q3.statistics["mip_gap"] != 0:
        raise RuntimeError(f"第三关未取得全局最优：{q3.status}, {q3.statistics}")
    q3_validation = validate_level_three(q3)
    if (
        q3_validation.failure_count
        or not q3_validation.nonanticipativity_ok
        or not q3_validation.rule_check_ok
        or abs(q3_validation.worst_wealth - q3.robust_value) > 1e-7
        or q3_validation.minimum_regret < -1e-7
    ):
        raise RuntimeError(f"第三关模型检验失败：{validation_summary(q3_validation)}")

    write_scenario_evaluations(OUTPUT_DIR / "第三关1024全情景检验.csv", q3_validation)
    write_policy_tree(OUTPUT_DIR / "第三关在线策略树.csv", q3)
    worst = min(
        q3_validation.evaluations,
        key=lambda item: (item.terminal_wealth, -item.regret, item.scenario),
    )
    worst_simulation = simulate_tree_policy(q3, worst.scenario)
    write_daily_records(
        OUTPUT_DIR / "第三关最坏情景逐日策略.csv",
        q3.initial_state,
        worst_simulation.records,
    )

    level_four = build_level_four()
    q4_plans = scan_safe_baselines(level_four, LEVEL_FOUR_GAME)
    for plan in q4_plans:
        pressure_weather = (
            ("沙暴",) * plan.gamma
            + ("高温",) * plan.shortest_steps
            + ("晴朗",) * (LEVEL_FOUR_GAME.deadline - plan.gamma - plan.shortest_steps)
        )
        check = simulate_safe_baseline(plan, pressure_weather)
        if (
            not check.success
            or check.arrival_day != plan.gamma + plan.shortest_steps
            or check.final_wealth != plan.guaranteed_wealth
        ):
            raise RuntimeError(f"第四关 Gamma={plan.gamma} 安全下界压力检验失败")
    _write_q4_baselines(OUTPUT_DIR / "第四关Gamma安全下界.csv", q4_plans)

    monte_carlo_trials = 10_000
    monte_carlo_seed = 20200816
    robust_plan = q4_plans[6]
    first_question_plan = build_first_question_fixed_plan(level_four, LEVEL_FOUR_GAME)
    nominal_plan = q4_plans[2]
    q4_scenarios = generate_markov_weather(
        monte_carlo_trials, LEVEL_FOUR_GAME.deadline, monte_carlo_seed
    )
    q4_metrics, q4_trials = evaluate_strategies(
        {
            "第二问鲁棒决策模型(Gamma=6)": robust_plan,
            "第一问已知天气固定方案": first_question_plan,
            "低保护简单方案(Gamma=2)": nominal_plan,
        },
        q4_scenarios,
    )
    gamma_rows = gamma_sensitivity(level_four, LEVEL_FOUR_GAME, q4_scenarios)
    storm_rows = storm_probability_sensitivity(
        robust_plan, trials=5_000, seed=monte_carlo_seed + 100
    )
    write_rows(OUTPUT_DIR / "第四关蒙特卡洛指标对比.csv", q4_metrics)
    write_rows(OUTPUT_DIR / "第四关蒙特卡洛逐情景结果.csv", q4_trials)
    write_rows(OUTPUT_DIR / "第四关Gamma灵敏性分析.csv", gamma_rows)
    write_rows(OUTPUT_DIR / "第四关沙暴概率灵敏性分析.csv", storm_rows)

    robust_metrics, q1_metrics, nominal_metrics = q4_metrics
    if robust_metrics.success_rate + 1e-12 < max(
        q1_metrics.success_rate, nominal_metrics.success_rate
    ):
        raise RuntimeError("第四关鲁棒模型成功率未超过对照策略")

    validation_payload = {
        "第三关": validation_summary(q3_validation),
        "第四关": {
            "检验性质": "压力情景、Monte Carlo样本外检验、第一问固定决策对比及灵敏性分析",
            "Gamma检验范围": [plan.gamma for plan in q4_plans],
            "全部压力情景通过": True,
            "压力情景构造": "Gamma个沙暴前置，随后全部高温完成最短路移动",
            "Monte Carlo设置": {
                "样本数": monte_carlo_trials,
                "随机种子": monte_carlo_seed,
                "天气生成": "由第一问30天天气估计的一阶Markov链",
            },
            "策略指标": [asdict(item) for item in q4_metrics],
            "Gamma灵敏性": list(gamma_rows),
            "沙暴概率灵敏性": list(storm_rows),
        },
    }
    write_json(VALIDATION_DIR / "模型检验摘要.json", validation_payload)

    summary = {
        "建模信息结构": "第t日行动仅依赖截至第t日的天气历史和当前状态",
        "第三关": {
            "模型": "自适应鲁棒DP的非前视天气情景树MILP等价展开",
            "初始采购": asdict(q3.initial_state),
            "最坏终端财富": q3.robust_value,
            "名义Markov期望财富": q3.nominal_value,
            "求解状态": q3.status,
            "全局最优": q3.optimal,
            "运行时间秒": q3.runtime_seconds,
            "统计": q3.statistics,
            "全情景检验": validation_summary(q3_validation),
            "最坏情景": "".join({"晴朗": "S", "高温": "H"}[w] for w in worst.scenario),
        },
        "第四关": {
            "当前实现": "Gamma预算鲁棒安全策略、Monte Carlo样本外检验、对照实验与灵敏性分析",
            "重要边界": "当前策略为可证明安全下界；Monte Carlo验证统计优势，不替代全局最优性证明",
            "Monte Carlo指标": [asdict(item) for item in q4_metrics],
            "与第一问对比结论": (
                f"鲁棒方案成功率{robust_metrics.success_rate:.2%}，"
                f"第一问固定方案成功率{q1_metrics.success_rate:.2%}；"
                "前者以一定保守成本换取未知天气下更高可行性"
            ),
            "Gamma安全下界": [
                {
                    "Gamma": plan.gamma,
                    "初购水": plan.initial_state.water,
                    "初购食物": plan.initial_state.food,
                    "保证财富下界": plan.guaranteed_wealth,
                    "最迟保证到达日": plan.shortest_steps + plan.gamma,
                }
                for plan in q4_plans
            ],
        },
    }
    write_json(OUTPUT_DIR / "求解摘要.json", summary)
    print(
        f"第三关：初购水/食物={q3.initial_state.water}/{q3.initial_state.food}，"
        f"最坏财富={q3.robust_value:.0f}，1024情景失败={q3_validation.failure_count}，"
        f"MIP gap={q3.statistics['mip_gap']}"
    )
    print(
        "第四关Monte Carlo："
        f"鲁棒方案成功率={robust_metrics.success_rate:.2%}，"
        f"第一问固定方案={q1_metrics.success_rate:.2%}，"
        f"低保护方案={nominal_metrics.success_rate:.2%}，"
        f"鲁棒方案平均财富={robust_metrics.mean_wealth:.2f}"
    )


if __name__ == "__main__":
    main()
