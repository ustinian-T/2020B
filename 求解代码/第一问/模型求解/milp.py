"""第一问 MILP 实现（可选验证器，参见建模手册 §2.3）。

建模手册 §2.3 明确指出：MILP 不作为第一问主模型，仅作为小规模或抽样
的独立校验器。完整动态规划主求解见 `dp.py`。

将完整逐日 Bellman 转移等价展开为 0-1/整数线性模型，由 HiGHS 做分支
定界求解，等价于 `dp.py` 中无剪枝的稀疏标签 DP（手册 §2.3、§6.4）。
"""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_matrix

from .checker import DailyRecord, InitialPurchase
from .config import GameConfig, LevelConfig


@dataclass(frozen=True)
class MILPOptions:
    time_limit_seconds: float = 300.0
    mip_relative_gap: float = 0.0
    disp: bool = False


class _LinearModel:
    def __init__(self) -> None:
        self.lower: list[float] = []
        self.upper: list[float] = []
        self.integrality: list[int] = []
        self.objective: list[float] = []
        self.rows: list[dict[int, float]] = []
        self.row_lower: list[float] = []
        self.row_upper: list[float] = []

    def var(self, lb=0.0, ub=np.inf, integer=False, objective=0.0) -> int:
        idx = len(self.lower)
        self.lower.append(lb)
        self.upper.append(ub)
        self.integrality.append(1 if integer else 0)
        self.objective.append(objective)
        return idx

    def constraint(self, terms: dict[int, float], lb=-np.inf, ub=np.inf) -> None:
        compact = {idx: value for idx, value in terms.items() if value}
        self.rows.append(compact)
        self.row_lower.append(lb)
        self.row_upper.append(ub)

    def equality(self, terms: dict[int, float], value: float) -> None:
        self.constraint(terms, value, value)

    def matrix(self):
        row_ids: list[int] = []
        col_ids: list[int] = []
        values: list[float] = []
        for row_id, row in enumerate(self.rows):
            for col_id, value in row.items():
                row_ids.append(row_id)
                col_ids.append(col_id)
                values.append(value)
        return coo_matrix(
            (values, (row_ids, col_ids)),
            shape=(len(self.rows), len(self.lower)),
            dtype=float,
        ).tocsr()


def _add(terms: dict[int, float], index: int, value: float) -> None:
    terms[index] = terms.get(index, 0.0) + value


