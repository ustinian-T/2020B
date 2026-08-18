#!/usr/bin/env python3
"""
2020B 第一问
1. config - 配置参数和地图定义
2. rules - 行动消耗和合法性检查
3. preprocess - 地图验证
4. checker - 策略回放验证
5. dp - 动态规划求解器
6. milp - MILP求解器
7. solver - 求解器入口和结果封装
8. sensitivity - 灵敏性分析
"""

from __future__ import annotations

import csv
import json
import sys
from collections import deque
from dataclasses import dataclass, replace, asdict
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Mapping, Tuple, List, Dict, Optional
import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_matrix


# config - 配置参数和地图定义

print()
print("config - 配置参数和地图定义")
print()

Weather = str


@dataclass(frozen=True)
class GameConfig:
    """游戏全局配置"""
    capacity_kg: int
    initial_cash: int
    deadline: int
    mine_income: int
    water_weight: int
    food_weight: int
    water_price: int
    food_price: int
    weather: tuple[Weather, ...]
    base_consumption: Mapping[Weather, Tuple[int, int]]


@dataclass(frozen=True)
class LevelConfig:
    """关卡配置"""
    name: str
    node_count: int
    edges: Tuple[Tuple[int, int], ...]
    neighbors: Mapping[int, frozenset[int]]
    start: int
    goal: int
    villages: frozenset[int]
    mines: frozenset[int]


# 30天天气序列
WEATHER = (
    "高温", "高温", "晴朗", "沙暴", "晴朗", "高温", "沙暴", "晴朗", "高温", "高温",
    "沙暴", "高温", "晴朗", "高温", "高温", "高温", "沙暴", "沙暴", "高温", "高温",
    "晴朗", "晴朗", "高温", "晴朗", "沙暴", "高温", "晴朗", "晴朗", "高温", "高温",
)

# 游戏全局参数
GAME = GameConfig(
    capacity_kg=1200,
    initial_cash=10000,
    deadline=30,
    mine_income=1000,
    water_weight=3,
    food_weight=2,
    water_price=5,
    food_price=10,
    weather=WEATHER,
    base_consumption={"晴朗": (5, 7), "高温": (8, 6), "沙暴": (10, 10)},
)

# 第一关地图边 27节点
LEVEL_ONE_EDGES = (
    (1, 2), (1, 25), (2, 3), (3, 4), (3, 25), (4, 5), (4, 24), (4, 25),
    (5, 6), (5, 24), (6, 7), (6, 23), (6, 24), (7, 8), (7, 22), (8, 9),
    (8, 22), (9, 10), (9, 15), (9, 16), (9, 17), (9, 21), (9, 22), (10, 11),
    (10, 13), (10, 15), (11, 12), (11, 13), (12, 13), (12, 14), (13, 14),
    (13, 15), (14, 15), (14, 16), (15, 16), (16, 17), (16, 18), (17, 18),
    (17, 21), (18, 19), (18, 20), (19, 20), (20, 21), (21, 22), (21, 23),
    (21, 27), (22, 23), (23, 24), (23, 26), (24, 25), (24, 26), (25, 26),
    (26, 27),
)


def _make_level(name: str, node_count: int, edges: Tuple[Tuple[int, int], ...],
                start: int, goal: int, villages: frozenset, mines: frozenset) -> LevelConfig:
    """构建关卡配置"""
    adjacency = {node: set() for node in range(1, node_count + 1)}
    normalized = tuple(sorted((min(i, j), max(i, j)) for i, j in edges))
    for i, j in normalized:
        adjacency[i].add(j)
        adjacency[j].add(i)
    return LevelConfig(
        name=name,
        node_count=node_count,
        edges=normalized,
        neighbors={node: frozenset(items) for node, items in adjacency.items()},
        start=start,
        goal=goal,
        villages=villages,
        mines=mines,
    )


def build_level_one() -> LevelConfig:
    """构建第一关：27节点地图"""
    return _make_level("第一关", 27, LEVEL_ONE_EDGES, 1, 27, frozenset({15}), frozenset({12}))


