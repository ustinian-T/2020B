# 第三问多人博弈求解代码 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在两个指定目录内完成第五关开环 Nash 求解与第六关滚动鲁棒阶段博弈，并提供可重复的模型检验、灵敏度分析和结构化结果输出。

**Architecture:** 两个子问各自构成独立 Python 包，不跨目录导入；每个包内部按“配置与数据—唯一转移内核—DP/鲁棒续值—博弈求解—独立验证—导出与入口”分层。生产代码均由失败测试驱动，规则检查器独立复算而不调用生产转移函数。

**Tech Stack:** Python 3.10、标准库、NumPy、SciPy、pytest；两人受限混合博弈可使用 nashpy（若运行环境无该依赖，则用 SciPy 线性规划求零和外的一般和支持条件并验证 exploitability）。

## Global Constraints

- 只改动 `求解代码/第三问（1）`、`求解代码/第三问（2）` 及本计划状态；不改手册、第一问、第二问、论文和绘图代码。
- 第五关使用用户给出的 13 节点、25 条无向边；第六关使用 5×5 网格的 40 条无向边。
- 第五关玩家数 2、期限 10、矿山 9、终点 13、固定天气序列；第六关玩家数 3、期限 30、村庄 14、矿山 18、终点 25。
- 同向移动按“日期+有向边”统计，K 人各消耗 `2K` 倍；反向移动不合并。
- 同矿每人收入 `R/K`、消耗固定 3 倍；同村仅实际购买者计数，单人 2 倍、多人 4 倍。
- 沙暴日禁止移动但允许原地挖矿；到矿当天不能挖矿；终点玩家退出互动。
- 未到终点时日末水食物各不少于 1，到达终点当天允许为 0；现金非负且负重不超过 1200 kg。
- 第六关在线策略接口不得接收未来真实天气；Gamma 是情景变量，6 仅作经验参考点。
- 不生成图；CSV 使用 UTF-8-SIG，JSON 使用 UTF-8；混合均衡容差 `1e-8`。

---

### Task 1: 第五关配置与图数据审计

**Files:**
- Create: `求解代码/第三问（1）/模型求解/__init__.py`
- Create: `求解代码/第三问（1）/模型求解/config.py`
- Create: `求解代码/第三问（1）/模型求解/data_loader.py`
- Test: `求解代码/第三问（1）/tests/test_data_loader.py`

**Interfaces:**
- Produces: `GameConfig`, `LevelConfig`, `load_level5() -> tuple[GameConfig, LevelConfig, tuple[str, ...]]`, `audit_graph(level) -> GraphAudit`。
- Consumes: 无。

- [ ] **Step 1: Write the failing graph test**

```python
from 模型求解.data_loader import audit_graph, load_level5

def test_level5_uses_exact_user_graph():
    game, level, weather = load_level5()
    assert level.node_count == 13
    assert len(level.edges) == 25
    assert level.start == 1 and level.mines == frozenset({9}) and level.goal == 13
    assert (1, 2) in level.edges and (12, 13) in level.edges
    assert weather == ("晴朗", "高温", "晴朗", "晴朗", "晴朗", "晴朗", "高温", "高温", "高温", "高温")
    audit = audit_graph(level)
    assert audit.connected and audit.key_nodes_reachable and audit.symmetric
```

- [ ] **Step 2: Run RED**

Run from `求解代码/第三问（1）`: `python -m pytest tests/test_data_loader.py -q`
Expected: FAIL because `模型求解.data_loader` does not exist.

- [ ] **Step 3: Implement immutable configs and exact edge normalization**

```python
@dataclass(frozen=True)
class LevelConfig:
    node_count: int
    edges: tuple[tuple[int, int], ...]
    neighbors: Mapping[int, frozenset[int]]
    start: int
    goal: int
    villages: frozenset[int]
    mines: frozenset[int]

def load_level5() -> tuple[GameConfig, LevelConfig, tuple[str, ...]]:
    edges = tuple(sorted((min(u, v), max(u, v)) for u, v in LEVEL5_EDGES))
    if len(edges) != len(set(edges)):
        raise ValueError("第五关邻接表存在重复边")
    level = make_level(
        node_count=13,
        edges=edges,
        start=1,
        goal=13,
        villages=frozenset(),
        mines=frozenset({9}),
    )
    return LEVEL5_GAME, level, LEVEL5_WEATHER
```

