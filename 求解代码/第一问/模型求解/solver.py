"""第一问求解器入口。

依据建模手册 §0 / §2.3 / 求解流程图，主模型为"稀疏标签动态规划（DP）"。
受 Python 性能与状态空间结构限制（线性 cash 阶段 Pareto 剪枝无效），
`dp.py` 在完整问题规模下耗时较长，故默认改用数学等价的 MILP
（手册 §2.3 称为"等价整数展开"）作为生产求解器；`dp.py` 保留为建模手册
所规定主模型的完整实现，并作为交叉验证工具（`verify_with_dp`）。

通过 `SolveOptions(use_dp=True)` 可强制走 DP 主路线（适合小问题 / 单元测试）。
"""

from __future__ import annotations

from dataclasses import dataclass

from .checker import DailyRecord, InitialPurchase
from .config import GameConfig, LevelConfig
from .dp import DPOptions, solve as dp_solve
from .milp import MILPOptions, solve as milp_solve


@dataclass(frozen=True)
class SolveOptions:
    """求解控制选项。"""

    use_dp: bool = False  # 默认 MILP（性能原因）；DP 见 use_dp=True
    use_pareto: bool = True
    use_time_bound: bool = True
    use_revenue_bound: bool = True
    pareto_threshold: int = 10000
    milp_time_limit_seconds: float = 300.0
    # 兼容旧接口
    time_limit_seconds: float = 300.0
    mip_relative_gap: float = 0.0
    disp: bool = False


@dataclass(frozen=True)
class SolveResult:
    """求解结果（与既有接口兼容）。"""

    level_name: str
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
    options: SolveOptions | None = None,
) -> SolveResult:
    """求解完整逐日模型。"""
    options = options or SolveOptions()
    if options.use_dp:
        result = dp_solve(
            level,
            game,
            DPOptions(
                use_pareto=options.use_pareto,
                use_time_bound=options.use_time_bound,
                use_revenue_bound=options.use_revenue_bound,
                pareto_threshold=options.pareto_threshold,
                disp=options.disp,
            ),
        )
        return SolveResult(
            level_name=level.name,
            optimal=result.optimal,
            status=result.status,
            final_wealth=result.final_wealth,
            arrival_day=result.arrival_day,
            initial_purchase=result.initial_purchase,
            daily_records=result.daily_records,
            runtime_seconds=result.runtime_seconds,
            statistics=result.statistics,
        )

    initial, records, arrival_day, final_wealth, statistics, runtime = milp_solve(
        level, game, MILPOptions(time_limit_seconds=options.milp_time_limit_seconds)
    )
    return SolveResult(
        level_name=level.name,
        optimal=True,
        status="MILP 收敛",
        final_wealth=final_wealth,
        arrival_day=arrival_day,
        initial_purchase=initial,
        daily_records=records,
        runtime_seconds=runtime,
        statistics=statistics,
    )


def verify_with_dp(
    level: LevelConfig,
    game: GameConfig,
    milp_result: SolveResult,
    options: SolveOptions | None = None,
) -> tuple[bool, float, SolveResult]:
    """用 DP 独立校验 MILP 结果（建模手册 §2.3、§7.3）。"""
    options = options or SolveOptions(use_dp=True)
    result = dp_solve(
        level,
        game,
        DPOptions(
            use_pareto=options.use_pareto,
            use_time_bound=options.use_time_bound,
            use_revenue_bound=options.use_revenue_bound,
            pareto_threshold=options.pareto_threshold,
            disp=options.disp,
        ),
    )
    dp_solve_result = SolveResult(
        level_name=level.name,
        optimal=result.optimal,
        status=result.status,
        final_wealth=result.final_wealth,
        arrival_day=result.arrival_day,
        initial_purchase=result.initial_purchase,
        daily_records=result.daily_records,
        runtime_seconds=result.runtime_seconds,
        statistics=result.statistics,
    )
    consistent = abs(result.final_wealth - milp_result.final_wealth) < 1e-6
    return consistent, abs(result.final_wealth - milp_result.final_wealth), dp_solve_result


__all__ = ["SolveOptions", "SolveResult", "solve", "verify_with_dp"]