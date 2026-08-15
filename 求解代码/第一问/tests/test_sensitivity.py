from pathlib import Path
import sys


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT))

from 模型求解.sensitivity import build_scenarios


def test_sensitivity_scenarios_cover_four_parameters_without_duplicate_baseline():
    scenarios = build_scenarios()
    keys = {(item.level_name, item.parameter, item.value) for item in scenarios}

    assert len(keys) == len(scenarios)
    assert {item.parameter for item in scenarios} == {
        "基准",
        "负重上限",
        "初始资金",
        "矿山收益",
        "截止日期",
    }
    assert sum(item.parameter == "基准" for item in scenarios) == 2
    assert all(item.game.deadline == len(item.game.weather) for item in scenarios)
