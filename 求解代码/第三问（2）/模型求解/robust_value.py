from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from math import inf

from .config import GameConfig, LevelConfig
from .transition import PlayerState, initial_state, terminal_wealth, total_weight


@dataclass(frozen=True)
class RobustValue:
    feasible: bool
    worst_wealth: float
    policy: str
    path: tuple[int, ...]
    mining_days: int
    required_days: int
    worst_case_water_margin: int
    worst_case_food_margin: int

    @property
    def score(self) -> tuple[int, float]:
        return int(self.feasible), self.worst_wealth


@dataclass(frozen=True)
class InitialPurchasePlan:
    state: PlayerState
    value: RobustValue
    gamma: int


@dataclass(frozen=True)
class _RouteOption:
    policy: str
    path: tuple[int, ...]
    village_index: int | None
    mine_index: int | None


def _shortest_path(level: LevelConfig, start: int, goal: int) -> tuple[int, ...]:
    if start == goal:
        return (start,)
    parent: dict[int, int | None] = {start: None}
    queue = deque([start])
    while queue:
        node = queue.popleft()
        for neighbor in sorted(level.neighbors[node]):
            if neighbor in parent:
                continue
            parent[neighbor] = node
            if neighbor == goal:
                queue.clear()
                break
            queue.append(neighbor)
    if goal not in parent:
        raise ValueError(f"节点{start}无法到达节点{goal}")
    reversed_path = [goal]
    node = goal
    while parent[node] is not None:
        node = int(parent[node])
        reversed_path.append(node)
    return tuple(reversed(reversed_path))


def _join_paths(*paths: tuple[int, ...]) -> tuple[int, ...]:
    joined: list[int] = []
    for path in paths:
        if not joined:
            joined.extend(path)
        else:
            joined.extend(path[1:])
    return tuple(joined)


def _route_options(state: PlayerState, level: LevelConfig) -> tuple[_RouteOption, ...]:
    goal = level.goal
    village = min(level.villages) if level.villages else None
    mine = min(level.mines) if level.mines else None
    raw: list[tuple[str, tuple[int, ...], int | None, int | None]] = []

    direct = _shortest_path(level, state.node, goal)
    raw.append(("直达终点", direct, None, None))
    if village is not None:
        via_village = _join_paths(
            _shortest_path(level, state.node, village),
            _shortest_path(level, village, goal),
        )
        raw.append(("经村庄补给", via_village, via_village.index(village), None))
    if mine is not None:
        via_mine = _join_paths(
            _shortest_path(level, state.node, mine),
            _shortest_path(level, mine, goal),
        )
        raw.append(("经矿山", via_mine, None, via_mine.index(mine)))
    if village is not None and mine is not None:
        village_mine = _join_paths(
            _shortest_path(level, state.node, village),
            _shortest_path(level, village, mine),
            _shortest_path(level, mine, goal),
        )
        raw.append(
            (
                "先村庄后矿山",
                village_mine,
                village_mine.index(village),
                village_mine.index(mine),
            )
        )
        mine_village = _join_paths(
            _shortest_path(level, state.node, mine),
            _shortest_path(level, mine, village),
            _shortest_path(level, village, goal),
        )
        raw.append(
            (
                "先矿山后村庄",
                mine_village,
                mine_village.index(village),
                mine_village.index(mine),
            )
        )

    unique: dict[tuple[tuple[int, ...], int | None, int | None], _RouteOption] = {}
    for policy, path, village_index, mine_index in raw:
        key = path, village_index, mine_index
        unique.setdefault(key, _RouteOption(policy, path, village_index, mine_index))
    return tuple(unique.values())