def solve(
    level: LevelConfig,
    game: GameConfig,
    options: MILPOptions | None = None,
) -> tuple[InitialPurchase, list[DailyRecord], int, float, dict[str, int | float | str], float]:
    """完整逐日 MILP 等价展开 + HiGHS 分支定界。"""
    options = options or MILPOptions()
    started = perf_counter()
    model = _LinearModel()
    days = range(1, game.deadline + 1)
    nodes = range(1, level.node_count + 1)

    x: dict[tuple[int, int], int] = {}
    for day in range(0, game.deadline + 1):
        for node in nodes:
            if day == 0:
                fixed = 1.0 if node == level.start else 0.0
                x[day, node] = model.var(fixed, fixed, integer=True)
            elif day == game.deadline and node == level.goal:
                x[day, node] = model.var(1, 1, integer=True)
            else:
                x[day, node] = model.var(0, 1, integer=True)

    directed_edges = tuple((i, j) for i, j in level.edges for i, j in ((i, j), (j, i)))
    move: dict[tuple[int, int, int], int] = {}
    stay: dict[tuple[int, int], int] = {}
    mine: dict[tuple[int, int], int] = {}
    finish: dict[int, int] = {}
    for day in days:
        can_move = game.weather[day - 1] != "沙暴"
        for i, j in directed_edges:
            move[day, i, j] = model.var(
                0, 1 if can_move and i != level.goal else 0, integer=True
            )
        for node in nodes:
            if node != level.goal:
                stay[day, node] = model.var(0, 1, integer=True)
        for node in level.mines:
            mine[day, node] = model.var(0, 1, integer=True)
        finish[day] = model.var(0, 1, integer=True)

    max_water = game.capacity_kg // game.water_weight
    max_food = game.capacity_kg // game.food_weight
    buy_water = {day: model.var(0, max_water, integer=True) for day in range(0, game.deadline + 1)}
    buy_food = {day: model.var(0, max_food, integer=True) for day in range(0, game.deadline + 1)}
    water = {day: model.var(0, max_water, integer=False) for day in range(0, game.deadline + 1)}
    food = {day: model.var(0, max_food, integer=False) for day in range(0, game.deadline + 1)}
    cash = {
        day: model.var(
            0,
            game.initial_cash + game.deadline * game.mine_income,
            integer=False,
            objective=-2.0 if day == game.deadline else 0.0,
        )
        for day in range(0, game.deadline + 1)
    }
    model.objective[water[game.deadline]] = -float(game.water_price)
    model.objective[food[game.deadline]] = -float(game.food_price)

    outgoing: dict[tuple[int, int], list[int]] = {}
    incoming: dict[tuple[int, int], list[int]] = {}
    for day in days:
        for i, j in directed_edges:
            outgoing.setdefault((day, i), []).append(move[day, i, j])
            incoming.setdefault((day, j), []).append(move[day, i, j])
        for node in nodes:
            origin_terms: dict[int, float] = {x[day - 1, node]: -1.0}
            for idx in outgoing.get((day, node), []):
                _add(origin_terms, idx, 1.0)
            if node != level.goal:
                _add(origin_terms, stay[day, node], 1.0)
            if node in level.mines:
                _add(origin_terms, mine[day, node], 1.0)
            if node == level.goal:
                _add(origin_terms, finish[day], 1.0)
            model.equality(origin_terms, 0.0)

            destination_terms: dict[int, float] = {x[day, node]: -1.0}
            for idx in incoming.get((day, node), []):
                _add(destination_terms, idx, 1.0)
            if node != level.goal:
                _add(destination_terms, stay[day, node], 1.0)
            if node in level.mines:
                _add(destination_terms, mine[day, node], 1.0)
            if node == level.goal:
                _add(destination_terms, finish[day], 1.0)
            model.equality(destination_terms, 0.0)

    model.equality({water[0]: 1, buy_water[0]: -1}, 0)
    model.equality({food[0]: 1, buy_food[0]: -1}, 0)
    model.equality(
        {
            cash[0]: 1,
            buy_water[0]: game.water_price,
            buy_food[0]: game.food_price,
        },
        game.initial_cash,
    )
    model.constraint(
        {water[0]: game.water_weight, food[0]: game.food_weight},
        ub=game.capacity_kg,
    )

    for day in days:
        base_water, base_food = game.base_consumption[game.weather[day - 1]]
        action_coeffs: dict[int, int] = {}
        for i, j in directed_edges:
            action_coeffs[move[day, i, j]] = 2
        for node in nodes:
            if node != level.goal:
                action_coeffs[stay[day, node]] = 1
        for node in level.mines:
            action_coeffs[mine[day, node]] = 3

        water_eq = {water[day]: 1, water[day - 1]: -1, buy_water[day]: -1}
        food_eq = {food[day]: 1, food[day - 1]: -1, buy_food[day]: -1}
        pre_water = {water[day - 1]: 1}
        pre_food = {food[day - 1]: 1}
        for idx, multiplier in action_coeffs.items():
            _add(water_eq, idx, base_water * multiplier)
            _add(food_eq, idx, base_food * multiplier)
            _add(pre_water, idx, -base_water * multiplier)
            _add(pre_food, idx, -base_food * multiplier)
        model.equality(water_eq, 0)
        model.equality(food_eq, 0)
        model.constraint(pre_water, lb=0)
        model.constraint(pre_food, lb=0)

        cash_eq = {
            cash[day]: 1,
            cash[day - 1]: -1,
            buy_water[day]: 2 * game.water_price,
            buy_food[day]: 2 * game.food_price,
        }
        for node in level.mines:
            _add(cash_eq, mine[day, node], -game.mine_income)
        model.equality(cash_eq, 0)

        village_position = {x[day, village]: -max_water for village in level.villages}
        village_position[buy_water[day]] = 1
        model.constraint(village_position, ub=0)
        village_position_food = {
            x[day, village]: -max_food for village in level.villages
        }
        village_position_food[buy_food[day]] = 1
        model.constraint(village_position_food, ub=0)

        model.constraint(
            {water[day]: game.water_weight, food[day]: game.food_weight},
            ub=game.capacity_kg,
        )
        model.constraint({water[day]: 1, x[day, level.goal]: max_water}, lb=1)
        model.constraint({food[day]: 1, x[day, level.goal]: max_food}, lb=1)

    matrix = model.matrix()
    result = milp(
        c=np.asarray(model.objective, dtype=float),
        integrality=np.asarray(model.integrality, dtype=np.uint8),
        bounds=Bounds(model.lower, model.upper),
        constraints=LinearConstraint(matrix, model.row_lower, model.row_upper),
        options={
            "time_limit": options.time_limit_seconds,
            "mip_rel_gap": options.mip_relative_gap,
            "presolve": True,
            "disp": options.disp,
        },
    )
    if result.x is None:
        raise RuntimeError(f"{level.name} MILP 求解失败：{result.message}")

    values = result.x
    initial = InitialPurchase(
        water=int(round(values[buy_water[0]])),
        food=int(round(values[buy_food[0]])),
    )
    records: list[DailyRecord] = []
    arrival_day = game.deadline
    for day in days:
        origin = max(nodes, key=lambda node: values[x[day - 1, node]])
        destination = max(nodes, key=lambda node: values[x[day, node]])
        if origin == level.goal:
            break
        if origin in level.mines and values[mine[day, origin]] > 0.5:
            action = "挖矿"
        elif destination == origin:
            action = "停留"
        else:
            action = "行走"
        records.append(
            DailyRecord(
                day=day,
                weather=game.weather[day - 1],
                from_node=origin,
                to_node=destination,
                action=action,
                buy_water=int(round(values[buy_water[day]])),
                buy_food=int(round(values[buy_food[day]])),
                cash=int(round(values[cash[day]])),
                water=int(round(values[water[day]])),
                food=int(round(values[food[day]])),
            )
        )
        if destination == level.goal:
            arrival_day = day
            break

    terminal = records[-1]
    final_wealth = (
        terminal.cash
        + 0.5 * game.water_price * terminal.water
        + 0.5 * game.food_price * terminal.food
    )
    statistics: dict[str, int | float | str] = {
        "变量总数": len(model.lower),
        "约束总数": len(model.rows),
        "MIP 节点数": int(getattr(result, "mip_node_count", 0) or 0),
        "MIP 间隙": float(getattr(result, "mip_gap", 0.0) or 0.0),
        "求解器目标值(2Z)": float(-result.fun),
        "终端现金": int(round(values[cash[game.deadline]])),
        "terminal_cash": int(round(values[cash[game.deadline]])),
        "终端水量": int(round(values[water[game.deadline]])),
        "终端食物量": int(round(values[food[game.deadline]])),
        "求解器": "SciPy milp / HiGHS",
    }
    return (
        initial,
        records,
        arrival_day,
        round(final_wealth * 2) / 2,
        statistics,
        perf_counter() - started,
    )