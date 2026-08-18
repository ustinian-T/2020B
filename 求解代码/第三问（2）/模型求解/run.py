from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from statistics import mean
from typing import Sequence

from .baselines import run_baselines
from .data_loader import load_level6
from .export import write_csv, write_json
from .game_rolling import RollingConfig, RollingSimulation, rolling_simulation
from .validation_experiments import (
    run_ablation,
    run_empirical_resample,
    run_exact_small_game,
    run_gamma_scan,
    run_initial_purchase_neighborhood,
    run_parameter_scan,
    run_player_count_scan,
)
from .validator import (
    audit_simulation,
    conflict_loss,
    counterfactual_prefix_test,
    ex_post_regret_upper_bound,
)


# 仅用于复现实验的公开历史轨迹；第六关在线决策函数从不读取未来天气。
EMPIRICAL_PRESSURE_WEATHER = (
    "高温", "高温", "晴朗", "沙暴", "晴朗", "高温", "沙暴", "晴朗", "高温", "高温",
    "沙暴", "高温", "晴朗", "高温", "高温", "高温", "沙暴", "沙暴", "高温", "高温",
    "晴朗", "晴朗", "高温", "晴朗", "沙暴", "高温", "晴朗", "晴朗", "高温", "高温",
)


def _daily_rows(simulation: RollingSimulation) -> tuple[dict[str, object], ...]:
    rows = []
    for day in simulation.days:
        for player, (before, action, after) in enumerate(
            zip(day.states_before, day.actions, day.states_after), start=1
        ):
            rows.append(
                {
                    "天数": day.day,
                    "当天天气": day.weather,
                    "玩家": player,
                    "行动前节点": before.node,
                    "行动": action.kind,
                    "目的节点": action.destination,
                    "购买水": action.buy_water,
                    "购买食物": action.buy_food,
                    "消耗倍数": day.multipliers[player - 1],
                    "耗水": day.water_consumption[player - 1],
                    "耗食物": day.food_consumption[player - 1],
                    "购买支出": day.purchase_cost[player - 1],
                    "挖矿收入": day.mine_income[player - 1],
                    "行动后节点": after.node,
                    "剩余水": after.water,
                    "剩余食物": after.food,
                    "剩余现金": after.cash,
                    "已到终点": after.arrived,
                    "均衡类型": day.equilibrium.kind,
                    "当日epsilon": day.equilibrium.epsilon,
                }
            )
    return tuple(rows)


def _baseline_rows(weather, gamma, config):
    rows = []
    for result in run_baselines(weather, gamma, config):
        rows.append(
            {
                "基准": result.name,
                "定义": result.definition,
                "成功": result.success,
                "执行天数": result.executed_days,
                "平均终端财富": result.mean_terminal_wealth,
                "最差终端财富": result.minimum_terminal_wealth,
                "epsilon_max": result.epsilon_max,
                "L_move": result.conflict_loss.move,
                "L_mine": result.conflict_loss.mine,
                "L_village": result.conflict_loss.village,
                "L_conflict": result.conflict_loss.total,
                "失败原因": result.failure_reason,
            }
        )
    return tuple(rows)


def _information_leakage_test(weather, gamma, config) -> tuple[bool, int, int]:
    """对每个 t=1…len(weather) 做同前缀反事实检验。

    返回 (全部通过, 通过日数, 总检查日数)。仅在前 t 天完全一致、
    第 t+1 天起不同的情况下比较第 t 天策略，要求动作与阶段 payoff 表
    完全相同，以证明策略函数未越界读取未来天气。
    """
    if not weather:
        return True, 0, 0
    alternatives = {"晴朗": "高温", "高温": "晴朗", "沙暴": "晴朗"}
    total = 0
    passed = 0
    for t in range(1, len(weather) + 1):
        cf = tuple(
            weather[i] if i < t else alternatives[weather[i]]
            for i in range(len(weather))
        )
        if weather[: t - 1] != cf[: t - 1]:
            # 防御性检查：反事实前 t-1 天必须与原序列一致
            continue
        total += 1
        if counterfactual_prefix_test(weather, cf, t, gamma, config):
            passed += 1
    return passed == total, passed, total