- [ ] **Step 4: Run GREEN and full local test directory**

Run: `python -m pytest tests/test_data_loader.py -q`
Expected: PASS.

- [ ] **Step 5: Commit task files**

```bash
git add "求解代码/第三问（1）/模型求解" "求解代码/第三问（1）/tests/test_data_loader.py"
git commit -m "feat(q3-1): add level five configuration"
```

### Task 2: 第五关多人联合转移与独立审计

**Files:**
- Create: `求解代码/第三问（1）/模型求解/transition.py`
- Create: `求解代码/第三问（1）/模型求解/validator.py`
- Test: `求解代码/第三问（1）/tests/test_transition.py`

**Interfaces:**
- Consumes: Task 1 `GameConfig`, `LevelConfig`。
- Produces: `PlayerState`, `Action`, `JointStep`, `initial_state()`, `legal_actions()`, `step_joint(states, actions, weather, game, level)`, `audit_records(initial, records, ...)`。

- [ ] **Step 1: Write failing interaction tests**

```python
def test_same_directed_edge_doubles_each_players_move_multiplier(level5):
    states = (PlayerState(1, 100, 100, 9000),) * 2
    actions = (Action.move(2), Action.move(2))
    result = step_joint(states, actions, "晴朗", *level5)
    assert [s.water for s in result.states] == [88, 88]  # 2K*3
    assert [s.food for s in result.states] == [84, 84]   # 2K*4

def test_opposite_directions_are_not_same_edge_event(level5):
    states = (PlayerState(1, 100, 100, 9000), PlayerState(2, 100, 100, 9000))
    result = step_joint(states, (Action.move(2), Action.move(1)), "晴朗", *level5)
    assert [s.water for s in result.states] == [94, 94]

def test_same_mine_splits_income_but_not_consumption(level5):
    states = (PlayerState(9, 100, 100, 9000),) * 2
    result = step_joint(states, (Action.mine(), Action.mine()), "晴朗", *level5)
    assert [s.water for s in result.states] == [91, 91]
    assert [s.cash for s in result.states] == [9100, 9100]
```

- [ ] **Step 2: Run RED**

Run: `python -m pytest tests/test_transition.py -q`
Expected: FAIL because transition types/functions are missing.

- [ ] **Step 3: Implement event counting and deterministic event order**

```python
directed_counts = Counter(
    (state.node, action.destination)
    for state, action in zip(states, actions)
    if action.kind == "行走"
)
mine_counts = Counter(
    state.node for state, action in zip(states, actions) if action.kind == "挖矿"
)
multiplier = 2 * directed_counts[(state.node, action.destination)]
mine_income = game.mine_income / mine_counts[state.node]
```

Implement purchase-before-action, load/cash checks, consumption, arrival/exit flags, and independent validator arithmetic without calling `step_joint`.

- [ ] **Step 4: Run GREEN**

Run: `python -m pytest tests/test_transition.py -q`
Expected: PASS with exact integer resource residuals.

- [ ] **Step 5: Commit**

```bash
git add "求解代码/第三问（1）/模型求解/transition.py" "求解代码/第三问（1）/模型求解/validator.py" "求解代码/第三问（1）/tests/test_transition.py"
git commit -m "feat(q3-1): implement multiplayer transition rules"
```

### Task 3: 第五关 Pareto DP 最优响应 Oracle

**Files:**
- Create: `求解代码/第三问（1）/模型求解/single_dp.py`
- Test: `求解代码/第三问（1）/tests/test_single_dp.py`

**Interfaces:**
- Consumes: `Plan`, `PlayerState`, `Action`, level/game/weather。
- Produces: `best_response(opponents_plan, game, level, weather) -> PlanResult`, `evaluate_plan(plan, opponents_plan, ...) -> PlanResult`。

- [ ] **Step 1: Write failing exact-oracle test on a tiny graph**