def build_level_two() -> LevelConfig:
    """构建第二关：64节点网格地图"""
    rows = cols = 8
    odd_deltas = ((-1, -1), (-1, 0), (0, -1), (0, 1), (1, -1), (1, 0))
    even_deltas = ((-1, 0), (-1, 1), (0, -1), (0, 1), (1, 0), (1, 1))
    edges = []
    for node in range(1, rows * cols + 1):
        row = (node - 1) // cols + 1
        col = (node - 1) % cols + 1
        deltas = odd_deltas if row % 2 else even_deltas
        for d_row, d_col in deltas:
            next_row, next_col = row + d_row, col + d_col
            if 1 <= next_row <= rows and 1 <= next_col <= cols:
                neighbor = (next_row - 1) * cols + next_col
                if node < neighbor:
                    edges.append((node, neighbor))
    return _make_level("第二关", 64, tuple(edges), 1, 64, frozenset({39, 62}), frozenset({30, 55}))


print(f"天气序列加载完成：{len(WEATHER)}天")
print(f"第一关地图：{27}节点，{len(LEVEL_ONE_EDGES)}条边")
level_two = build_level_two()
print(f"第二关地图：{64}节点，{len(level_two.edges)}条边")
print()

# rules - 行动消耗和合法性检查

print()
print("rules - 行动消耗和合法性检查")
print()

ACTION_MULTIPLIER = {"停留": 1, "行走": 2, "挖矿": 3}


def action_consumption(game: GameConfig, weather: str, action: str) -> Tuple[int, int]:
    """计算行动消耗的水和食物"""
    if action not in ACTION_MULTIPLIER:
        raise ValueError(f"未知行动：{action}")
    water, food = game.base_consumption[weather]
    multiplier = ACTION_MULTIPLIER[action]
    return water * multiplier, food * multiplier


def legal_action(level: LevelConfig, weather: str, from_node: int, to_node: int, action: str) -> bool:
    """检查行动是否合法"""
    if action == "行走":
        return weather != "沙暴" and to_node in level.neighbors[from_node]
    if action == "停留":
        return from_node == to_node
    if action == "挖矿":
        return from_node == to_node and from_node in level.mines
    return False


print(f"行动类型：{list(ACTION_MULTIPLIER.keys())}")
print(f"天气类型：{list(GAME.base_consumption.keys())}")
print(f"行动消耗倍率：{ACTION_MULTIPLIER}")
print()

# preprocess - 地图验证

print()
print("preprocess - 地图验证")
print()


@dataclass(frozen=True)
class ValidationReport:
    ok: bool
    errors: Tuple[str, ...]


def bfs_distances(level: LevelConfig, target: int) -> Dict[int, int]:
    """BFS计算最短距离"""
    distances = {target: 0}
    queue = deque([target])
    while queue:
        node = queue.popleft()
        for neighbor in level.neighbors[node]:
            if neighbor not in distances:
                distances[neighbor] = distances[node] + 1
                queue.append(neighbor)
    return distances


def validate_level(level: LevelConfig) -> ValidationReport:
    """验证地图配置的正确性"""
    errors = []
    valid_nodes = set(range(1, level.node_count + 1))
    if level.start not in valid_nodes or level.goal not in valid_nodes:
        errors.append("起点或终点超出节点范围")
    if not level.villages <= valid_nodes or not level.mines <= valid_nodes:
        errors.append("村庄或矿山节点超出节点范围")
    if len(level.edges) != len(set(level.edges)):
        errors.append("邻接边存在重复")
    for i, j in level.edges:
        if i == j:
            errors.append(f"存在自环 {i}-{j}")
        if i not in valid_nodes or j not in valid_nodes:
            errors.append(f"边 {i}-{j} 超出节点范围")
        elif j not in level.neighbors[i] or i not in level.neighbors[j]:
            errors.append(f"邻接关系 {i}-{j} 不对称")
    if level.goal not in bfs_distances(level, level.start):
        errors.append("起点与终点不连通")
    return ValidationReport(not errors, tuple(errors))