def run_experiment(
    config: RollingConfig,
    weather_sequence: Sequence[str],
    gamma: int,
    output_root: Path,
    include_extended: bool = True,
) -> dict[str, object]:
    weather = tuple(weather_sequence)
    simulation = rolling_simulation(weather, gamma, config)
    audit = audit_simulation(simulation, config)
    loss = conflict_loss(simulation, config.game)
    regret = ex_post_regret_upper_bound(simulation, config.game)
    leakage_ok, leakage_passed, leakage_total = _information_leakage_test(
        weather, gamma, config
    )
    epsilon_max = max(
        (day.equilibrium.epsilon for day in simulation.days), default=0.0
    )
    wealths = [value for value in simulation.terminal_wealths if value is not None]
    resample_rows = run_empirical_resample(weather, gamma, config)
    resample = resample_rows[0]
    summary = {
        "experiment_type": "empirical_pressure_test",
        "future_weather_used_by_policy": False,
        "players": config.game.player_count,
        "Gamma": gamma,
        "weather_days_provided": len(weather),
        "executed_days": len(simulation.days),
        "success": simulation.success,
        "terminal_wealths": list(simulation.terminal_wealths),
        "mean_terminal_wealth": mean(wealths) if wealths else None,
        "epsilon_max": epsilon_max,
        "conflict_loss": asdict(loss),
        "information_leakage_ok": leakage_ok,
        "information_leakage_passed": leakage_passed,
        "information_leakage_total": leakage_total,
        "audit_check_count": audit.check_count,
        "audit_violation_count": audit.violation_count,
        "audit_max_abs_residual": audit.max_abs_residual,
        "audit_messages": list(audit.messages),
        "failure_reason": simulation.failure_reason,
        "resample_n_samples": resample["样本数"],
        "resample_success_rate": resample["成功率"],
        "resample_mean_wealth": resample["平均终端财富"],
    }
    if audit.violation_count or audit.max_abs_residual != 0 or not leakage_ok:
        raise RuntimeError("模型检验未通过，拒绝导出未经验证的第六关结果")
    if epsilon_max > config.tolerance:
        raise RuntimeError(f"阶段均衡误差超限：epsilon={epsilon_max}")

    output_root = Path(output_root)
    write_csv(output_root / "结果输出" / "第六关逐日滚动策略.csv", _daily_rows(simulation))
    write_json(output_root / "结果输出" / "第六关经验压力测试摘要.json", summary)
    write_json(output_root / "结果验证" / "第六关模型检验摘要.json", summary)
    write_csv(
        output_root / "结果验证" / "第六关Ex-post-Regret上界.csv",
        (asdict(row) for row in regret),
    )

    if include_extended:
        write_csv(
            output_root / "结果验证" / "第六关经验重采样.csv",
            resample_rows,
        )
        write_csv(
            output_root / "结果验证" / "第六关基准对比.csv",
            _baseline_rows(weather, gamma, config),
        )
        write_csv(
            output_root / "结果验证" / "第六关消融实验.csv",
            run_ablation(weather, gamma, config),
        )
        write_csv(
            output_root / "结果验证" / "第六关Gamma灵敏度.csv",
            run_gamma_scan(config.game, config.level),
        )
        write_csv(
            output_root / "结果验证" / "第六关参数灵敏度.csv",
            run_parameter_scan(config.game, config.level),
        )
        write_csv(
            output_root / "结果验证" / "第六关初始采购邻域灵敏度.csv",
            run_initial_purchase_neighborhood(config.game, config.level, gamma),
        )
        write_csv(
            output_root / "结果验证" / "第六关玩家数推广试验.csv",
            run_player_count_scan(weather, gamma, config),
        )
        write_json(
            output_root / "结果验证" / "第六关小规模精确对照.json",
            run_exact_small_game(),
        )
    return summary


def main() -> None:
    game, level = load_level6()
    root = Path(__file__).resolve().parents[1]
    summary = run_experiment(
        RollingConfig(game=game, level=level),
        EMPIRICAL_PRESSURE_WEATHER,
        gamma=6,
        output_root=root,
    )
    print(
        "第六关经验压力测试："
        f"成功={summary['success']}，执行{summary['executed_days']}天，"
        f"终端财富={summary['terminal_wealths']}，epsilon_max={summary['epsilon_max']}"
    )


if __name__ == "__main__":
    main()