```python
def test_best_response_matches_complete_enumeration(tiny_level):
    opponent = fixed_plan([Action.stay(), Action.move(2)])
    dp = best_response((opponent,), tiny_level.game, tiny_level.level, ("晴朗", "晴朗"))
    brute = enumerate_all_plans((opponent,), tiny_level.game, tiny_level.level, ("晴朗", "晴朗"))
    assert dp.terminal_wealth == brute.terminal_wealth
    assert dp.arrival_day == brute.arrival_day
```

- [ ] **Step 2: Run RED**

Run: `python -m pytest tests/test_single_dp.py -q`
Expected: FAIL because `best_response` is missing.

- [ ] **Step 3: Implement label DP with Pareto pruning**

```python
@dataclass(frozen=True)
class Label:
    day: int
    state: PlayerState
    initial_water: int
    initial_food: int
    actions: tuple[Action, ...]

def dominates(a: Label, b: Label) -> bool:
    return (a.state.water >= b.state.water and a.state.food >= b.state.food
            and a.state.cash >= b.state.cash and a != b)
```

Generate feasible initial purchases, expand complete daily actions against fixed opponent events, apply shortest-distance deadline pruning, retain non-dominated labels by `(day,node,arrived)` and tie-break deterministically.

- [ ] **Step 4: Run GREEN and regression tests**

Run: `python -m pytest tests/test_single_dp.py tests/test_transition.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add "求解代码/第三问（1）/模型求解/single_dp.py" "求解代码/第三问（1）/tests/test_single_dp.py"
git commit -m "feat(q3-1): add exact best response oracle"
```

### Task 4: 第五关开环 Nash 搜索与全局偏离检验

**Files:**
- Create: `求解代码/第三问（1）/模型求解/game_open_loop.py`
- Extend: `求解代码/第三问（1）/模型求解/validator.py`
- Test: `求解代码/第三问（1）/tests/test_open_loop_game.py`

**Interfaces:**
- Consumes: `best_response`, `evaluate_plan`。
- Produces: `find_pure_ne(update_order, initial_profile, ...) -> EquilibriumResult`, `exploitability(profile, ...) -> ExploitabilityReport`, `solve_restricted_mixed(strategy_sets, ...) -> MixedEquilibriumResult`。

- [ ] **Step 1: Write failing equilibrium test**

```python
def test_returned_pure_equilibrium_has_zero_global_exploitability(tiny_game):
    equilibrium = find_pure_ne(tiny_game, update_order=(0, 1))
    report = exploitability(equilibrium.profile, tiny_game)
    assert equilibrium.kind == "pure"
    assert report.epsilon == 0
    assert all(item.gain == 0 for item in report.players)
```

- [ ] **Step 2: Run RED**

Run: `python -m pytest tests/test_open_loop_game.py -q`
Expected: FAIL because game solver is missing.

- [ ] **Step 3: Implement alternating BR, cycle detection and mixed fallback**

```python
for player in update_order:
    candidate = best_response(profile_without(player), game, level, weather)
    if candidate.terminal_wealth > current_payoff[player]:
        profile[player] = candidate.plan
if profile_key(profile) in seen:
    return expand_and_solve_restricted_mixed(generated_strategies, oracle=best_response)
```

Verify every returned result with a fresh global Oracle call. Never accept a restricted mixed solution until support equality and out-of-support epsilon pass `1e-8`.

- [ ] **Step 4: Run GREEN**

Run: `python -m pytest tests/test_open_loop_game.py tests/test_single_dp.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add "求解代码/第三问（1）/模型求解/game_open_loop.py" "求解代码/第三问（1）/模型求解/validator.py" "求解代码/第三问（1）/tests/test_open_loop_game.py"
git commit -m "feat(q3-1): solve and verify open loop Nash game"
```

### Task 5: 第五关灵敏度、导出和运行入口

**Files:**
- Create: `求解代码/第三问（1）/模型求解/sensitivity.py`
- Create: `求解代码/第三问（1）/模型求解/export.py`
- Create: `求解代码/第三问（1）/模型求解/run.py`
- Test: `求解代码/第三问（1）/tests/test_export_and_sensitivity.py`

**Interfaces:**
- Produces: `scan_thresholds(base_config, ...)`, `write_csv()`, `write_json()`, `main()`。

- [ ] **Step 1: Write failing deterministic-export test**