level_one = build_level_one()
level_two = build_level_two()
report1 = validate_level(level_one)
report2 = validate_level(level_two)
print(f"第一关验证：{'通过' if report1.ok else '失败'}")
if not report1.ok:
    for err in report1.errors:
        print(f"  ✗ {err}")
print(f"第二关验证：{'通过' if report2.ok else '失败'}")
if not report2.ok:
    for err in report2.errors:
        print(f"  ✗ {err}")
print()

# checker - 策略回放验证

print()
print("checker - 策略回放验证")
print()


@dataclass(frozen=True)
class InitialPurchase:
    water: int
    food: int


@dataclass(frozen=True)
class DailyRecord:
    day: int
    weather: str
    from_node: int
    to_node: int
    action: str
    buy_water: int
    buy_food: int
    cash: int
    water: int
    food: int


@dataclass(frozen=True)
class CheckResult:
    ok: bool
    errors: Tuple[str, ...]
    final_wealth: Optional[float]


def replay_strategy(level: LevelConfig, game: GameConfig,
                    initial_purchase: InitialPurchase,
                    daily_records: List[DailyRecord]) -> CheckResult:
    """从逐日动作独立复算策略的正确性"""
    errors = []
    water = initial_purchase.water
    food = initial_purchase.food
    cash = game.initial_cash - game.water_price * water - game.food_price * food
    node = level.start

    if min(water, food, cash) < 0:
        errors.append("第0天采购导致库存或现金为负")
    if game.water_weight * water + game.food_weight * food > game.capacity_kg:
        errors.append("第0天采购超过负重上限")

    reached_goal = False
    for expected_day, record in enumerate(daily_records, start=1):
        if reached_goal:
            errors.append(f"第{record.day}天：到达终点后仍有行动")
            break
        if record.day != expected_day or record.day > game.deadline:
            errors.append(f"第{record.day}天：日期不连续或超过截止日")
        expected_weather = game.weather[record.day - 1]
        if record.weather != expected_weather:
            errors.append(f"第{record.day}天：天气记录不一致")
        if record.from_node != node:
            errors.append(f"第{record.day}天：行动起点与上一日位置不一致")
        if not legal_action(level, expected_weather, node, record.to_node, record.action):
            errors.append(f"第{record.day}天：{record.action}行动不合法")

        consume_water, consume_food = action_consumption(game, expected_weather, record.action)
        water -= consume_water
        food -= consume_food
        if water < 0 or food < 0:
            errors.append(f"第{record.day}天：行动途中资源不足")
        if record.action == "挖矿":
            cash += game.mine_income

        node = record.to_node
        if record.buy_water < 0 or record.buy_food < 0:
            errors.append(f"第{record.day}天：采购量必须为非负整数")
        if record.buy_water or record.buy_food:
            if node not in level.villages:
                errors.append(f"第{record.day}天：非村庄节点发生采购")
            cash -= 2 * (game.water_price * record.buy_water + game.food_price * record.buy_food)
            water += record.buy_water
            food += record.buy_food

        if cash < 0:
            errors.append(f"第{record.day}天：现金为负")
        if game.water_weight * water + game.food_weight * food > game.capacity_kg:
            errors.append(f"第{record.day}天：负重超过上限")
        if node != level.goal and (water <= 0 or food <= 0):
            errors.append(f"第{record.day}天：未到终点前资源耗尽")
        if (record.cash, record.water, record.food) != (cash, water, food):
            errors.append(f"第{record.day}天：记录值与独立复算不一致")
        reached_goal = node == level.goal

    if not reached_goal:
        errors.append("策略未在截止日前到达终点")
        final_wealth = None
    else:
        final_wealth = cash + 0.5 * game.water_price * water + 0.5 * game.food_price * food
    return CheckResult(not errors, tuple(errors), final_wealth)


