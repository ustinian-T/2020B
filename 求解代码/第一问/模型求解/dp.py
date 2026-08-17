"""第一问稀疏标签动态规划（主模型）。

实现建模手册 §5 / 求解流程图所描述的精确动态规划：
    - 状态 S_t = (t, i, W, F)，价值 V_t(i, w, f) 保存该状态可达到的最大现金；
    - 三种精确剪枝：Pareto 支配剪枝（§5.2）、时间可达性剪枝（§5.3）、
      乐观收益上界剪枝（§5.4）；
    - 起点采购一次（§5.1.4）、村庄补给闭包（§5.1.8）、终点吸收（§5.1.3 / §5.1.9）。

详细建模语义、约束编号、剪枝依据和复杂度说明见
`建模文件/第一问建模手册_已知天气单玩家最优策略.docx`。
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from time import perf_counter

from .checker import DailyRecord, InitialPurchase
from .config import GameConfig, LevelConfig


# 行动消耗倍率 κ(a)：停留 1、行走 2、挖矿 3（手册 §5.1.5，公式 5.5）。
ACTION_MULTIPLIER = {"停留": 1, "行走": 2, "挖矿": 3}


@dataclass(frozen=True)
class DPOptions:
    """DP 求解控制选项（建模手册 §2.3：MILP 仅作可选验证，DP 为主模型）。"""

    use_pareto: bool = True
    use_time_bound: bool = True
    use_revenue_bound: bool = True
    pareto_threshold: int = 10000
    disp: bool = False


@dataclass(frozen=True)
class _Label:
    """稀疏标签：状态 (t, i, w, f) 下的最大现金 + 前驱指针。"""

    cash: int
    prev: tuple[int, int, int, int, str, int, int] | None


def _bfs_distances(level: LevelConfig, target: int) -> dict[int, int]:
    """节点到 target 的最少移动步数（边权均为 1）。"""
    distances: dict[int, int] = {target: 0}
    queue = deque([target])
    while queue:
        node = queue.popleft()
        for neighbor in level.neighbors[node]:
            if neighbor not in distances:
                distances[neighbor] = distances[node] + 1
                queue.append(neighbor)
    return distances


def _earliest_arrival(
    t: int,
    dist: int,
    deadline: int,
    weather: tuple[str, ...],
) -> int | None:
    """从第 t 天末出发到目标的理论最早日期（手册 §5.3）。"""
    if dist == 0:
        return t
    needed = dist
    for q in range(t + 1, deadline + 1):
        if weather[q - 1] != "沙暴":
            needed -= 1
            if needed == 0:
                return q
    return None


def _precompute_earliest(
    deadline: int,
    weather: tuple[str, ...],
    distances: dict[int, int],
) -> dict[int, dict[int, int | None]]:
    """每个 (day, node) 的最早到达日。"""
    table: dict[int, dict[int, int | None]] = {}
    for t in range(0, deadline + 1):
        table[t] = {
            node: _earliest_arrival(t, dist, deadline, weather)
            for node, dist in distances.items()
        }
    return table


def _pareto_prune(
    labels: dict[tuple[int, int], _Label],
) -> dict[tuple[int, int], _Label]:
    """Pareto 支配剪枝（手册 §5.2）。

    同一 (t, i) 下，若 A 的 (w, f, cash) 均 ≥ B 且至少一项严格更优，则 B 被支配。
    实现：按 w 降序扫描，每步把已保留点中 (f, cash) 维护成 2D Pareto 前沿，
    使新点的支配检查成为 O(frontier_size)。
    """
    if not labels:
        return labels
    # 同 (w, f) 只保留 cash 最大者。
    best: dict[tuple[int, int], _Label] = {}
    for key, label in labels.items():
        existing = best.get(key)
        if existing is None or label.cash > existing.cash:
            best[key] = label
    items = sorted(best.items(), key=lambda kv: (-kv[0][0], -kv[1].cash, kv[0][1]))
    kept: dict[tuple[int, int], _Label] = {}
    # 2D Pareto 前沿（按 f 升序、cash 升序的扫描线维护）。
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
        # 清理被新点支配的旧前沿项。
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


def _enumerate_initial(
    game: GameConfig,
    level: LevelConfig,
    pareto: bool,
) -> tuple[dict[int, dict[tuple[int, int], _Label]], tuple[int, int]]:
    """枚举第 0 天起点采购状态（手册 §5.1.4）。

    完整枚举所有满足预算 + 负重 + 非负约束的整数 (w, f) 组合。
    初始层中所有点互不支配（cash = C0 − 5w − 10f 单调），
    故 Pareto 剪枝在初始层不会削减规模；后续扩展中再由 §5.2 逐步剪枝。
    """
    labels_at_start: dict[tuple[int, int], _Label] = {}
    max_water = game.capacity_kg // game.water_weight
    max_food = game.capacity_kg // game.food_weight
    for w in range(0, max_water + 1):
        cost_w = game.water_price * w
        if cost_w > game.initial_cash:
            break
        max_f_budget = (game.initial_cash - cost_w) // game.food_price
        max_f_weight = (game.capacity_kg - game.water_weight * w) // game.food_weight
        max_f = min(max_f_budget, max_f_weight, max_food)
        for f in range(0, max_f + 1):
            cost = cost_w + game.food_price * f
            cash = game.initial_cash - cost
            labels_at_start[(w, f)] = _Label(cash=cash, prev=None)
    # 初始层 Pareto 剪枝在 cash = C0 − 5w − 10f 的线性阶段不削减规模，
    # O(n²) 调用只会拖慢启动。仅在规模较小时才执行。
    if pareto and len(labels_at_start) <= 2000:
        labels_at_start = _pareto_prune(labels_at_start)
    wrapped: dict[int, dict[tuple[int, int], _Label]] = {level.start: labels_at_start}
    return wrapped, (0, 0)


def _legal_actions(
    level: LevelConfig,
    weather_today: str,
    from_node: int,
) -> list[tuple[int, str]]:
    """从 from_node 出发的合法动作（手册 §5.1.5）。"""
    actions: list[tuple[int, str]] = []
    if from_node == level.goal:
        return actions
    if weather_today != "沙暴":
        for neighbor in level.neighbors[from_node]:
            actions.append((neighbor, "行走"))
    if from_node in level.mines:
        actions.append((from_node, "挖矿"))
    actions.append((from_node, "停留"))
    return actions


def _village_purchase_closure(
    w_after: int,
    f_after: int,
    cash_after: int,
    game: GameConfig,
) -> list[tuple[int, int, int, int, int]]:
    """村庄补给闭包（手册 §5.1.8）。

    返回所有满足预算/负重/非负约束的 (w'', f'', cash'', bw, bf) 组合。
    """
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


def _optimistic_upper_bound(
    cash: int,
    w: int,
    f: int,
    t: int,
    deadline: int,
    water_price: float,
    food_price: float,
    mine_income: int,
    best_terminal: float,
) -> bool:
    """乐观收益上界剪枝（手册 §5.4）。

    UB = C + 0.5 p_w W + 0.5 p_f F + (T − t) R。
    若 UB ≤ best_terminal 返回 True（可剪枝）。
    """
    if best_terminal == float("-inf"):
        return False
    remaining_days = deadline - t
    ub = (
        cash
        + 0.5 * water_price * w
        + 0.5 * food_price * f
        + remaining_days * mine_income
    )
    return ub <= best_terminal


def _backtrack(
    final_t: int,
    final_i: int,
    final_w: int,
    final_f: int,
    final_cash: int,
    labels: list[dict[int, dict[tuple[int, int], _Label]]],
    game: GameConfig,
) -> tuple[list[DailyRecord], tuple[int, int]]:
    """从终态标签逆推得到逐日动作、采购记录与起点采购组合 (w, f)。"""
    chain: list[tuple[int, int, int, int, int, int, int, int, int]] = []
    t = final_t
    i = final_i
    w = final_w
    f = final_f
    initial_w: int | None = None
    initial_f: int | None = None
    while t > 0:
        label = labels[t][i][(w, f)]
        assert label.prev is not None
        prev_t, prev_i, prev_w, prev_f, action, bw, bf = label.prev
        chain.append((t, prev_i, i, action, bw, bf, label.cash, w, f))
        t, i, w, f = prev_t, prev_i, prev_w, prev_f
        if t == 0:
            initial_w, initial_f = w, f
    assert initial_w is not None and initial_f is not None
    chain.reverse()
    records: list[DailyRecord] = []
    for t, prev_i, cur_i, action, bw, bf, cash, w, f in chain:
        records.append(
            DailyRecord(
                day=t,
                weather=game.weather[t - 1],
                from_node=prev_i,
                to_node=cur_i,
                action=action,
                buy_water=bw,
                buy_food=bf,
                cash=cash,
                water=w,
                food=f,
            )
        )
    return records, (initial_w, initial_f)


@dataclass
class DPResult:
    """DP 求解结果（与 SolveResult 字段对齐）。"""

    optimal: bool
    status: str
    final_wealth: float
    arrival_day: int
    initial_purchase: InitialPurchase
    daily_records: list[DailyRecord]
    runtime_seconds: float
    statistics: dict[str, int | float | str]


def solve(
    level: LevelConfig,
    game: GameConfig,
    options: DPOptions | None = None,
) -> DPResult:
    """稀疏标签 DP 求解主函数。"""
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
                            # 同时存入 next_layer 以便回溯（建模手册 §5.1.3 / §5.1.9）。
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

        # Pareto 剪枝（手册 §5.2）。为避免 O(n²) 在初始层（线性 cash 阶段，
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