```python
def test_threshold_scan_and_export_are_reproducible(tmp_path, solved_level5):
    first = scan_thresholds(solved_level5.config, revenues=(0, 200, 400))
    second = scan_thresholds(solved_level5.config, revenues=(0, 200, 400))
    assert first == second
    write_json(tmp_path / "summary.json", {"rows": first})
    assert (tmp_path / "summary.json").read_text("utf-8").endswith("\n")
```

- [ ] **Step 2: Run RED**

Run: `python -m pytest tests/test_export_and_sensitivity.py -q`
Expected: FAIL because export/sensitivity modules are missing.

- [ ] **Step 3: Implement scans and output contract**

Create player daily CSV, equilibrium JSON, audit CSV, update-order comparison CSV and `R/M/C0` threshold CSV. `run.py` must abort if rule violations or exploitability exceed tolerance.

- [ ] **Step 4: Run GREEN and execute level five**

Run: `python -m pytest tests -q`
Run: `python -m 模型求解.run`
Expected: tests PASS; outputs appear only under `结果输出/` and `结果验证/`.

- [ ] **Step 5: Commit**

```bash
git add "求解代码/第三问（1）"
git commit -m "feat(q3-1): export solutions and sensitivity checks"
```

### Task 6: 第六关配置与三人联合转移

**Files:**
- Create: `求解代码/第三问（2）/模型求解/__init__.py`
- Create: `求解代码/第三问（2）/模型求解/config.py`
- Create: `求解代码/第三问（2）/模型求解/data_loader.py`
- Create: `求解代码/第三问（2）/模型求解/transition.py`
- Test: `求解代码/第三问（2）/tests/test_data_and_transition.py`

**Interfaces:**
- Produces: `load_level6()`, `legal_actions()`, `step_joint()` with the same state/action field names as Q3(1), plus village purchases。

- [ ] **Step 1: Write failing grid and village tests**

```python
def test_level6_grid_has_25_nodes_and_40_edges():
    game, level = load_level6()
    assert level.node_count == 25 and len(level.edges) == 40
    assert level.villages == frozenset({14}) and level.mines == frozenset({18})

def test_only_buyers_trigger_four_times_village_price(level6):
    states = (PlayerState(14, 20, 20, 9000),) * 3
    actions = (Action.stay(buy_water=1), Action.stay(buy_food=1), Action.stay())
    result = step_joint(states, actions, "晴朗", *level6)
    assert result.states[0].cash == 8980
    assert result.states[1].cash == 8960
    assert result.states[2].cash == 9000
```

- [ ] **Step 2: Run RED**

Run from `求解代码/第三问（2）`: `python -m pytest tests/test_data_and_transition.py -q`
Expected: FAIL because modules are missing.

- [ ] **Step 3: Implement grid generator and complete transition**

Generate right/down edges only, normalize them, build symmetric adjacency, and add village price counting before consumption. Reject purchase outside village and purchase combinations exceeding cash/load.

- [ ] **Step 4: Run GREEN**

Run: `python -m pytest tests/test_data_and_transition.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add "求解代码/第三问（2）/模型求解" "求解代码/第三问（2）/tests/test_data_and_transition.py"
git commit -m "feat(q3-2): add level six multiplayer rules"
```

### Task 7: 第六关 Gamma 鲁棒续值与初始采购

**Files:**
- Create: `求解代码/第三问（2）/模型求解/robust_value.py`
- Test: `求解代码/第三问（2）/tests/test_robust_value.py`

**Interfaces:**
- Consumes: one `PlayerState`, `day`, `gamma_remaining`, game/level; never consumes realized future weather。
- Produces: `robust_value(day, state, gamma_remaining, game, level) -> RobustValue`, `plan_initial_purchase(gamma, game, level) -> PlayerState`。

- [ ] **Step 1: Write failing monotonicity and interface tests**

```python
def test_more_storm_budget_never_improves_robust_value(level6):
    state = PlayerState(1, 200, 300, 6000)
    low = robust_value(1, state, 0, *level6)
    high = robust_value(1, state, 2, *level6)
    assert high.feasible <= low.feasible
    if high.feasible:
        assert high.worst_wealth <= low.worst_wealth

def test_robust_value_signature_has_no_future_weather_parameter():
    assert "future_weather" not in inspect.signature(robust_value).parameters
```

