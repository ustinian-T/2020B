from __future__ import annotations

import csv
from dataclasses import asdict
import json
from pathlib import Path
from typing import Iterable

from .robust_dp_q3 import DailyRecord
from .scenario_tree_milp import ScenarioTreeSolution
from .validate_q2 import LevelThreeValidationReport


WEATHER_CODE = {"晴朗": "S", "高温": "H", "沙暴": "X"}


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )


def write_scenario_evaluations(
    path: Path, report: LevelThreeValidationReport
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        fieldnames = [
            "情景编号", "天气序列", "是否成功", "到达日", "在线终端财富",
            "Oracle终端财富", "Regret",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for number, item in enumerate(report.evaluations, start=1):
            writer.writerow(
                {
                    "情景编号": number,
                    "天气序列": "".join(WEATHER_CODE[w] for w in item.scenario),
                    "是否成功": item.success,
                    "到达日": item.arrival_day,
                    "在线终端财富": item.terminal_wealth,
                    "Oracle终端财富": item.oracle_wealth,
                    "Regret": item.regret,
                }
            )


def write_policy_tree(path: Path, solution: ScenarioTreeSolution) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        fieldnames = [
            "日期", "天气历史", "当天气", "行动", "目标节点", "鲁棒价值", "名义价值"
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for history in sorted(solution.policy, key=lambda item: (len(item), item)):
            action = solution.policy[history]
            writer.writerow(
                {
                    "日期": len(history),
                    "天气历史": "".join(WEATHER_CODE[w] for w in history),
                    "当天气": history[-1],
                    "行动": action.kind,
                    "目标节点": action.destination,
                    "鲁棒价值": solution.robust_by_history[history],
                    "名义价值": solution.nominal_by_history[history],
                }
            )


def write_daily_records(
    path: Path, initial_state, records: Iterable[DailyRecord]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        fieldnames = [
            "day", "node", "weather", "action", "from_node", "water", "food",
            "cash", "weight", "robust_value", "nominal_value",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow(
            {
                "day": 0,
                "node": initial_state.node,
                "weather": "—",
                "action": "起点统一采购",
                "from_node": initial_state.node,
                "water": initial_state.water,
                "food": initial_state.food,
                "cash": initial_state.cash,
                "weight": 3 * initial_state.water + 2 * initial_state.food,
                "robust_value": "",
                "nominal_value": "",
            }
        )
        for record in records:
            writer.writerow(
                {
                    "day": record.day,
                    "node": record.to_node,
                    "weather": record.weather,
                    "action": record.action,
                    "from_node": record.from_node,
                    "water": record.water,
                    "food": record.food,
                    "cash": record.cash,
                    "weight": record.weight,
                    "robust_value": record.robust_value,
                    "nominal_value": record.nominal_value,
                }
            )


def validation_summary(report: LevelThreeValidationReport) -> dict:
    payload = asdict(report)
    payload.pop("evaluations")
    return payload
