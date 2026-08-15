# 第一问精确动态规划求解 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为第一关和第二关构建可复现、可审计的精确动态规划求解器，并输出逐日结果、已填写 Excel、DOCX 求解报告和完整 GitHub 项目。

**Architecture:** 公共规则与关卡配置分离；预处理模块负责图校验和距离下界；求解器以日末 `(day, node, water, food)` 为状态并保存最大现金与前驱；独立 checker 只根据输出动作重放规则。所有结果先汇总到统一 JSON，再派生 CSV、Excel 和 DOCX，避免跨文件数值漂移。

**Tech Stack:** Python 3、标准库、pytest、NumPy；Excel 使用工作区提供的 `@oai/artifact-tool`；DOCX 使用工作区提供的 `python-docx`/OOXML 辅助与文档渲染流程；Git/GitHub。

## Global Constraints

- 第一关与第二关都必须完成；暂不创建绘图代码或图片。
- 第一关节点配置为起点 1、村庄 15、矿山 12、终点 27；采用用户核对的 27 节点邻接表。
- 第二关为 8×8 错位六邻域图，起点 1、村庄 39/62、矿山 30/55、终点 64。
- 公共参数、天气和日末状态口径严格来自题目与已确认设计。
- `数据/Result.xlsx` 不原地覆盖；生成 `求解代码/第一问/结果输出/Result_已填写.xlsx`。
- 报告输出必须为 `求解报告/第一问求解报告.docx`，内容详细且可直接供论文写作参考。
- GitHub 推送整个项目，包括题目、数据和建模文件；排除缓存、临时 QA 和构建垃圾。

---

### Task 1: 关卡配置与地图预处理

**Files:**
- Create: `求解代码/第一问/模型求解/__init__.py`
- Create: `求解代码/第一问/模型求解/config.py`
- Create: `求解代码/第一问/模型求解/preprocess.py`
- Create: `求解代码/第一问/tests/test_config_preprocess.py`

**Interfaces:**
- Produces: `GameConfig`, `LevelConfig`, `build_level_one()`, `build_level_two()`, `validate_level(level)`, `bfs_distances(level, target)`。

- [ ] **Step 1: 写失败测试**：断言天气恰为 30 天、第一关边表对称连通且功能节点正确、第二关边数与六邻域模板一致、两关起点均可达终点。
- [ ] **Step 2: 运行红灯**：`python -m pytest 求解代码/第一问/tests/test_config_preprocess.py -v`，预期因模块不存在失败。
- [ ] **Step 3: 最小实现**：使用不可变 dataclass 保存参数与关卡；第一关逐边录入；第二关按奇偶行 delta 生成；BFS 返回所有节点到目标的单位边距离。
- [ ] **Step 4: 运行绿灯**：同一测试命令全部通过。
- [ ] **Step 5: 提交**：仅提交本任务配置、预处理和测试文件。

### Task 2: 规则引擎与独立策略检查器

**Files:**
- Create: `求解代码/第一问/模型求解/rules.py`
- Create: `求解代码/第一问/模型求解/checker.py`
- Create: `求解代码/第一问/tests/test_rules_checker.py`

**Interfaces:**
- Consumes: `GameConfig`, `LevelConfig`。
- Produces: `action_consumption(weather, action) -> tuple[int,int]`、`replay_strategy(level, game, initial_purchase, daily_records) -> CheckResult`。

- [ ] **Step 1: 写失败测试**：覆盖三种天气三类动作倍率、沙暴禁行、到矿当日不能挖、村庄采购价格与负重、起点只采购一次、终点半价回收。
- [ ] **Step 2: 运行红灯**：`python -m pytest 求解代码/第一问/tests/test_rules_checker.py -v`，预期因规则函数不存在失败。
- [ ] **Step 3: 最小实现**：checker 从第 0 天采购开始，逐日校验动作起点/终点、邻接、天气、消耗、采购、现金和负重，并计算终端财富。
- [ ] **Step 4: 运行绿灯**：规则测试全部通过。
- [ ] **Step 5: 提交**：提交规则引擎、checker 与测试。

### Task 3: 稀疏标签动态规划求解器

**Files:**
- Create: `求解代码/第一问/模型求解/solver.py`
- Create: `求解代码/第一问/tests/test_solver.py`

**Interfaces:**
- Consumes: `LevelConfig`, `GameConfig`, BFS 距离和规则函数。
- Produces: `solve(level, game, options) -> SolveResult`，其中包含最优财富、到达日、初始采购、逐日记录、标签统计和运行时间。

- [ ] **Step 1: 写失败测试**：构造 2—4 节点小图，验证直接到达、沙暴等待、经矿山挖矿、村庄补给、终点剩余资源回收；比较启用/关闭剪枝的最优值。
- [ ] **Step 2: 运行红灯**：`python -m pytest 求解代码/第一问/tests/test_solver.py -v`，预期求解器缺失失败。
- [ ] **Step 3: 最小实现**：枚举可行初始采购标签；按天扩展 Stay/Move/Mine；村庄执行精确采购闭包；同 `(day,node,water,food)` 仅保留最大现金和前驱。
- [ ] **Step 4: 加入安全剪枝**：实现同日同节点 Pareto 前沿、考虑未来沙暴的移动日可达性和乐观收益上界；所有剪枝可通过选项关闭。
- [ ] **Step 5: 运行绿灯及回归**：求解器测试、规则测试、配置测试全部通过。
- [ ] **Step 6: 提交**：提交求解器与测试。