- [ ] **Step 2: Run RED**

Run: `python -m pytest tests/test_robust_value.py -q`
Expected: FAIL because robust value is missing.

- [ ] **Step 3: Implement budget-state minimax DP**

```python
@lru_cache(maxsize=None)
def value(day: int, node: int, water: int, food: int, cash: int, gamma: int):
    weather_set = ("晴朗", "高温") if gamma == 0 else ("晴朗", "高温", "沙暴")
    return max_over_actions(min_over_weather(next_value))
```

Use lexicographic `(feasible, worst_wealth)`, Pareto pruning, distance/deadline lower bounds, bounded purchase candidates at village, and deterministic tie-breaks. Initial purchase enumerates feasible integer stocks and selects the best robust value without realized weather.

- [ ] **Step 4: Run GREEN and cache regression**

Run: `python -m pytest tests/test_robust_value.py -q`
Expected: PASS; repeated call returns identical value/action.

- [ ] **Step 5: Commit**

```bash
git add "求解代码/第三问（2）/模型求解/robust_value.py" "求解代码/第三问（2）/tests/test_robust_value.py"
git commit -m "feat(q3-2): add Gamma robust continuation value"
```

### Task 8: 第六关阶段 Nash 与在线滚动策略

**Files:**
- Create: `求解代码/第三问（2）/模型求解/game_rolling.py`
- Test: `求解代码/第三问（2）/tests/test_rolling_game.py`

**Interfaces:**
- Produces: `choose_actions(day, current_weather, public_states, gamma_remaining, config) -> StageEquilibrium`, `solve_stage_game(action_sets, payoffs)`, `rolling_simulation(weather_source, ...)`。

- [ ] **Step 1: Write failing no-lookahead and exploitability tests**

```python
def test_equal_prefixes_produce_identical_current_decision(initial_public_state):
    a = simulate_until_decision(("晴朗", "高温", "沙暴"), stop_day=1)
    b = simulate_until_decision(("晴朗", "沙暴", "晴朗"), stop_day=1)
    assert a.stage_equilibrium == b.stage_equilibrium

def test_pure_stage_equilibrium_has_zero_exploitability(tiny_stage_game):
    eq = solve_stage_game(*tiny_stage_game)
    assert eq.kind == "pure"
    assert eq.epsilon == 0
```

- [ ] **Step 2: Run RED**

Run: `python -m pytest tests/test_rolling_game.py -q`
Expected: FAIL because rolling game is missing.

- [ ] **Step 3: Implement payoff tensor, pure enumeration and verified mixed fallback**

```python
def choose_actions(day, current_weather, public_states, gamma_remaining, config):
    action_sets = tuple(legal_actions(s, current_weather, config) for s in public_states)
    for joint_action in product(*action_sets):
        next_states = step_joint(public_states, joint_action, current_weather, config)
        payoffs[joint_action] = tuple(
            robust_value(day + 1, state, gamma_after, config).score
            for state in next_states
        )
    return solve_stage_game(action_sets, payoffs)
```

Enumerate all unilateral deviations for pure Nash. For no-pure cases solve probability/simplex constraints numerically, then recompute actual epsilon; reject any unverified result.

- [ ] **Step 4: Run GREEN**

Run: `python -m pytest tests/test_rolling_game.py tests/test_robust_value.py -q`
Expected: PASS with no future-weather parameter in the decision stack.

- [ ] **Step 5: Commit**

```bash
git add "求解代码/第三问（2）/模型求解/game_rolling.py" "求解代码/第三问（2）/tests/test_rolling_game.py"
git commit -m "feat(q3-2): implement rolling stage Nash policy"
```

### Task 9: 第六关独立验证、基准、消融和灵敏度实验

**Files:**
- Create: `求解代码/第三问（2）/模型求解/validator.py`
- Create: `求解代码/第三问（2）/模型求解/baselines.py`
- Create: `求解代码/第三问（2）/模型求解/validation_experiments.py`
- Test: `求解代码/第三问（2）/tests/test_validation_experiments.py`

