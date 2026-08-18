"""第二问共享剪枝工具：Pareto 支配与乐观收益上界。

沿用第一问 [dp.py](求解代码/第一问/模型求解/dp.py) 的剪枝思想：
- `_pareto_prune_3d`：按 (w, f, c) 三维 Pareto 剪枝。先按 w 降序、cash 升序、f 升序排列，
  扫一遍时维护 (f, c) 上的 2D frontier。O(n²) 在 frontier 上限 ~200 时仍可控。
- `_optimistic_upper_bound_3d`：与第一问 [dp.py:222-247] 同公式，把 w、f、cash 三者全部计入
  折算现金并加上剩余天数可能挖矿的乐观收益。

建模手册 §6.4 第四关 Pareto 剪枝、§5.2 状态压缩都基于此模式。
"""

from __future__ import annotations

from typing import Callable, Generic, Hashable, Iterable, TypeVar

K = TypeVar("K", bound=Hashable)


def pareto_prune_3d(
    labels: dict[tuple[int, int, int], float],
    threshold: int = 10_000,
) -> dict[tuple[int, int, int], float]:
    """三维 Pareto 支配剪枝（w, f, cash 三者越大越好）。

    输入 ``labels`` 的键为 ``(w, f, cash)``，值为任意可比较的"分数"——通常取
    ``cash`` 本身作为分数，做去重后再做支配判断；但接口允许外部传入其它
    指标（例如 cash + 估值），方便拓展。

    A 支配 B 当且仅当 ``w_A ≥ w_B``、``f_A ≥ f_B``、``cash_A ≥ cash_B``，
    且至少一项严格更优。
    """
    if not labels:
        return labels
    # 同 (w, f, cash) 保留最大分数者。
    best: dict[tuple[int, int, int], float] = {}
    for key, score in labels.items():
        existing = best.get(key)
        if existing is None or score > existing:
            best[key] = score
    # 桶规模过大跳过剪枝（与第一问 dp.py:445 同模式）。
    if len(best) > threshold:
        return best
    items = sorted(best.items(), key=lambda kv: (-kv[0][0], -kv[1], kv[0][1]))
    kept: dict[tuple[int, int, int], float] = {}
    front_f: list[int] = []
    front_cash: list[int] = []
    for key, score in items:
        w, f, cash = key
        dominated = False
        for ff, fc in zip(front_f, front_cash):
            if ff >= f and fc >= cash and (ff > f or fc > cash):
                dominated = True
                break
        if dominated:
            continue
        new_f: list[int] = []
        new_c: list[int] = []
        for ff, fc in zip(front_f, front_cash):
            if not (ff <= f and fc <= cash):
                new_f.append(ff)
                new_c.append(fc)
        front_f = new_f
        front_cash = new_c
        front_f.append(f)
        front_cash.append(cash)
        kept[key] = score
    return kept


def optimistic_upper_bound_3d(
    water: int,
    food: int,
    cash: int,
    deadline: int,
    current_day: int,
    water_price: int,
    food_price: int,
    mine_income: int,
) -> float:
    """乐观收益上界：现金 + 折算剩余资源 + 剩余天数可能的挖矿收入。

    与第一问 [dp.py:222-247] 同公式。
    """
    remaining_days = deadline - current_day
    return (
        cash
        + 0.5 * water_price * water
        + 0.5 * food_price * food
        + remaining_days * mine_income
    )


def optimistic_upper_bound_4d(
    water: int,
    food: int,
    cash: int,
    deadline: int,
    current_day: int,
    water_price: int,
    food_price: int,
    mine_income: int,
    storm_budget: int,
    storm_factor: float = 1.0,
) -> float:
    """四维乐观上界：第三维基础上叠加剩余沙暴预算可能带来的等待日挖矿收益。

    ``storm_factor`` 用于把"沙暴日不能行走但能挖矿"的边际收益折算回非沙暴日。
    """
    base = optimistic_upper_bound_3d(
        water,
        food,
        cash,
        deadline,
        current_day,
        water_price,
        food_price,
        mine_income,
    )
    return base + storm_budget * storm_factor * mine_income