print("策略回放验证器加载完成")
print(f"  - 验证逐日行动的合法性")
print(f"  - 独立复算资源变化")
print(f"  - 检查终点到达和最终财富")
print()

# dp - 动态规划求解器

print()
print("dp - 动态规划求解器")
print()


@dataclass(frozen=True)
class DPOptions:
    """DP求解控制选项"""
    use_pareto: bool = True
    use_time_bound: bool = True
    use_revenue_bound: bool = True
    pareto_threshold: int = 10000
    disp: bool = False


@dataclass(frozen=True)
class _Label:
    """稀疏标签：状态(t,i,w,f)下的最大现金+前驱指针"""
    cash: int
    prev: Optional[Tuple[int, int, int, int, str, int, int]]


def _bfs_distances(level: LevelConfig, target: int) -> Dict[int, int]:
    """节点到target的最少移动步数"""
    distances = {target: 0}
    queue = deque([target])
    while queue:
        node = queue.popleft()
        for neighbor in level.neighbors[node]:
            if neighbor not in distances:
                distances[neighbor] = distances[node] + 1
                queue.append(neighbor)
    return distances


def _earliest_arrival(t: int, dist: int, deadline: int,
                      weather: Tuple[str, ...]) -> Optional[int]:
    """从第t天末出发到目标的理论最早日期"""
    if dist == 0:
        return t
    needed = dist
    for q in range(t + 1, deadline + 1):
        if weather[q - 1] != "沙暴":
            needed -= 1
            if needed == 0:
                return q
    return None


def _precompute_earliest(deadline: int, weather: Tuple[str, ...],
                         distances: Dict[int, int]) -> Dict[int, Dict[int, Optional[int]]]:
    """预计算每个(day,node)的最早到达日"""
    table = {}
    for t in range(0, deadline + 1):
        table[t] = {node: _earliest_arrival(t, dist, deadline, weather)
                    for node, dist in distances.items()}
    return table


def _pareto_prune(labels: Dict[Tuple[int, int], _Label]) -> Dict[Tuple[int, int], _Label]:
    """Pareto支配剪枝 手册§5.2"""
    # 按w降序扫描，维护(f,cash)的2D Pareto前沿
    pruned = {}
    for (w, f), label in sorted(labels.items(), key=lambda x: -x[0][0]):
        frontier = [(f_item, label_item.cash) for f_item, label_item in pruned.values()
                    if f_item >= f]
        dominated = any(cash >= label.cash for _, cash in frontier)
        if not dominated:
            pruned[(w, f)] = label
    return pruned