def _evaluate_option(
    option: _RouteOption,
    mining_days: int,
    remaining_days: int,
    state: PlayerState,
    gamma: int,
    game: GameConfig,
) -> RobustValue:
    move_days = len(option.path) - 1
    required_days = move_days + mining_days + gamma
    if required_days > remaining_days:
        return RobustValue(False, -inf, option.policy, option.path, mining_days, required_days, -1, -1)
    high_move = 2 * game.base_consumption["高温"][0]
    high_mine = 3 * game.base_consumption["高温"][0]
    storm_wait = game.base_consumption["沙暴"][0]
    income_total = mining_days * game.mine_income

    if option.village_index is None:
        needed = move_days * high_move + mining_days * high_mine + gamma * storm_wait
        if state.water < needed or state.food < needed:
            return RobustValue(False, -inf, option.policy, option.path, mining_days, required_days, state.water - needed, state.food - needed)
        final = PlayerState(
            node=option.path[-1],
            water=state.water - needed,
            food=state.food - needed,
            cash=state.cash + income_total,
            arrived=True,
        )
        return RobustValue(
            True,
            terminal_wealth(final, game),
            option.policy,
            option.path,
            mining_days,
            required_days,
            final.water,
            final.food,
        )

    village_index = option.village_index
    pre_moves = village_index
    post_moves = move_days - pre_moves
    mine_before = mining_days if option.mine_index is not None and option.mine_index < village_index else 0
    mine_after = mining_days - mine_before
    scenario_wealth: list[float] = []
    water_margins: list[int] = []
    food_margins: list[int] = []
    for storms_before in range(gamma + 1):
        storms_after = gamma - storms_before
        pre_need = pre_moves * high_move + mine_before * high_mine + storms_before * storm_wait
        post_need = post_moves * high_move + mine_after * high_mine + storms_after * storm_wait
        if state.water < pre_need or state.food < pre_need:
            return RobustValue(False, -inf, option.policy, option.path, mining_days, required_days, state.water - pre_need, state.food - pre_need)
        water_at_village = state.water - pre_need
        food_at_village = state.food - pre_need
        buy_water = max(0, post_need - water_at_village)
        buy_food = max(0, post_need - food_at_village)
        cash_at_village = state.cash + mine_before * game.mine_income
        purchase_cost = 2 * (
            game.water_price * buy_water + game.food_price * buy_food
        )
        purchased = PlayerState(
            node=option.path[village_index],
            water=water_at_village + buy_water,
            food=food_at_village + buy_food,
            cash=cash_at_village - purchase_cost,
        )
        if purchased.cash < 0 or total_weight(purchased, game) > game.capacity_kg:
            return RobustValue(False, -inf, option.policy, option.path, mining_days, required_days, -1, -1)
        final = PlayerState(
            node=option.path[-1],
            water=purchased.water - post_need,
            food=purchased.food - post_need,
            cash=purchased.cash + mine_after * game.mine_income,
            arrived=True,
        )
        scenario_wealth.append(terminal_wealth(final, game))
        water_margins.append(final.water)
        food_margins.append(final.food)
    return RobustValue(
        True,
        min(scenario_wealth),
        option.policy,
        option.path,
        mining_days,
        required_days,
        min(water_margins),
        min(food_margins),
    )


def robust_value(
    day: int,
    state: PlayerState,
    gamma_remaining: int,
    game: GameConfig,
    level: LevelConfig,
) -> RobustValue:
    """预算鲁棒单人续值下界，不读取任何未来真实天气。"""
    if gamma_remaining < 0:
        raise ValueError("剩余沙暴预算不能为负")
    if state.arrived:
        return RobustValue(True, terminal_wealth(state, game), "已到达", (state.node,), 0, 0, state.water, state.food)
    remaining_days = game.deadline - day + 1
    if remaining_days <= 0:
        return RobustValue(False, -inf, "超期", (), 0, 0, -1, -1)

    candidates: list[RobustValue] = []
    for option in _route_options(state, level):
        move_days = len(option.path) - 1
        max_mining = 0
        if option.mine_index is not None:
            max_mining = max(0, remaining_days - move_days - gamma_remaining)
        for mining_days in range(max_mining + 1):
            candidates.append(
                _evaluate_option(
                    option,
                    mining_days,
                    remaining_days,
                    state,
                    gamma_remaining,
                    game,
                )
            )
    feasible = [candidate for candidate in candidates if candidate.feasible]
    if not feasible:
        return RobustValue(False, -inf, "无鲁棒可行路线", (), 0, remaining_days, -1, -1)
    return max(
        feasible,
        key=lambda item: (
            item.worst_wealth,
            -item.required_days,
            -item.mining_days,
            tuple(-node for node in item.path),
        ),
    )


def plan_initial_purchase(
    gamma: int,
    game: GameConfig,
    level: LevelConfig,
) -> InitialPurchasePlan:
    """第0天按基准价选择可承受的整数初始库存。"""
    max_equal_stock = min(
        game.capacity_kg // (game.water_weight + game.food_weight),
        game.initial_cash // (game.water_price + game.food_price),
    )
    best: InitialPurchasePlan | None = None
    for amount in range(1, max_equal_stock + 1):
        state = initial_state(amount, amount, game, level)
        value = robust_value(1, state, gamma, game, level)
        if not value.feasible:
            continue
        candidate = InitialPurchasePlan(state, value, gamma)
        if best is None or (
            value.worst_wealth,
            -total_weight(state, game),
            state.cash,
        ) > (
            best.value.worst_wealth,
            -total_weight(best.state, game),
            best.state.cash,
        ):
            best = candidate
    if best is None:
        raise RuntimeError(f"Gamma={gamma} 时不存在鲁棒可行的初始采购")
    return best