**Interfaces:**
- Produces: `audit_records()`, `stage_exploitability()`, `counterfactual_prefix_test()`, `ex_post_regret()`, `conflict_loss()`, `run_baselines()`, `run_ablation()`, `run_gamma_scan()`, `run_exact_small_game()`。

- [ ] **Step 1: Write failing validation metric tests**

```python
def test_conflict_loss_decomposes_exactly(sample_records):
    loss = conflict_loss(sample_records)
    assert loss.total == loss.move + loss.mine + loss.village

def test_exact_small_game_reports_value_and_action_difference():
    report = run_exact_small_game(days=3, gamma=1)
    assert set(report) >= {"exact_value", "approx_value", "absolute_gap", "action_match"}
    assert 0 <= report["action_match"] <= 1
```

- [ ] **Step 2: Run RED**

Run: `python -m pytest tests/test_validation_experiments.py -q`
Expected: FAIL because validation modules are missing.

- [ ] **Step 3: Implement independent evidence chain**

Recompute every daily record using direct formulas, not `step_joint`. Add B0/B1/B2/Full, `-Game/-Rolling/-FutureValue/-Robust`, Gamma integer scan, R/M/C0/n scenario scans, ex-post full-information best response, and a connected short-horizon exact joint-state comparison.

- [ ] **Step 4: Run GREEN**

Run: `python -m pytest tests/test_validation_experiments.py -q`
Expected: PASS; integer residual maximum equals 0.

- [ ] **Step 5: Commit**

```bash
git add "求解代码/第三问（2）/模型求解/validator.py" "求解代码/第三问（2）/模型求解/baselines.py" "求解代码/第三问（2）/模型求解/validation_experiments.py" "求解代码/第三问（2）/tests/test_validation_experiments.py"
git commit -m "feat(q3-2): add validation and sensitivity experiments"
```

### Task 10: 第六关导出、运行入口与全项目验证

**Files:**
- Create: `求解代码/第三问（2）/模型求解/export.py`
- Create: `求解代码/第三问（2）/模型求解/run.py`
- Test: `求解代码/第三问（2）/tests/test_export_and_run.py`
- Modify: `README.md` only if the existing root run instructions require adding the two new commands; otherwise leave unchanged.

**Interfaces:**
- Produces: `run_experiment(config, weather_sequence, gamma, output_root)`, `main()`, CSV/JSON files in Q3(2) output directories。

- [ ] **Step 1: Write failing output-schema test**

```python
def test_run_exports_required_validation_fields(tmp_path, short_weather):
    summary = run_experiment(short_level6, short_weather, gamma=1, output_root=tmp_path)
    assert set(summary) >= {"players", "epsilon_max", "conflict_loss", "information_leakage_ok"}
    assert summary["information_leakage_ok"] is True
    assert (tmp_path / "结果验证" / "模型检验摘要.json").exists()
```

- [ ] **Step 2: Run RED**

Run: `python -m pytest tests/test_export_and_run.py -q`
Expected: FAIL because run/export modules are missing.

- [ ] **Step 3: Implement reproducible CLI and bounded experiment defaults**

Default CLI writes the Gamma reference policy and bounded validation experiments. It accepts a weather file for replay but passes only one day's weather at a time to `choose_actions`. Write daily states, stage equilibria, audit, baselines, ablations, Gamma scan, regret and small-instance comparison; do not import plotting libraries.

- [ ] **Step 4: Run all new and existing tests**

Run from repository root:

```powershell
python -m pytest "求解代码\第三问（1）\tests" -q
python -m pytest "求解代码\第三问（2）\tests" -q
python -m pytest "求解代码\第一问\tests" "求解代码\第二问\tests" -q
python -m 模型求解.run  # once from each third-question directory
git diff --check
```

Expected: all tests PASS, both runs exit 0, all rule residuals are 0, accepted equilibria satisfy tolerance, and no image files are created.

- [ ] **Step 5: Inspect final change scope and commit**

```bash
git status --short
git diff --stat HEAD~10
git add "求解代码/第三问（2）" README.md
git commit -m "feat(q3): complete multiplayer game solvers"
```

Do not stage the user-provided untracked DOCX or `._qa` extraction helpers.