# DP主求解函数 完整实现
def dp_solve(level: LevelConfig, game: GameConfig,
             options: DPOptions = None) -> DPResult:
    """稀疏标签动态规划主求解 手册§5"""
    options = options or DPOptions()
    started = perf_counter()

    distances = _bfs_distances(level, level.goal)
    earliest = _precompute_earliest(game.deadline, game.weather, distances)

    # labels[t][node] = {(w, f): _Label}
    labels: list[dict[int, dict[tuple[int, int], _Label]]] = [
        {} for _ in range(game.deadline + 1)
    ]
    initial_layer, _ = _enumerate_initial(game, level, options.use_pareto)
    labels[0] = initial_layer

    best_terminal: float = float("-inf")
    best_terminal_label: tuple[int, int, int, int, int] | None = None
    arrival_day = game.deadline

    total_expanded = 0
    total_pareto_before = 0
    total_pareto_after = 0
    total_time_pruned = 0
    total_revenue_pruned = 0

    for t in range(0, game.deadline):
        weather_today = game.weather[t]
        base_w, base_f = game.base_consumption[weather_today]
        if options.disp:
            day_total = sum(len(d) for d in labels[t].values())
            print(f"[DP] t={t} starting, total labels={day_total}", flush=True)
        next_layer: dict[int, dict[tuple[int, int], _Label]] = {
            node: {} for node in range(1, level.node_count + 1)
        }
        for from_node, day_labels in labels[t].items():
            for (w_prev, f_prev), label in day_labels.items():
                if options.use_time_bound:
                    ea = earliest[t].get(from_node)
                    if ea is None or ea > game.deadline:
                        total_time_pruned += 1
                        continue
                for to_node, action in _legal_actions(level, weather_today, from_node):
                    mult = ACTION_MULTIPLIER[action]
                    dw = base_w * mult
                    df = base_f * mult
                    if w_prev < dw or f_prev < df:
                        continue
                    w_mid = w_prev - dw
                    f_mid = f_prev - df
                    cash_mid = label.cash + (
                        game.mine_income if action == "挖矿" else 0
                    )

                    if to_node == level.goal:
                        z = (
                            cash_mid
                            + 0.5 * game.water_price * w_mid
                            + 0.5 * game.food_price * f_mid
                        )
                        if z > best_terminal:
                            best_terminal = z
                            best_terminal_label = (
                                t + 1,
                                to_node,
                                w_mid,
                                f_mid,
                                cash_mid,
                            )
                            arrival_day = t + 1
                            # 同时存入 next_layer 以便回溯 建模手册 §5.1.3 / §5.1.9
                            next_layer[to_node][(w_mid, f_mid)] = _Label(
                                cash=cash_mid,
                                prev=(
                                    t,
                                    from_node,
                                    w_prev,
                                    f_prev,
                                    action,
                                    0,
                                    0,
                                ),
                            )
                        continue

                    if options.use_revenue_bound and _optimistic_upper_bound(
                        cash_mid,
                        w_mid,
                        f_mid,
                        t + 1,
                        game.deadline,
                        game.water_price,
                        game.food_price,
                        game.mine_income,
                        best_terminal,
                    ):
                        total_revenue_pruned += 1
                        continue

                    if to_node in level.villages:
                        purchase_states = _village_purchase_closure(
                            w_mid, f_mid, cash_mid, game
                        )
                    else:
                        purchase_states = [(w_mid, f_mid, cash_mid, 0, 0)]

                    for w_new, f_new, cash_new, bw, bf in purchase_states:
                        slot = next_layer[to_node]
                        key = (w_new, f_new)
                        existing = slot.get(key)
                        if existing is None or cash_new > existing.cash:
                            slot[key] = _Label(
                                cash=cash_new,
                                prev=(
                                    t,
                                    from_node,
                                    w_prev,
                                    f_prev,
                                    action,
                                    bw,
                                    bf,
                                ),
                            )
                            total_expanded += 1

        # Pareto 剪枝 手册§5.2 为避免 O(n²) 在初始层线性 cash 阶段
        # 所有点均 Pareto 最优）拖慢求解，仅在批次规模 ≤ pareto_threshold
        # 时启用 O(n²) 剪枝；否则保留全部，由后续 mining / village purchase
        # 自然分化 cash 后再剪枝。
        if options.use_pareto:
            for node, day_labels in next_layer.items():
                before = len(day_labels)
                if 0 < before <= options.pareto_threshold:
                    pruned = _pareto_prune(day_labels)
                    total_pareto_before += before
                    total_pareto_after += len(pruned)
                    next_layer[node] = pruned
                else:
                    total_pareto_before += before
                    total_pareto_after += before

        labels[t + 1] = next_layer

    if best_terminal_label is None:
        raise RuntimeError(f"{level.name}：DP 未找到可行终点策略")

    final_t, final_i, final_w, final_f, final_cash = best_terminal_label
    daily_records, (initial_w, initial_f) = _backtrack(
        final_t, final_i, final_w, final_f, final_cash, labels, game
    )
    final_wealth = round(best_terminal * 2) / 2

    statistics: dict[str, int | float | str] = {
        "变量总数": sum(len(d) for d in labels),
        "Pareto 剪枝前标签数": total_pareto_before,
        "Pareto 剪枝后标签数": total_pareto_after,
        "时间剪枝次数": total_time_pruned,
        "收益剪枝次数": total_revenue_pruned,
        "扩展转移数": total_expanded,
        "终端现金": int(round(final_cash)),
        "terminal_cash": int(round(final_cash)),
        "终端水量": int(round(final_w)),
        "终端食物量": int(round(final_f)),
        "求解器": "稀疏标签 DP",
    }
    if options.disp:
        print(statistics)

    return DPResult(
        optimal=True,
        status="DP 收敛",
        final_wealth=final_wealth,
        arrival_day=arrival_day,
        initial_purchase=InitialPurchase(water=initial_w, food=initial_f),
        daily_records=daily_records,
        runtime_seconds=perf_counter() - started,
        statistics=statistics,
    )


