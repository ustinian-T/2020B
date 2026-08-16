"""第一问求解器：有限期资源约束状态模型的整数网络流展开。

对应《第一问求解报告》第 5 章模型建立：

- 公式 (4)-(5)：第 0 天起点一次性采购，预算与负重双重约束
- 公式 (6)-(7)：行动消耗倍率 κ(a_t) ∈ {1, 2, 3}
- 公式 (8)：沙暴禁行走、挖矿需在矿山
- 公式 (9)-(10)：资源递推，先动作扣消耗再日末村庄采购
- 公式 (11)：现金递推，含挖矿收益与村庄双倍价
- 公式 (12)：非负与负重约束；非终点"≥ 1"为 checker 等价的 tightening
- 公式 (13)：到达 g 后 a_{t+1}=Finish，且村庄采购仅在村庄节点
- 公式 (15)-(16)：逐日整数网络流的起点/终点守恒
- 公式 (2)：目标函数 max Z = C_τ + 0.5 p_w W_τ + 0.5 p_f F_τ

由于截止日后所有变量保持不变（公式 13 吸收约束），
deadline 日的 cash/water/food 等于到达日 τ 的值，故以 deadline 日
变量作为 τ 的等价表达。SciPy milp 接口调用 HiGHS 分支定界，
mip_rel_gap=0 保证零间隙全局最优。
"""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Iterable

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_matrix

from .checker import DailyRecord, InitialPurchase
from .config import GameConfig, LevelConfig


@dataclass(frozen=True)
class SolveOptions:
    time_limit_seconds: float = 300.0
    mip_relative_gap: float = 0.0
    disp: bool = False


@dataclass(frozen=True)
class SolveResult:
    level_name: str
    optimal: bool
    status: str
    final_wealth: float
    arrival_day: int
    initial_purchase: InitialPurchase
    daily_records: list[DailyRecord]
    runtime_seconds: float
    statistics: dict[str, int | float | str]