### Task 4: 两关运行、统一结果与 Excel/CSV 输出

**Files:**
- Create: `求解代码/第一问/模型求解/run.py`
- Create: `求解代码/第一问/导出结果.mjs`
- Create: `求解代码/第一问/README.md`
- Create: `求解代码/第一问/结果输出/第一关逐日策略.csv`
- Create: `求解代码/第一问/结果输出/第二关逐日策略.csv`
- Create: `求解代码/第一问/结果输出/求解摘要.json`
- Create: `求解代码/第一问/结果输出/Result_已填写.xlsx`
- Create: `求解代码/第一问/tests/test_outputs.py`

**Interfaces:**
- Consumes: `solve()` 与 `replay_strategy()`。
- Produces: 两关统一摘要 JSON、逐日 CSV、填写后的 Excel 模板。

- [ ] **Step 1: 写失败测试**：断言输出记录包含日期、区域、行动、天气、采购量、资金、水、食物、负重；终点后不再输出日记录；JSON 与 CSV 终值一致。
- [ ] **Step 2: 运行红灯**：输出测试因运行入口和文件不存在失败。
- [ ] **Step 3: 实现运行入口**：依次求解两关、调用独立 checker、写 UTF-8 BOM CSV 和结构化 JSON；未通过 checker 时禁止导出。
- [ ] **Step 4: 运行两关**：执行 `python 求解代码/第一问/模型求解/run.py`，记录实际最优值、策略和性能。
- [ ] **Step 5: 生成 Excel**：从公共模板读取布局，将两关日末数据写入对应列，保留模板结构和格式，导出到结果目录。
- [ ] **Step 6: 验证输出**：检查关键单元格、公式错误扫描、CSV/JSON/Excel 终值一致性。
- [ ] **Step 7: 提交**：提交运行入口、结果、导出脚本、README 和测试。

### Task 5: 灵敏性分析与 DOCX 求解报告

**Files:**
- Create: `求解代码/第一问/模型求解/sensitivity.py`
- Create: `求解代码/第一问/结果输出/灵敏性分析.csv`
- Create: `求解代码/第一问/生成求解报告.py`
- Create: `求解报告/第一问求解报告.docx`
- Create: `求解代码/第一问/tests/test_report_inputs.py`

**Interfaces:**
- Consumes: 统一求解摘要、逐日记录、验证统计和参数扰动结果。
- Produces: 灵敏性分析 CSV 与最终 DOCX 报告。

- [ ] **Step 1: 写失败测试**：断言报告输入包含四个论文前置章节、模型公式所需变量、两关关键结果、检验统计和灵敏性结果，且不存在未解析模板标记。
- [ ] **Step 2: 运行红灯**：报告输入测试因生成模块不存在失败。
- [ ] **Step 3: 实现灵敏性分析**：对负重、初始资金、矿山收益和截止日期使用明确的离散扰动集合重新求解，输出财富、到达日、挖矿天数和策略摘要。
- [ ] **Step 4: 标记 DOCX 创建操作**：使用工作区 Node 运行一次 `mark_artifact_operation_started.mjs --operation-kind create --expected-output-count 1 --output-format docx`。
- [ ] **Step 5: 生成报告**：采用正式建模报告样式，包含问题重述、问题分析、模型假设、三线符号表、模型建立、目标函数/决策变量/约束、求解算法、两关结果、策略分析、模型检验、灵敏性分析和参考文献。
- [ ] **Step 6: 文档校验**：结构检查标题、表格、公式和数值；使用文档渲染器逐页检查。若 LibreOffice 缺失，则尝试本机 Word 导出；仍失败时执行结构审计并如实记录限制。
- [ ] **Step 7: 提交**：提交灵敏性数据、报告生成器、测试和最终 DOCX。

### Task 6: 全量验证与 GitHub 发布

**Files:**
- Create: `.gitignore`
- Create: `README.md`
- Modify: all task-related project artifacts as required by final verification。

**Interfaces:**
- Consumes: 全部项目文件和测试命令。
- Produces: 干净的 `main` 分支及 GitHub 仓库 `ustinian-T/2020B`。

- [ ] **Step 1: 全量验证**：运行完整 pytest、两关求解、checker、输出一致性检查、DOCX 结构审计和 `git diff --check`。
- [ ] **Step 2: 范围检查**：确认题目、数据、建模文件、求解代码、求解报告、LaTeX 目录和设计文档均在提交范围；排除 `._qa/`、`__pycache__/`、`.pytest_cache/` 和临时文件。
- [ ] **Step 3: 创建项目 README**：说明问题、目录、运行命令、依赖、结果位置和验证方法。
- [ ] **Step 4: 配置远端**：将 `origin` 设置为 `https://github.com/ustinian-T/2020B.git`，分支保持 `main`。
- [ ] **Step 5: 提交全项目**：显式检查 `git status` 与暂存清单后提交。
- [ ] **Step 6: 推送**：执行 `git push -u origin main`；若认证或网络失败，停止并给出精确人工命令。
- [ ] **Step 7: 远端核验**：确认远端 main 指向本地最终提交，并汇总提交 SHA、验证结果与关键输出。