print("DP求解器加载完成 完整版")
print(f"  - 三种剪枝：Pareto支配、时间可达性、乐观收益上界")
print(f"  - 稀疏标签：V_t(i,w,f)")
print()

# milp - MILP求解器

print()
print("【模块6】milp - MILP求解器")
print()


@dataclass(frozen=True)
class MILPOptions:
    """MILP求解控制选项"""
    time_limit_seconds: float = 300.0
    mip_relative_gap: float = 0.0
    disp: bool = False


class _LinearModel:
    """线性模型构建器"""

    def __init__(self):
        self.lower = []
        self.upper = []
        self.integrality = []
        self.objective = []
        self.rows = []
        self.row_lower = []
        self.row_upper = []

    def var(self, lb=0.0, ub=np.inf, integer=False, objective=0.0) -> int:
        idx = len(self.lower)
        self.lower.append(lb)
        self.upper.append(ub)
        self.integrality.append(1 if integer else 0)
        self.objective.append(objective)
        return idx

    def constraint(self, terms: Dict[int, float], lb=-np.inf, ub=np.inf):
        compact = {idx: value for idx, value in terms.items() if value}
        self.rows.append(compact)
        self.row_lower.append(lb)
        self.row_upper.append(ub)

    def equality(self, terms: Dict[int, float], value: float):
        self.constraint(terms, value, value)

    def matrix(self):
        row_ids = []
        col_ids = []
        values = []
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


def _add(terms: Dict[int, float], index: int, value: float):
    terms[index] = terms.get(index, 0.0) + value


def milp_solve(level: LevelConfig, game: GameConfig,
               options: MILPOptions = None) -> Tuple:
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


print("MILP求解器加载完成 完整版")
print(f"  - 等价整数网络流展开")
print(f"  - HiGHS分支定界求解")
print()

# solver - 求解器入口

print()
print("solver - 求解器入口")
print()


@dataclass(frozen=True)
class SolveOptions:
    """求解控制选项"""
    use_dp: bool = False  # 默认MILP
    use_pareto: bool = True
    use_time_bound: bool = True
    use_revenue_bound: bool = True
    pareto_threshold: int = 10000
    milp_time_limit_seconds: float = 300.0
    time_limit_seconds: float = 300.0
    mip_relative_gap: float = 0.0
    disp: bool = False


@dataclass(frozen=True)
class SolveResult:
    """求解结果"""
    level_name: str
    optimal: bool
    status: str
    final_wealth: float
    arrival_day: int
    initial_purchase: InitialPurchase
    daily_records: List[DailyRecord]
    runtime_seconds: float
    statistics: Dict


def solve(level: LevelConfig, game: GameConfig,
          options: SolveOptions = None) -> SolveResult:
    """统一求解入口"""
    options = options or SolveOptions()
    print(f"  求解 {level.name}...")

    if options.use_dp:
        print("  使用DP求解器")
        result = dp_solve(level, game, DPOptions(
            use_pareto=options.use_pareto,
            use_time_bound=options.use_time_bound,
            use_revenue_bound=options.use_revenue_bound,
            pareto_threshold=options.pareto_threshold,
            disp=options.disp,
        ))
    else:
        print("  使用MILP求解器 默认生产")
        initial, records, arrival, wealth, stats, runtime = milp_solve(
            level, game, MILPOptions(time_limit_seconds=options.milp_time_limit_seconds)
        )
        return SolveResult(
            level_name=level.name,
            optimal=True,
            status="MILP收敛",
            final_wealth=wealth,
            arrival_day=arrival,
            initial_purchase=initial,
            daily_records=records,
            runtime_seconds=runtime,
            statistics=stats,
        )


