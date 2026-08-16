from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from time import perf_counter

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_matrix

from .config import GameConfig, LevelConfig
from .robust_dp_q3 import DailyRecord, SimulationResult
from .transition import Action, State, apply_action, terminal_wealth, total_weight
from .weather_markov import (
    HISTORICAL_WEATHER,
    empirical_initial_probabilities,
    nominal_transition_probabilities,
)


@dataclass(frozen=True)
class ScenarioTreeSolution:
    level: LevelConfig
    game: GameConfig
    weather_states: tuple[str, ...]
    initial_state: State
    policy: dict[tuple[str, ...], Action]
    robust_by_history: dict[tuple[str, ...], float]
    nominal_by_history: dict[tuple[str, ...], float]
    robust_value: float
    nominal_value: float
    optimal: bool
    status: str
    runtime_seconds: float
    statistics: dict[str, int | float | str]


class _LinearModel:
    def __init__(self) -> None:
        self.lower: list[float] = []
        self.upper: list[float] = []
        self.integrality: list[int] = []
        self.objective: list[float] = []
        self.rows: list[dict[int, float]] = []
        self.row_lower: list[float] = []
        self.row_upper: list[float] = []

    def var(
        self, lb: float = 0.0, ub: float = np.inf, integer: bool = False,
        objective: float = 0.0,
    ) -> int:
        index = len(self.lower)
        self.lower.append(lb)
        self.upper.append(ub)
        self.integrality.append(1 if integer else 0)
        self.objective.append(objective)
        return index

    def constraint(
        self, terms: dict[int, float], lb: float = -np.inf, ub: float = np.inf
    ) -> None:
        self.rows.append({index: value for index, value in terms.items() if value})
        self.row_lower.append(lb)
        self.row_upper.append(ub)

    def equality(self, terms: dict[int, float], value: float) -> None:
        self.constraint(terms, value, value)

    def matrix(self):
        row_ids: list[int] = []
        column_ids: list[int] = []
        values: list[float] = []
        for row_id, row in enumerate(self.rows):
            for column_id, value in row.items():
                row_ids.append(row_id)
                column_ids.append(column_id)
                values.append(value)
        return coo_matrix(
            (values, (row_ids, column_ids)),
            shape=(len(self.rows), len(self.lower)),
            dtype=float,
        ).tocsr()


def _add(terms: dict[int, float], index: int, value: float) -> None:
    terms[index] = terms.get(index, 0.0) + value


def _histories(
    deadline: int, weather_states: tuple[str, ...]
) -> dict[int, tuple[tuple[str, ...], ...]]:
    return {
        day: tuple(product(weather_states, repeat=day))
        for day in range(1, deadline + 1)
    }


def _solve_model(model: _LinearModel, time_limit_seconds: float, disp: bool):
    matrix = model.matrix()
    return milp(
        c=np.asarray(model.objective, dtype=float),
        integrality=np.asarray(model.integrality, dtype=np.uint8),
        bounds=Bounds(model.lower, model.upper),
        constraints=LinearConstraint(matrix, model.row_lower, model.row_upper),
        options={
            "time_limit": time_limit_seconds,
            "mip_rel_gap": 0.0,
            "presolve": True,
            "disp": disp,
        },
    )


