from __future__ import annotations

import csv
from dataclasses import asdict
import json
from pathlib import Path

from .checker import replay_strategy
from .config import GAME, build_level_one, build_level_two
from .solver import SolveOptions, SolveResult, solve


PROJECT_ROOT = Path(__file__).resolve().parents[3]
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "结果输出"


def result_to_dict(result: SolveResult) -> dict:
    return {
        "关卡": result.level_name,
        "最优终端财富": result.final_wealth,
        "到达日期": result.arrival_day,
        "初始采购": asdict(result.initial_purchase),
        "求解状态": result.status,
        "全局最优": result.optimal,
        "运行时间秒": round(result.runtime_seconds, 6),
        "统计": result.statistics,
        "逐日策略": [asdict(record) for record in result.daily_records],
    }


def write_csv(result: SolveResult, path: Path) -> None:
    fieldnames = [
        "日期", "天气", "行动前区域", "所在区域", "行动", "购买水量", "购买食物量",
        "剩余资金数", "剩余水量", "剩余食物量", "总负重kg",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow(
            {
                "日期": 0,
                "天气": "—",
                "行动前区域": result.daily_records[0].from_node,
                "所在区域": result.daily_records[0].from_node,
                "行动": "起点采购",
                "购买水量": result.initial_purchase.water,
                "购买食物量": result.initial_purchase.food,
                "剩余资金数": GAME.initial_cash
                - GAME.water_price * result.initial_purchase.water
                - GAME.food_price * result.initial_purchase.food,
                "剩余水量": result.initial_purchase.water,
                "剩余食物量": result.initial_purchase.food,
                "总负重kg": GAME.water_weight * result.initial_purchase.water
                + GAME.food_weight * result.initial_purchase.food,
            }
        )
        for record in result.daily_records:
            writer.writerow(
                {
                    "日期": record.day,
                    "天气": record.weather,
                    "行动前区域": record.from_node,
                    "所在区域": record.to_node,
                    "行动": record.action,
                    "购买水量": record.buy_water,
                    "购买食物量": record.buy_food,
                    "剩余资金数": record.cash,
                    "剩余水量": record.water,
                    "剩余食物量": record.food,
                    "总负重kg": GAME.water_weight * record.water + GAME.food_weight * record.food,
                }
            )


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    results: list[SolveResult] = []
    for level in (build_level_one(), build_level_two()):
        result = solve(level, GAME, SolveOptions(time_limit_seconds=600))
        check = replay_strategy(level, GAME, result.initial_purchase, result.daily_records)
        if not result.optimal or not check.ok or check.final_wealth != result.final_wealth:
            raise RuntimeError(
                f"{level.name}未通过最终验证：optimal={result.optimal}, errors={check.errors}"
            )
        results.append(result)
        write_csv(result, OUTPUT_DIR / f"{level.name}逐日策略.csv")

    summary = {
        "模型": "有限期资源约束状态模型的完整逐日整数展开",
        "状态口径": "第t天日末，已扣除当日消耗并完成当日村庄采购",
        "公共参数": {
            "负重上限kg": GAME.capacity_kg,
            "初始资金": GAME.initial_cash,
            "截止日": GAME.deadline,
            "矿山基础收益": GAME.mine_income,
            "天气": list(GAME.weather),
        },
        "关卡结果": {result.level_name: result_to_dict(result) for result in results},
        "独立检验": "两关均由 checker.py 从逐日动作独立复算通过",
    }
    (OUTPUT_DIR / "求解摘要.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    for result in results:
        print(
            f"{result.level_name}: 最优终端财富={result.final_wealth:.0f}, "
            f"到达日={result.arrival_day}, 运行={result.runtime_seconds:.2f}s"
        )


if __name__ == "__main__":
    main()
