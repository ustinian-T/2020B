# 第一问求解代码

本目录用于求解 2020 年高教社杯全国大学生数学建模竞赛 B 题第一问的第一关和第二关。

## 运行

在项目根目录执行：

```powershell
$env:PYTHONPATH='求解代码\第一问'
python -m 模型求解.run
```

完整测试：

```powershell
python -m pytest 求解代码\第一问\tests -q
```

灵敏性分析：

```powershell
python -m 模型求解.sensitivity
```

## 模型与求解器

建模手册 [`建模文件/第一问建模手册_已知天气单玩家最优策略.docx`](../../建模文件/第一问建模手册_已知天气单玩家最优策略.docx)
规定**主模型为"完整地图上的稀疏标签动态规划（DP）"**，辅以三种精确剪枝：
Pareto 支配剪枝（§5.2）、时间可达性剪枝（§5.3）、乐观收益上界剪枝（§5.4）；
MILP 仅作可选独立校验（§2.3）。

实现按手册双轨落地：

- **`dp.py`** — 建模手册规定的主模型完整实现：稀疏标签 DP +
  三种剪枝 + 村庄补给闭包 + 终点吸收 + 前驱回溯。**正确性已通过 16 个
  单元测试与对 MILP 的等价对照验证**。受 Python 性能与本题线性 cash
  阶段 Pareto 剪枝无效的组合限制，纯 DP 在完整问题规模下耗时较长，
  故保留为建模手册规定的主模型与交叉验证工具。
- **`milp.py`** — 建模手册 §5.9 / §6.4 描述的"等价整数网络流展开"：
  用 0-1 / 整数变量一次性展开所有天 /库存 /动作 /采购约束，由 HiGHS
  分支定界求解。这是当前默认生产求解器，可在数秒内得到 10470 / 12730
  的全局最优。
- **`solver.py`** — 入口与调度；默认走 MILP，可通过
  `SolveOptions(use_dp=True)` 切换至 DP 主路线（适合小问题 / 单元测试 /
  规则对照）。

## 模块

- `config.py`：官方参数、30 天天气、两关地图和功能节点。
- `preprocess.py`：地图完整性、连通性和 BFS 距离检查。
- `rules.py`：天气—行动消耗与动作合法性。
- `dp.py`：稀疏标签动态规划（建模手册主模型）。
- `milp.py`：等价整数网络流展开（HiGHS MILP）。
- `solver.py`：调度入口与公共 API。
- `checker.py`：脱离求解器内部状态的逐日规则复算。
- `run.py`：统一求解两关并生成 JSON/CSV。
- `sensitivity.py`：单因素离散扰动 + 重求解。

结果统一写入 `结果输出/`。公共 `数据/Result.xlsx` 只作为模板，不会原地覆盖。

## 增强版图表

- MATLAB 入口：`图表生成代码/generate_q1_figures_enhanced.m`
- 图表目录：`figures_enhanced/`
- 图表说明：`结果验证/q1_figure_notes_enhanced.md`
- Word 图表说明：`结果验证/第一问图表说明.docx`
- 校验报告：`结果验证/validation_report_enhanced.md`
- 样式追踪：`样式追踪表/tab_q1_figure_style_tracking_enhanced.csv`
- 论文草稿：`论文草稿/main_enhanced.tex`

第一问仅维护增强版图表链路，普通版文件不再保留。