def solve_scenario_tree(
    level: LevelConfig,
    game: GameConfig,
    weather_states: tuple[str, ...] = ("晴朗", "高温"),
    time_limit_seconds: float = 300.0,
    disp: bool = False,
) -> ScenarioTreeSolution:
    """精确求解自适应鲁棒策略的非前视天气情景树展开。"""
    if level.villages:
        raise ValueError("第三关情景树入口不处理村庄补给")
    started = perf_counter()
    model = _LinearModel()
    histories = _histories(game.deadline, weather_states)
    nodes = range(1, level.node_count + 1)
    directed_edges = tuple(
        direction for i, j in level.edges for direction in ((i, j), (j, i))
    )

    max_water = game.capacity_kg // game.water_weight
    max_food = game.capacity_kg // game.food_weight
    max_cash = game.initial_cash + game.deadline * game.mine_income
    buy_water = model.var(0, max_water, integer=True)
    buy_food = model.var(0, max_food, integer=True)
    robust_floor = model.var(0, max_cash + game.initial_cash, objective=-1.0)

    x: dict[tuple[tuple[str, ...], int], int] = {}
    post_x: dict[tuple[tuple[str, ...], int], int] = {}
    water: dict[tuple[str, ...], int] = {}
    food: dict[tuple[str, ...], int] = {}
    cash: dict[tuple[str, ...], int] = {}
    post_water: dict[tuple[str, ...], int] = {}
    post_food: dict[tuple[str, ...], int] = {}
    post_cash: dict[tuple[str, ...], int] = {}
    move: dict[tuple[tuple[str, ...], int, int], int] = {}
    stay: dict[tuple[tuple[str, ...], int], int] = {}
    mine: dict[tuple[tuple[str, ...], int], int] = {}
    finish: dict[tuple[str, ...], int] = {}

    for day in range(1, game.deadline + 1):
        for history in histories[day]:
            for node in nodes:
                fixed = (1.0 if node == level.start else 0.0) if day == 1 else None
                x[history, node] = model.var(
                    fixed if fixed is not None else 0,
                    fixed if fixed is not None else 1,
                    integer=True,
                )
                post_x[history, node] = model.var(0, 1, integer=True)
            water[history] = model.var(0, max_water)
            food[history] = model.var(0, max_food)
            cash[history] = model.var(0, max_cash)
            post_water[history] = model.var(0, max_water)
            post_food[history] = model.var(0, max_food)
            post_cash[history] = model.var(0, max_cash)
            can_move = history[-1] != "沙暴"
            for i, j in directed_edges:
                move[history, i, j] = model.var(0, 1 if can_move else 0, integer=True)
            for node in nodes:
                if node != level.goal:
                    stay[history, node] = model.var(0, 1, integer=True)
            for node in level.mines:
                mine[history, node] = model.var(0, 1, integer=True)
            finish[history] = model.var(0, 1, integer=True)

    model.constraint(
        {buy_water: game.water_weight, buy_food: game.food_weight},
        ub=game.capacity_kg,
    )
    model.constraint(
        {buy_water: game.water_price, buy_food: game.food_price},
        ub=game.initial_cash,
    )

    for first_history in histories[1]:
        model.equality({water[first_history]: 1, buy_water: -1}, 0)
        model.equality({food[first_history]: 1, buy_food: -1}, 0)
        model.equality(
            {
                cash[first_history]: 1,
                buy_water: game.water_price,
                buy_food: game.food_price,
            },
            game.initial_cash,
        )

    outgoing: dict[int, list[tuple[int, int]]] = {node: [] for node in nodes}
    incoming: dict[int, list[tuple[int, int]]] = {node: [] for node in nodes}
    for i, j in directed_edges:
        outgoing[i].append((i, j))
        incoming[j].append((i, j))

    terminal_histories = histories[game.deadline]
    terminal_wealth_terms: dict[tuple[str, ...], dict[int, float]] = {}
    for day in range(1, game.deadline + 1):
        for history in histories[day]:
            for node in nodes:
                origin = {x[history, node]: -1.0}
                for i, j in outgoing[node]:
                    _add(origin, move[history, i, j], 1.0)
                if node != level.goal:
                    _add(origin, stay[history, node], 1.0)
                if node in level.mines:
                    _add(origin, mine[history, node], 1.0)
                if node == level.goal:
                    _add(origin, finish[history], 1.0)
                model.equality(origin, 0)

                destination = {post_x[history, node]: -1.0}
                for i, j in incoming[node]:
                    _add(destination, move[history, i, j], 1.0)
                if node != level.goal:
                    _add(destination, stay[history, node], 1.0)
                if node in level.mines:
                    _add(destination, mine[history, node], 1.0)
                if node == level.goal:
                    _add(destination, finish[history], 1.0)
                model.equality(destination, 0)

            base_water, base_food = game.base_consumption[history[-1]]
            water_terms = {post_water[history]: 1, water[history]: -1}
            food_terms = {post_food[history]: 1, food[history]: -1}
            cash_terms = {post_cash[history]: 1, cash[history]: -1}
            for i, j in directed_edges:
                _add(water_terms, move[history, i, j], 2 * base_water)
                _add(food_terms, move[history, i, j], 2 * base_food)
            for node in nodes:
                if node != level.goal:
                    _add(water_terms, stay[history, node], base_water)
                    _add(food_terms, stay[history, node], base_food)
            for node in level.mines:
                _add(water_terms, mine[history, node], 3 * base_water)
                _add(food_terms, mine[history, node], 3 * base_food)
                _add(cash_terms, mine[history, node], -game.mine_income)
            model.equality(water_terms, 0)
            model.equality(food_terms, 0)
            model.equality(cash_terms, 0)

            if day < game.deadline:
                for next_weather in weather_states:
                    child = history + (next_weather,)
                    model.equality({water[child]: 1, post_water[history]: -1}, 0)
                    model.equality({food[child]: 1, post_food[history]: -1}, 0)
                    model.equality({cash[child]: 1, post_cash[history]: -1}, 0)
                    for node in nodes:
                        model.equality(
                            {x[child, node]: 1, post_x[history, node]: -1}, 0
                        )
            else:
                model.equality({post_x[history, level.goal]: 1}, 1)
                wealth_terms = {
                    post_cash[history]: 1.0,
                    post_water[history]: 0.5 * game.water_price,
                    post_food[history]: 0.5 * game.food_price,
                }
                terminal_wealth_terms[history] = wealth_terms
                floor_constraint = {robust_floor: 1.0}
                for index, coefficient in wealth_terms.items():
                    _add(floor_constraint, index, -coefficient)
                model.constraint(floor_constraint, ub=0)

    first_result = _solve_model(model, time_limit_seconds, disp)
    if first_result.x is None:
        raise RuntimeError(f"{level.name}鲁棒情景树求解失败：{first_result.message}")
    robust_optimum = round(float(first_result.x[robust_floor]) * 2) / 2

    model.constraint({robust_floor: 1.0}, lb=robust_optimum - 1e-7)
    model.objective = [0.0] * len(model.objective)
    initial_probabilities = empirical_initial_probabilities(
        HISTORICAL_WEATHER, weather_states
    )
    markov_states, markov = nominal_transition_probabilities(
        HISTORICAL_WEATHER, weather_states
    )
    weather_index = {weather: i for i, weather in enumerate(markov_states)}
    leaf_probabilities: dict[tuple[str, ...], float] = {}
    for history in terminal_histories:
        probability = initial_probabilities[history[0]]
        for current, following in zip(history, history[1:]):
            probability *= markov[weather_index[current], weather_index[following]]
        leaf_probabilities[history] = float(probability)
        for index, coefficient in terminal_wealth_terms[history].items():
            model.objective[index] -= probability * coefficient

    second_result = _solve_model(model, time_limit_seconds, disp)
    result = second_result if second_result.x is not None else first_result
    values = result.x

    initial = State(
        level.start,
        int(round(values[buy_water])),
        int(round(values[buy_food])),
        game.initial_cash
        - game.water_price * int(round(values[buy_water]))
        - game.food_price * int(round(values[buy_food])),
    )
    policy: dict[tuple[str, ...], Action] = {}
    for day in range(1, game.deadline + 1):
        for history in histories[day]:
            chosen: Action | None = None
            for i, j in directed_edges:
                if values[move[history, i, j]] > 0.5:
                    chosen = Action("行走", j)
                    break
            if chosen is None:
                for node in level.mines:
                    if values[mine[history, node]] > 0.5:
                        chosen = Action("挖矿", node)
                        break
            if chosen is None:
                for node in nodes:
                    if node != level.goal and values[stay[history, node]] > 0.5:
                        chosen = Action("停留", node)
                        break
            if chosen is None and values[finish[history]] > 0.5:
                chosen = Action("终止", level.goal)
            if chosen is None:
                raise RuntimeError(f"天气历史 {history} 未提取到行动")
            policy[history] = chosen

    leaf_values = {
        history: sum(
            coefficient * values[index]
            for index, coefficient in terminal_wealth_terms[history].items()
        )
        for history in terminal_histories
    }
    robust_by_history: dict[tuple[str, ...], float] = dict(leaf_values)
    nominal_by_history: dict[tuple[str, ...], float] = dict(leaf_values)
    for day in range(game.deadline - 1, 0, -1):
        for history in histories[day]:
            children = [history + (weather,) for weather in weather_states]
            robust_by_history[history] = min(robust_by_history[child] for child in children)
            row = markov[weather_index[history[-1]]]
            nominal_by_history[history] = sum(
                row[weather_index[weather]] * nominal_by_history[history + (weather,)]
                for weather in weather_states
            )

    robust_value = min(leaf_values.values())
    nominal_value = sum(
        leaf_probabilities[history] * leaf_values[history]
        for history in terminal_histories
    )
    return ScenarioTreeSolution(
        level=level,
        game=game,
        weather_states=weather_states,
        initial_state=initial,
        policy=policy,
        robust_by_history=robust_by_history,
        nominal_by_history=nominal_by_history,
        robust_value=round(robust_value * 2) / 2,
        nominal_value=nominal_value,
        optimal=first_result.status == 0 and result.status == 0,
        status=str(result.message),
        runtime_seconds=perf_counter() - started,
        statistics={
            "variables": len(model.lower),
            "constraints": len(model.rows),
            "weather_tree_nodes": sum(len(items) for items in histories.values()),
            "terminal_scenarios": len(terminal_histories),
            "mip_gap": float(getattr(result, "mip_gap", 0.0) or 0.0),
            "mip_nodes": int(getattr(result, "mip_node_count", 0) or 0),
            "solver": "SciPy milp / HiGHS（非前视天气情景树）",
        },
    )


def simulate_tree_policy(
    solution: ScenarioTreeSolution, weather_sequence: tuple[str, ...]
) -> SimulationResult:
    state = solution.initial_state
    history: tuple[str, ...] = ()
    records: list[DailyRecord] = []
    for day, weather in enumerate(weather_sequence, start=1):
        if day > solution.game.deadline or state.node == solution.level.goal:
            break
        history += (weather,)
        action = solution.policy.get(history)
        if action is None or action.kind == "终止":
            return SimulationResult(
                False, state, None, None, tuple(records), f"第{day}天未找到可执行行动"
            )
        previous = state
        try:
            state = apply_action(
                state, action, weather, solution.level, solution.game
            )
        except ValueError as exc:
            return SimulationResult(
                False, previous, None, None, tuple(records), f"第{day}天：{exc}"
            )
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
                weight=total_weight(state, solution.game),
                robust_value=solution.robust_by_history[history],
                nominal_value=solution.nominal_by_history[history],
            )
        )
        if state.node == solution.level.goal:
            return SimulationResult(
                True, state, terminal_wealth(state, solution.game), day, tuple(records)
            )
    return SimulationResult(
        False, state, None, None, tuple(records), "截止日前未到达终点"
    )