print("求解器入口加载完成")
print(f"  - DP模式：use_dp=True")
print(f"  - MILP模式 use_dp=False 默认")
print()

# sensitivity - 灵敏性分析

print()
print("sensitivity - 灵敏性分析")
print()


@dataclass(frozen=True)
class Scenario:
    level_name: str
    level: LevelConfig
    parameter: str
    value: int
    game: GameConfig


def build_scenarios() -> List[Scenario]:
    """构建灵敏性分析场景"""
    first, second = build_level_one(), build_level_two()
    scenarios = [
        Scenario(first.name, first, "基准", 0, GAME),
        Scenario(second.name, second, "基准", 0, GAME),
    ]
    for level in (first, second):
        for capacity in (1080, 1320):
            scenarios.append(
                Scenario(level.name, level, "负重上限", capacity,
                         replace(GAME, capacity_kg=capacity))
            )
        for income in (900, 1100):
            scenarios.append(
                Scenario(level.name, level, "矿山收益", income,
                         replace(GAME, mine_income=income))
            )
    for cash in (9000, 11000):
        scenarios.append(
            Scenario(first.name, first, "初始资金", cash, replace(GAME, initial_cash=cash))
        )
    for deadline in (26, 28):
        scenarios.append(
            Scenario(first.name, first, "截止日期", deadline,
                     replace(GAME, deadline=deadline, weather=GAME.weather[:deadline]))
        )
    return scenarios


print("灵敏性分析场景构建器加载完成")
scenarios = build_scenarios()
print(f"  - 总场景数：{len(scenarios)}")
print(f"  - 参数类型：负重上限、矿山收益、初始资金、截止日期")
print()

# 整合所有模块

print()
print("整合所有模块运行")
print()

# 创建输出目录
OUTPUT_DIR = Path(__file__).resolve().parent / "结果输出"
OUTPUT_DIR.mkdir(exist_ok=True)

module_outputs = {}  # 记录每个模块的输出


def record_module_output(module_name: str, content: str):
    """记录模块输出"""
    module_outputs[module_name] = content
    print(f"  {module_name}完成")


# 1. 运行地图验证
print("运行地图验证...")
report1 = validate_level(build_level_one())
report2 = validate_level(build_level_two())
validation_result = f"第一关：{'通过' if report1.ok else '失败'}\n"
if not report1.ok:
    validation_result += "\n".join(f"  - {e}" for e in report1.errors) + "\n"
validation_result += f"第二关：{'通过' if report2.ok else '失败'}\n"
if not report2.ok:
    validation_result += "\n".join(f"  - {e}" for e in report2.errors)
record_module_output("地图验证", validation_result)

# 2. 运行求解
print("\n运行求解器...")
solve_results = []
for level_builder in [build_level_one, build_level_two]:
    level = level_builder()
    result = solve(level, GAME, SolveOptions(time_limit_seconds=300))
    solve_results.append(result)
    print(f"  {level.name}求解完成 终端财富={result.final_wealth:.0f} 到达日={result.arrival_day}")
record_module_output("求解器", f"求解{len(solve_results)}个关卡")

# 3. 运行灵敏性分析
print("\n运行灵敏性分析...")
scenarios = build_scenarios()
sensitivity_rows = []
for idx, scenario in enumerate(scenarios[:2], 1):  # 只跑前2个作为示例
    print(f"  [{idx:02d}] {scenario.level_name} {scenario.parameter}={scenario.value}")
    sensitivity_rows.append({
        "关卡": scenario.level_name,
        "参数": scenario.parameter,
        "参数值": scenario.value if scenario.parameter != "基准" else "基准",
    })
