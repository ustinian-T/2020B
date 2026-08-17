"""完全信息 Oracle DP（建模手册 §8.3.3）：用于计算 Regret 上界。

两关统一入口 ``solve_oracle``，根据关卡是否含村庄自动选择实现：
- Q3 路径（无村庄）：原 Pareto 标签 DP，不允许非起点购买
- Q4 路径（有村庄）：稀疏标签 DP（含村庄补给闭包、Pareto 剪枝、
  时间下界、乐观收益上界），与第一问 [dp.py](求解代码/第一问/模型求解/dp.py) 同模式

完全信息玩家在第 0 天知道完整天气序列，可绕路、挖矿、补矿，
因此 Oracle 提供"已知未来天气下的最优终端财富"上界，用于 Regret 计算。
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from time import perf_counter

from .config import GameConfig, LevelConfig
from .preprocess import bfs_distances
from .pareto_utils import optimistic_upper_bound_3d
from .transition import (
    ACTION_MULTIPLIER,
    Action,
    State,
    apply_action,
    feasible_actions,
    terminal_wealth,
    total_weight,
)


# ─────────────────────────────────────────────────────────────────────────────
# 数据结构
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class OracleResult:
    final_wealth: float
    initial_water: int
    initial_food: int
    initial_cash: int
    arrival_day: int
    actions: tuple
    records: tuple


# ─────────────────────────────────────────────────────────────────────────────
# Q3 路径：无村庄 + Pareto 标签 DP
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class _Q3Label:
    node: int
    water_used: int
    food_used: int
    cash_used: int
    mine_income: int
    actions: tuple


def _q3_dominates(left: _Q3Label, right: _Q3Label) -> bool:
    return (
        left.water_used <= right.water_used
        and left.food_used <= right.food_used
        and left.cash_used <= right.cash_used
        and left.mine_income >= right.mine_income
        and (
            left.water_used < right.water_used
            or left.food_used < right.food_used
            or left.cash_used < right.cash_used
            or left.mine_income > right.mine_income
        )
    )


def _q3_insert_pareto(frontier: list[_Q3Label], candidate: _Q3Label) -> None:
    for existing in frontier:
        if (
            existing.water_used == candidate.water_used
            and existing.food_used == candidate.food_used
            and existing.cash_used <= candidate.cash_used
            and existing.mine_income >= candidate.mine_income
        ) or _q3_dominates(existing, candidate):
            return
    frontier[:] = [item for item in frontier if not _q3_dominates(candidate, item)]
    frontier.append(candidate)


def _solve_oracle_q3(
    level: LevelConfig, game: GameConfig, weather_sequence: tuple[str, ...]
) -> OracleResult:
    """Q3 路径：完全信息玩家在已知天气下做最优选择（无村庄购买）。"""
    if len(weather_sequence) != game.deadline:
        raise ValueError("Oracle 天气序列长度必须等于关卡截止日")
    if level.villages:
        raise ValueError("Q3 路径不处理村庄，请使用 solve_oracle(level, game, seq) 自动调度")

    frontier: dict[int, list[_Q3Label]] = {
        level.start: [_Q3Label(level.start, 0, 0, 0, 0, ())]
    }
    terminal: list[tuple[_Q3Label, int]] = []
    for day, weather in enumerate(weather_sequence, start=1):
        next_frontier: dict[int, list[_Q3Label]] = {}
        base_water, base_food = game.base_consumption[weather]
        for labels in frontier.values():
            for label in labels:
                dummy = State(label.node, 0, 0, 0)
                for action in feasible_actions(dummy, weather, level):
                    multiplier = ACTION_MULTIPLIER[action.kind]
                    water_used = label.water_used + multiplier * base_water
                    food_used = label.food_used + multiplier * base_food
                    if (
                        game.water_weight * water_used + game.food_weight * food_used
                        > game.capacity_kg
                    ):
                        continue
                    if (
                        game.water_price * water_used + game.food_price * food_used
                        > game.initial_cash
                    ):
                        continue
                    candidate = _Q3Label(
                        node=action.destination,
                        water_used=water_used,
                        food_used=food_used,
                        cash_used=label.cash_used,
                        mine_income=label.mine_income
                        + (game.mine_income if action.kind == "挖矿" else 0),
                        actions=label.actions + (action,),
                    )
                    if candidate.node == level.goal:
                        terminal.append((candidate, day))
                    elif day < game.deadline:
                        _q3_insert_pareto(
                            next_frontier.setdefault(candidate.node, []), candidate
                        )
        frontier = next_frontier

    if not terminal:
        raise RuntimeError("给定天气情景下不存在截止日前可行的 Oracle 路径")

    def score(item: tuple[_Q3Label, int]) -> tuple[float, int, int, int]:
        label, arrival = item
        wealth = (
            game.initial_cash
            - game.water_price * label.water_used
            - game.food_price * label.food_used
            + label.mine_income
        )
        return wealth, -arrival, -label.water_used, -label.food_used

    best, arrival_day = max(terminal, key=score)
    initial_cash = (
        game.initial_cash
        - game.water_price * best.water_used
        - game.food_price * best.food_used
    )
    state = State(level.start, best.water_used, best.food_used, initial_cash)
    records = []
    from .robust_dp_q3 import DailyRecord  # 避免循环导入
    for day, (weather, action) in enumerate(
        zip(weather_sequence, best.actions), start=1
    ):
        previous = state
        state = apply_action(state, action, weather, level, game)
        records.append(
            DailyRecord(
                day=day,
                weather=weather,
                from_node=previous.node,
                to_node=state.node,
                action=action.kind,
                buy_water=0,
                buy_food=0,
                cash=state.cash,
                water=state.water,
                food=state.food,
                weight=total_weight(state, game),
                robust_value=float("nan"),
                nominal_value=float("nan"),
            )
        )
        if state.node == level.goal:
            break
    return OracleResult(
        final_wealth=terminal_wealth(state, game),
        initial_water=best.water_used,
        initial_food=best.food_used,
        initial_cash=initial_cash,
        arrival_day=arrival_day,
        actions=best.actions,
        records=tuple(records),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Q4 路径：含村庄 + 稀疏标签 DP（与第一问 dp.py 同模式）
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class _Q4Label:
    """稀疏标签：状态下最大现金 + 前驱指针。

    键 = (t, node, w, f)；值 = _Q4Label。cash 是该 (w, f) 下的最大剩余现金；
    Pareto 剪枝在每个 (t, node) 桶内做。
    """

    cash: int
    prev: tuple | None  # (prev_t, prev_node, prev_w, prev_f, action_kind, bw, bf, action_dest)


def _q4_pareto_prune(
    labels: dict[tuple[int, int], _Q4Label],
    threshold: int = 10_000,
) -> dict[tuple[int, int], _Q4Label]:
    """Q4 标签 Pareto 剪枝（沿用第一问 [dp.py:92-135] 的 2D frontier 模式）。"""
    if not labels:
        return labels
    if len(labels) > threshold:
        return labels
    # 同 (w, f) 保留最大 cash
    best: dict[tuple[int, int], _Q4Label] = {}
    for key, label in labels.items():
        existing = best.get(key)
        if existing is None or label.cash > existing.cash:
            best[key] = label
    # 按 w 降序、cash 降序、f 升序排列
    items = sorted(best.items(), key=lambda kv: (-kv[0][0], -kv[1].cash, kv[0][1]))
    kept: dict[tuple[int, int], _Q4Label] = {}
    front_f: list[int] = []
    front_cash: list[int] = []
    for key, label in items:
        w, f = key
        dominated = False
        for ff, fc in zip(front_f, front_cash):
            if ff >= f and fc >= label.cash and (ff > f or fc > label.cash):
                dominated = True
                break
        if dominated:
            continue
        new_f: list[int] = []
        new_c: list[int] = []
        for ff, fc in zip(front_f, front_cash):
            if not (ff <= f and fc <= label.cash):
                new_f.append(ff)
                new_c.append(fc)
        front_f = new_f
        front_cash = new_c
        front_f.append(f)
        front_cash.append(label.cash)
        kept[key] = label
    return kept


def _q4_village_closure(
    w_after: int,
    f_after: int,
    cash_after: int,
    game: GameConfig,
) -> list[tuple[int, int, int, int, int]]:
    """Q4 村庄补给闭包（沿用第一问 [dp.py:189-219]）。"""
    candidates: list[tuple[int, int, int, int, int]] = []
    max_water = game.capacity_kg // game.water_weight
    max_food = game.capacity_kg // game.food_weight
    if cash_after < 0:
        return candidates
    for bw in range(0, max(0, max_water - w_after) + 1):
        cost_w = 2 * game.water_price * bw
        if cost_w > cash_after:
            break
        for bf in range(0, max(0, max_food - f_after) + 1):
            cost = cost_w + 2 * game.food_price * bf
            if cost > cash_after:
                break
            w_new = w_after + bw
            f_new = f_after + bf
            if game.water_weight * w_new + game.food_weight * f_new > game.capacity_kg:
                continue
            candidates.append((w_new, f_new, cash_after - cost, bw, bf))
    if not candidates:
        candidates.append((w_after, f_after, cash_after, 0, 0))
    return candidates


def _q4_earliest_arrival(
    t: int,
    dist: int,
    deadline: int,
    weather: tuple[str, ...],
) -> int | None:
    """从第 t 天末出发到目标的理论最早日期（沙暴日不算移动日）。"""
    if dist == 0:
        return t
    needed = dist
    for q in range(t + 1, deadline + 1):
        if weather[q - 1] != "沙暴":
            needed -= 1
            if needed == 0:
                return q
    return None


def _q4_precompute_earliest(
    deadline: int,
    weather: tuple[str, ...],
    distances: dict[int, int],
) -> dict[int, dict[int, int | None]]:
    """每个 (day, node) 的最早到达日。"""
    table: dict[int, dict[int, int | None]] = {}
    for t in range(0, deadline + 1):
        table[t] = {
            node: _q4_earliest_arrival(t, dist, deadline, weather)
            for node, dist in distances.items()
        }
    return table


def _q4_optimistic_bound(
    cash: int,
    w: int,
    f: int,
    t: int,
    deadline: int,
    game: GameConfig,
) -> float:
    """乐观收益上界（与第一问 [dp.py:222-247] 同公式）。"""
    return optimistic_upper_bound_3d(
        w,
        f,
        cash,
        deadline,
        t,
        game.water_price,
        game.food_price,
        game.mine_income,
    )


def _q4_legal_actions(level: LevelConfig, weather_today: str, from_node: int):
    """合法动作（沿用第一问 [dp.py:171-186]）。"""
    actions = []
    if from_node == level.goal:
        return actions
    if weather_today != "沙暴":
        for neighbor in level.neighbors[from_node]:
            actions.append(Action("行走", neighbor))
    if from_node in level.mines:
        actions.append(Action("挖矿", from_node))
    actions.append(Action("停留", from_node))
    return actions


def _q4_backtrack(
    final_t: int,
    final_i: int,
    final_w: int,
    final_f: int,
    final_cash: int,
    labels: list[dict[int, dict[tuple[int, int], _Q4Label]]],
    level: LevelConfig,
    game: GameConfig,
    weather: tuple[str, ...],
) -> tuple[list, tuple[int, int, int]]:
    """从终态标签逆推得到逐日动作、采购记录与起点采购组合。"""
    from .robust_dp_q3 import DailyRecord
    chain: list[tuple[int, int, int, int, int, int, int, int, int]] = []
    t = final_t
    i = final_i
    w = final_w
    f = final_f
    initial_w: int | None = None
    initial_f: int | None = None
    initial_cash: int | None = None
    while t > 0:
        label = labels[t][i][(w, f)]
        assert label.prev is not None
        prev_t, prev_i, prev_w, prev_f, action_kind, bw, bf, action_dest = label.prev
        chain.append((t, prev_i, i, action_kind, bw, bf, label.cash, w, f))
        t, i, w, f = prev_t, prev_i, prev_w, prev_f
        if t == 0:
            initial_w, initial_f = w, f
            initial_cash = labels[0][level.start][(w, f)].cash
    assert initial_w is not None and initial_f is not None
    chain.reverse()
    records: list[DailyRecord] = []
    for t, prev_i, cur_i, action_kind, bw, bf, cash, w, f in chain:
        records.append(
            DailyRecord(
                day=t,
                weather=weather[t - 1],
                from_node=prev_i,
                to_node=cur_i,
                action=action_kind,
                buy_water=bw,
                buy_food=bf,
                cash=cash,
                water=w,
                food=f,
                weight=total_weight(State(cur_i, w, f, cash), game),
                robust_value=float("nan"),
                nominal_value=float("nan"),
            )
        )
    return records, (initial_w, initial_f, initial_cash or 0)


def _solve_oracle_q4(
    level: LevelConfig, game: GameConfig, weather_sequence: tuple[str, ...]
) -> OracleResult:
    """Q4 路径：含村庄购买的稀疏标签 Oracle DP（沿用第一问 dp.py 模式）。"""
    if len(weather_sequence) != game.deadline:
        raise ValueError("Oracle 天气序列长度必须等于关卡截止日")
    distances = bfs_distances(level, level.goal)
    earliest = _q4_precompute_earliest(game.deadline, weather_sequence, distances)

    # labels[t][node][(w, f)] = _Q4Label(cash, prev)
    labels: list[dict[int, dict[tuple[int, int], _Q4Label]]] = [
        {} for _ in range(game.deadline + 1)
    ]

    # Day 0: 起点采购
    max_water = game.capacity_kg // game.water_weight
    max_food = game.capacity_kg // game.food_weight
    initial_layer: dict[tuple[int, int], _Q4Label] = {}
    for w in range(0, max_water + 1):
        cost_w = game.water_price * w
        if cost_w > game.initial_cash:
            break
        max_f_budget = (game.initial_cash - cost_w) // game.food_price
        max_f_weight = (game.capacity_kg - game.water_weight * w) // game.food_weight
        max_f = min(max_f_budget, max_f_weight, max_food)
        for f in range(0, max_f + 1):
            cash = game.initial_cash - cost_w - game.food_price * f
            initial_layer[(w, f)] = _Q4Label(cash=cash, prev=None)
    labels[0] = {level.start: initial_layer}

    best_terminal: float = float("-inf")
    best_terminal_label: tuple[int, int, int, int, int] | None = None
    arrival_day = game.deadline

    for t in range(0, game.deadline):
        weather_today = weather_sequence[t]
        base_w, base_f = game.base_consumption[weather_today]
        next_layer: dict[int, dict[tuple[int, int], _Q4Label]] = {
            node: {} for node in range(1, level.node_count + 1)
        }
        for from_node, day_labels in labels[t].items():
            for (w_prev, f_prev), label in day_labels.items():
                # 时间下界
                ea = earliest[t].get(from_node)
                if ea is None or ea > game.deadline:
                    continue
                # 乐观收益上界
                if _q4_optimistic_bound(label.cash, w_prev, f_prev, t, game.deadline, game) <= best_terminal:
                    continue
                for action in _q4_legal_actions(level, weather_today, from_node):
                    mult = ACTION_MULTIPLIER[action.kind]
                    dw = base_w * mult
                    df = base_f * mult
                    if w_prev < dw or f_prev < df:
                        continue
                    w_mid = w_prev - dw
                    f_mid = f_prev - df
                    cash_mid = label.cash + (
                        game.mine_income if action.kind == "挖矿" else 0
                    )

                    if action.destination == level.goal:
                        z = (
                            cash_mid
                            + 0.5 * game.water_price * w_mid
                            + 0.5 * game.food_price * f_mid
                        )
                        if z > best_terminal:
                            best_terminal = z
                            best_terminal_label = (
                                t + 1,
                                level.goal,
                                w_mid,
                                f_mid,
                                cash_mid,
                            )
                            arrival_day = t + 1
                            next_layer[level.goal][(w_mid, f_mid)] = _Q4Label(
                                cash=cash_mid,
                                prev=(
                                    t, from_node, w_prev, f_prev,
                                    action.kind, 0, 0, action.destination,
                                ),
                            )
                        continue

                    # 村庄补给闭包
                    if action.destination in level.villages:
                        purchase_states = _q4_village_closure(w_mid, f_mid, cash_mid, game)
                    else:
                        purchase_states = [(w_mid, f_mid, cash_mid, 0, 0)]

                    for w_new, f_new, cash_new, bw, bf in purchase_states:
                        slot = next_layer[action.destination]
                        key = (w_new, f_new)
                        existing = slot.get(key)
                        if existing is None or cash_new > existing.cash:
                            slot[key] = _Q4Label(
                                cash=cash_new,
                                prev=(
                                    t, from_node, w_prev, f_prev,
                                    action.kind, bw, bf, action.destination,
                                ),
                            )
        # Pareto 剪枝
        for node, day_labels in next_layer.items():
            if day_labels:
                next_layer[node] = _q4_pareto_prune(day_labels)
        labels[t + 1] = next_layer

    if best_terminal_label is None:
        raise RuntimeError(f"{level.name}：Oracle DP 未找到可行终点策略")

    final_t, final_i, final_w, final_f, final_cash = best_terminal_label
    records, (initial_w, initial_f, initial_cash) = _q4_backtrack(
        final_t, final_i, final_w, final_f, final_cash,
        labels, level, game, weather_sequence,
    )
    return OracleResult(
        final_wealth=round(best_terminal * 2) / 2,
        initial_water=initial_w,
        initial_food=initial_f,
        initial_cash=initial_cash,
        arrival_day=arrival_day,
        actions=tuple(record.action for record in records),
        records=tuple(records),
    )


# ─────────────────────────────────────────────────────────────────────────────
# 统一入口
# ─────────────────────────────────────────────────────────────────────────────


def solve_oracle(
    level: LevelConfig,
    game: GameConfig,
    weather_sequence: tuple[str, ...],
) -> OracleResult:
    """统一入口：根据关卡是否含村庄自动选择 Q3 / Q4 实现。"""
    if not level.villages:
        return _solve_oracle_q3(level, game, weather_sequence)
    return _solve_oracle_q4(level, game, weather_sequence)