class _LinearModel:
    """稀疏线性模型的轻量封装，与 SciPy milp 输入对齐。"""

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
    level: LevelConfig, game: GameConfig, options: SolveOptions | None = None
) -> SolveResult:
    """求解完整逐日模型（对应报告第 5 章）。

    变量与约束与公式 (15)-(16) 一一对应；目标取自公式 (2)。
    HiGHS 分支定界 mip_rel_gap=0，输出由 checker 独立逐日复算。
    """
    options = options or SolveOptions()
    started = perf_counter()
    model = _LinearModel()
    days = range(1, game.deadline + 1)
    nodes = range(1, level.node_count + 1)

    # 状态变量 x[t,i]：第 t 日日末是否位于节点 i（公式 5.2 状态口径）
    x: dict[tuple[int, int], int] = {}
    for day in range(0, game.deadline + 1):
        for node in nodes:
            if day == 0:
                # 第 0 天固定在起点（公式 5.4 起点约束）
                fixed = 1.0 if node == level.start else 0.0
                x[day, node] = model.var(fixed, fixed, integer=True)
            elif day == game.deadline and node == level.goal:
                # 截止日强制抵达终点，使目标函数取值点唯一
                x[day, node] = model.var(1, 1, integer=True)
            else:
                x[day, node] = model.var(0, 1, integer=True)

    # 行动变量（公式 5.2 + 公式 5.9）：
    #   move[day,i,j] ≡ y_{t,i,j} 沿 (i,j) 行走
    #   stay[day,i]   ≡ u^S_{t,i}   在 i 停留
    #   mine[day,i]   ≡ u^M_{t,i}   在 i 挖矿
    #   finish[day]   ≡ u^G_t       到达 g 后保持吸收状态（公式 5.7 / 公式 13）
    directed_edges = tuple(
        (i, j) for i, j in level.edges for i, j in ((i, j), (j, i))
    )
    move: dict[tuple[int, int, int], int] = {}
    stay: dict[tuple[int, int], int] = {}
    mine: dict[tuple[int, int], int] = {}
    finish: dict[int, int] = {}
    for day in days:
        # 沙暴日 move 全部为 0（公式 8 第二条）
        can_move = game.weather[day - 1] != "沙暴"
        for i, j in directed_edges:
            move[day, i, j] = model.var(
                0, 1 if can_move and i != level.goal else 0, integer=True
            )
        # 终点不允许停留（公式 13 吸收约束）
        for node in nodes:
            if node != level.goal:
                stay[day, node] = model.var(0, 1, integer=True)
        # 仅在矿山定义挖矿变量（公式 8 第三条）
        for node in level.mines:
            mine[day, node] = model.var(0, 1, integer=True)
        # u^G_t：吸收动作的 0-1 变量（公式 13）
        finish[day] = model.var(0, 1, integer=True)

    # 资源/采购/现金变量（公式 9-11）
    max_water = game.capacity_kg // game.water_weight
    max_food = game.capacity_kg // game.food_weight
    buy_water = {
        day: model.var(0, max_water, integer=True)
        for day in range(0, game.deadline + 1)
    }
    buy_food = {
        day: model.var(0, max_food, integer=True)
        for day in range(0, game.deadline + 1)
    }
    # 库存连续即可：消耗、采购、初始均为整数，自动保证整数解
    water = {
        day: model.var(0, max_water, integer=False)
        for day in range(0, game.deadline + 1)
    }
    food = {
        day: model.var(0, max_food, integer=False)
        for day in range(0, game.deadline + 1)
    }
    # 目标函数（公式 2）：max Z = C_τ + 0.5 p_w W_τ + 0.5 p_f F_τ
    # 截止日后所有变量保持不变（公式 13），deadline 日变量等于 τ 日值。
    # HiGHS 不接受小数系数系数 0.5，统一乘 2：
    #   min -(2 C_τ + p_w W_τ + p_f F_τ) = max (2 C_τ + p_w W_τ + p_f F_τ)
    # final_wealth = obj / 2 = Z
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

    # 每日流守恒（公式 15 / 16）：
    #   公式 15：x_{t-1,i} = Σ_j y_{t,i,j} + u^S_{t,i} + u^M_{t,i} + u^G_t·I(i=g)
    #   公式 16：x_{t,j}   = Σ_i y_{t,i,j} + u^S_{t,j} + u^M_{t,j} + u^G_t·I(j=g)
    # 终点节点同时被吸收约束封锁所有外向移动，保证游戏到达后即结束。
    outgoing: dict[tuple[int, int], list[int]] = {}
    incoming: dict[tuple[int, int], list[int]] = {}
    for day in days:
        for i, j in directed_edges:
            outgoing.setdefault((day, i), []).append(move[day, i, j])
            incoming.setdefault((day, j), []).append(move[day, i, j])
        for node in nodes:
            # 公式 15：起点流出守恒
            origin_terms: dict[int, float] = {x[day - 1, node]: -1.0}
            for idx in outgoing.get((day, node), []):
                _add(origin_terms, idx, 1.0)
            if node != level.goal:
                _add(origin_terms, stay[day, node], 1.0)
            if node in level.mines:
                _add(origin_terms, mine[day, node], 1.0)
            if node == level.goal:
                # u^G_t 仅在 i=g 显式出现；非 goal 节点的 + u^G_t 项通过
                # flow 守恒隐含为 0（因为 x_{t-1,i}=0 时所有动作必须为 0），
                # 与报告公式 15 的写法等价。
                _add(origin_terms, finish[day], 1.0)
            model.equality(origin_terms, 0.0)

            # 公式 16：终点汇入守恒
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

    # 第 0 天采购与状态（公式 4-5）
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
    # 负重约束 m_w W_0 + m_f F_0 ≤ M（公式 5 第二条）
    model.constraint(
        {water[0]: game.water_weight, food[0]: game.food_weight},
        ub=game.capacity_kg,
    )

    for day in days:
        base_water, base_food = game.base_consumption[game.weather[day - 1]]
        # 公式 6：行动消耗倍率 κ(a_t) ∈ {1, 2, 3}
        action_coeffs: dict[int, int] = {}
        for i, j in directed_edges:
            action_coeffs[move[day, i, j]] = 2
        for node in nodes:
            if node != level.goal:
                action_coeffs[stay[day, node]] = 1
        for node in level.mines:
            action_coeffs[mine[day, node]] = 3

        # 公式 9-10：资源递推 W_t = W_{t-1} - κ(a_t)c_w(ω_t) + b^w_t
        water_eq = {water[day]: 1, water[day - 1]: -1, buy_water[day]: -1}
        food_eq = {food[day]: 1, food[day - 1]: -1, buy_food[day]: -1}
        # 可执行性：W_{t-1} ≥ κ(a_t) c_w(ω_t)（公式 7 + 12 隐含）
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

        # 公式 11：现金递推 C_t = C_{t-1} + R·I(Mine) - 2p_w b^w_t - 2p_f b^f_t
        cash_eq = {
            cash[day]: 1,
            cash[day - 1]: -1,
            buy_water[day]: 2 * game.water_price,
            buy_food[day]: 2 * game.food_price,
        }
        for node in level.mines:
            _add(cash_eq, mine[day, node], -game.mine_income)
        model.equality(cash_eq, 0)

        # 公式 13 村庄约束：b^w_t, b^f_t > 0 ⇒ x_{t,·} ∈ V_v
        village_position = {x[day, village]: -max_water for village in level.villages}
        village_position[buy_water[day]] = 1
        model.constraint(village_position, ub=0)
        village_position_food = {
            x[day, village]: -max_food for village in level.villages
        }
        village_position_food[buy_food[day]] = 1
        model.constraint(village_position_food, ub=0)

        # 公式 12 负重约束：m_w W_t + m_f F_t ≤ M
        model.constraint(
            {water[day]: game.water_weight, food[day]: game.food_weight},
            ub=game.capacity_kg,
        )
        # 公式 12 非负约束 W_t, F_t ≥ 0 的大 M 收紧：
        #   报告允许 W_t ≥ 0；checker 与题目语义要求"非终点前不可断粮断水"，
        #   故此处用 (W_t, F_t) ≥ 1 作为 tightening。
        #   终点处通过大 M 系数 max_water / max_food 放松至 W_t ≥ -max_water + 1，
        #   与变量下界 0 共同作用允许 W_t = 0（公式 13 终点半价回收一致）。
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
        raise RuntimeError(f"{level.name}求解失败：{result.message}")

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
    return SolveResult(
        level_name=level.name,
        optimal=result.status == 0,
        status=str(result.message),
        final_wealth=round(final_wealth * 2) / 2,
        arrival_day=arrival_day,
        initial_purchase=initial,
        daily_records=records,
        runtime_seconds=perf_counter() - started,
        statistics={
            "variables": len(model.lower),
            "constraints": len(model.rows),
            "mip_nodes": int(getattr(result, "mip_node_count", 0) or 0),
            "mip_gap": float(getattr(result, "mip_gap", 0.0) or 0.0),
            "solver_objective_twice": float(-result.fun),
            "terminal_cash": int(round(values[cash[game.deadline]])),
            "terminal_water": int(round(values[water[game.deadline]])),
            "terminal_food": int(round(values[food[game.deadline]])),
            "solver": "SciPy milp / HiGHS",
        },
    )
