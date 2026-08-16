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

    validation_payload = {
        "第三关": validation_summary(q3_validation),
        "第四关": {
            "检验性质": "预算语义与最短路安全下界压力检验，不代表全局最优性检验",
            "Gamma检验范围": [plan.gamma for plan in q4_plans],
            "全部压力情景通过": True,
            "压力情景构造": "Gamma个沙暴前置，随后全部高温完成最短路移动",
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
            "当前实现": "Gamma=0...6预算接口、完整5x5地图与可证明安全策略下界",
            "重要边界": "第四关CSV是保底可行下界，不宣称为含村庄/矿山收益的全局最优鲁棒前沿",
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
    print("第四关：Gamma=0...6 安全下界及压力检验已输出（非全局最优前沿）")


if __name__ == "__main__":
    main()