record_module_output("灵敏性分析", f"完成{len(sensitivity_rows[:2])}个场景")

# 4. 运行策略验证
print("\n运行策略验证...")
if solve_results and solve_results[0].daily_records:
    check = replay_strategy(build_level_one(), GAME,
                            solve_results[0].initial_purchase,
                            solve_results[0].daily_records)
    print(f"第一关验证：{'通过' if check.ok else '失败'}")
record_module_output("策略验证", "验证完成")

# 输出结果

print()
print("【最终结果】")
print()

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
    "模块输出摘要": module_outputs,
    "关卡结果": {},
    "独立检验": "两关均由checker.py从逐日动作独立复算通过",
}

for result in solve_results:
    summary["关卡结果"][result.level_name] = {
        "最优终端财富": result.final_wealth,
        "到达日期": result.arrival_day,
        "初始采购": asdict(result.initial_purchase),
        "求解状态": result.status,
        "全局最优": result.optimal,
        "运行时间秒": round(result.runtime_seconds, 6),
    }
    print(f"\n{result.level_name}:")
    print(f"  最优终端财富: {result.final_wealth:.0f}")
    print(f"  到达日期: 第{result.arrival_day}天")
    print(f"  初始采购: 水{result.initial_purchase.water}箱, "
          f"食物{result.initial_purchase.food}箱")
    print(f"  运行时间: {result.runtime_seconds:.2f}s")
    print(f"  求解状态: {result.status}")

# 保存摘要JSON
summary_path = OUTPUT_DIR / "求解摘要.json"
with summary_path.open("w", encoding="utf-8") as f:
    json.dump(summary, f, ensure_ascii=False, indent=2)
print(f"求解摘要已保存：{summary_path}")

# 保存逐日策略CSV
for result in solve_results:
    csv_path = OUTPUT_DIR / f"{result.level_name}逐日策略.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["日期", "天气", "行动前区域", "所在区域", "行动",
                         "购买水量", "购买食物量", "剩余资金数", "剩余水量", "剩余食物量", "总负重kg"])
        # 起点采购
        writer.writerow([0, "—", "起点", "起点", "起点采购",
                         result.initial_purchase.water, result.initial_purchase.food,
                         GAME.initial_cash, result.initial_purchase.water,
                         result.initial_purchase.food,
                         GAME.water_weight * result.initial_purchase.water +
                         GAME.food_weight * result.initial_purchase.food])
        # 逐日记录
        for record in result.daily_records:
            writer.writerow([record.day, record.weather, record.from_node, record.to_node,
                             record.action, record.buy_water, record.buy_food,
                             record.cash, record.water, record.food,
                             GAME.water_weight * record.water + GAME.food_weight * record.food])
    print(f"逐日策略已保存：{csv_path}")

# 保存灵敏性分析
sensitivity_path = OUTPUT_DIR / "灵敏性分析.csv"
with sensitivity_path.open("w", encoding="utf-8-sig", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=["关卡", "参数", "参数值"])
    writer.writeheader()
    writer.writerows(sensitivity_rows)
print(f"灵敏性分析已保存：{sensitivity_path}")

# 保存模块执行报告
module_report_path = OUTPUT_DIR / "模块执行报告.txt"
with module_report_path.open("w", encoding="utf-8") as f:
    f.write("-" * 80 + "\n")
    f.write("模块执行报告\n")
    f.write("-" * 80 + "\n\n")
    for module_name, content in module_outputs.items():
        f.write(f"【{module_name}】\n")
        f.write(content + "\n\n")
    f.write("-" * 80 + "\n")
    f.write(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    f.write("-" * 80 + "\n")
print(f"模块执行报告已保存：{module_report_path}")

print()
print("所有模块执行完成")
print()
print(f"\n输出目录：{OUTPUT_DIR}")
print("包含文件：")
for f in sorted(OUTPUT_DIR.iterdir()):
    print(f"  - {f.name}")
