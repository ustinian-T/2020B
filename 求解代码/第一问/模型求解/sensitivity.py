from __future__ import annotations

import csv
from dataclasses import dataclass, replace
from pathlib import Path

from .checker import replay_strategy
from .config import GAME, GameConfig, LevelConfig, build_level_one, build_level_two
from .solver import SolveOptions, solve


OUTPUT_PATH = Path(__file__).resolve().parents[1] / "结果输出" / "灵敏性分析.csv"


@dataclass(frozen=True)
class Scenario:
    level_name: str
    level: LevelConfig
    parameter: str
    value: int
    game: GameConfig


def _with_deadline(deadline: int) -> GameConfig:
    return replace(GAME, deadline=deadline, weather=GAME.weather[:deadline])


def build_scenarios() -> list[Scenario]:
    first, second = build_level_one(), build_level_two()
    scenarios = [
        Scenario(first.name, first, "基准", 0, GAME),
        Scenario(second.name, second, "基准", 0, GAME),
    ]
    for level in (first, second):
        for capacity in (1080, 1320):
            scenarios.append(
                Scenario(level.name, level, "负重上限", capacity, replace(GAME, capacity_kg=capacity))
            )
        for income in (900, 1100):
            scenarios.append(
                Scenario(level.name, level, "矿山收益", income, replace(GAME, mine_income=income))
            )
    for cash in (9000, 11000):
        scenarios.append(
            Scenario(first.name, first, "初始资金", cash, replace(GAME, initial_cash=cash))
        )
    for deadline in (26, 28):
        scenarios.append(
            Scenario(first.name, first, "截止日期", deadline, _with_deadline(deadline))
        )
    return scenarios


def main() -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, int | float | str]] = []
    for index, scenario in enumerate(build_scenarios(), start=1):
        result = solve(
            scenario.level,
            scenario.game,
            SolveOptions(time_limit_seconds=300),
        )
        check = replay_strategy(
            scenario.level,
            scenario.game,
            result.initial_purchase,
            result.daily_records,
        )
        if not result.optimal or not check.ok:
            raise RuntimeError(
                f"灵敏性场景未通过：{scenario.level_name}/{scenario.parameter}/{scenario.value}: "
                f"{result.status}; {check.errors}"
            )
        records = result.daily_records
        rows.append(
            {
                "关卡": scenario.level_name,
                "参数": scenario.parameter,
                "参数值": scenario.value if scenario.parameter != "基准" else "基准",
                "最优终端财富": result.final_wealth,
                "到达日": result.arrival_day,
                "挖矿天数": sum(record.action == "挖矿" for record in records),
                "村庄采购次数": sum(
                    bool(record.buy_water or record.buy_food) for record in records
                ),
                "初始水量": result.initial_purchase.water,
                "初始食物量": result.initial_purchase.food,
                "运行时间秒": round(result.runtime_seconds, 3),
            }
        )
        print(
            f"[{index:02d}/{len(build_scenarios())}] {scenario.level_name} "
            f"{scenario.parameter}={scenario.value}: {result.final_wealth:.0f}"
        )

    with OUTPUT_PATH.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(OUTPUT_PATH)


if __name__ == "__main__":
    main()
