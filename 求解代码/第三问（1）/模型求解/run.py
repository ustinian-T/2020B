from __future__ import annotations

from pathlib import Path

from .data_loader import audit_graph, load_level5
from .export import write_csv, write_json
from .game_open_loop import find_pure_ne
from .sensitivity import scan_sensitivity
from .validator import audit_plan_result, exploitability


QUESTION_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = QUESTION_ROOT / "结果输出"
VALIDATION_DIR = QUESTION_ROOT / "结果验证"


def _daily_rows(equilibrium) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for player, result in enumerate(equilibrium.player_results, start=1):
        for record in result.records:
            rows.append(
                {
                    "玩家": player,
                    "日期": record.day,
                    "天气": record.weather,
                    "出发节点": record.from_node,
                    "到达节点": record.to_node,
                    "行动": record.action,
                    "消耗倍率": record.multiplier,
                    "同向同行对手数": record.edge_companions,
                    "同矿对手数": record.mine_companions,
                    "剩余水": record.water,
                    "剩余食物": record.food,
                    "剩余现金": record.cash,
                }
            )
    return rows


def main() -> dict[str, object]:
    game, level, weather = load_level5()
    graph_audit = audit_graph(level)
    equilibrium = find_pure_ne(game, level, weather)
    deviation = exploitability(equilibrium.profile, game, level, weather)
    audits = tuple(
        audit_plan_result(
            equilibrium.player_results[player],
            (equilibrium.profile[1 - player],),
            game,
            level,
            weather,
        )
        for player in range(2)
    )
    if equilibrium.kind != "pure" or deviation.epsilon != 0:
        raise RuntimeError(f"第五关未取得经全局偏离检验的纯均衡：{equilibrium}")
    if any(audit.violation_count for audit in audits):
        raise RuntimeError(f"第五关独立规则审计失败：{audits}")

    summary = {
        "模型": "完全信息开环有限动态博弈 + Pareto-DP最优响应",
        "均衡类型": equilibrium.kind,
        "迭代次数": equilibrium.iterations,
        "epsilon": deviation.epsilon,
        "图审计": {
            "对称": graph_audit.symmetric,
            "连通": graph_audit.connected,
            "关键节点可达": graph_audit.key_nodes_reachable,
            "重复边数": graph_audit.duplicate_edge_count,
        },
        "玩家": [
            {
                "玩家": player + 1,
                "初始水": result.plan.initial_water,
                "初始食物": result.plan.initial_food,
                "到达日": result.arrival_day,
                "终端现金": result.final_state.cash,
                "剩余水": result.final_state.water,
                "剩余食物": result.final_state.food,
                "终端财富": result.terminal_wealth,
                "路线": [record.from_node for record in result.records]
                + [result.records[-1].to_node],
                "行动": [record.action for record in result.records],
            }
            for player, result in enumerate(equilibrium.player_results)
        ],
    }
    validation = {
        "全局单边偏离": [
            {
                "玩家": row.player,
                "当前财富": row.current_wealth,
                "最优响应财富": row.best_response_wealth,
                "盈利偏离": row.gain,
            }
            for row in deviation.players
        ],
        "epsilon": deviation.epsilon,
        "规则审计": [
            {
                "玩家": player + 1,
                "检查数": audit.check_count,
                "违规数": audit.violation_count,
                "最大绝对残差": audit.max_abs_residual,
                "消息": list(audit.messages),
            }
            for player, audit in enumerate(audits)
        ],
    }
    write_csv(OUTPUT_DIR / "第五关玩家逐日策略.csv", _daily_rows(equilibrium))
    write_json(OUTPUT_DIR / "第五关均衡摘要.json", summary)
    write_json(VALIDATION_DIR / "第五关模型检验.json", validation)
    write_csv(
        VALIDATION_DIR / "第五关灵敏度分析.csv",
        scan_sensitivity(game, level, weather),
    )
    print(
        "第五关：纯Nash，epsilon=0，"
        + "，".join(
            f"玩家{i + 1}财富={result.terminal_wealth:.0f}、第{result.arrival_day}天到达"
            for i, result in enumerate(equilibrium.player_results)
        )
    )
    return summary


if __name__ == "__main__":
    main()
