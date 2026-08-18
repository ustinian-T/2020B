# 第三问（1）求解代码

本目录用于求解 2020 年高教社杯全国大学生数学建模竞赛 B 题第三问的**第五关**（双玩家博弈均衡策略）。

## 运行

### MATLAB 绘图

在 `01MATLAB绘图代码/` 目录下执行：

```matlab
mainQ3_1_plot
```

或单独绘制：

```matlab
fig31_resource
```

### Python 模型求解

在项目根目录执行：

```powershell
$env:PYTHONPATH='求解代码\第三问（1）'
python -m 模型求解.run
```

完整测试：

```powershell
python -m pytest 求解代码\第三问（1）\tests -q
```

灵敏性分析：

```powershell
python -m 模型求解.sensitivity
```

## 模块

- `config.py`：第五关参数配置（双玩家、地图节点、天气分布）。
- `single_dp.py`：单玩家动态规划基准求解器。
- `game_open_loop.py`：双玩家开环 Nash 均衡求解。
- `transition.py`：状态转移与动作合法性检查。
- `data_loader.py`：CSV 数据加载与验证。
- `export.py`：结果导出（JSON/CSV）。
- `validator.py`：模型正确性验证。
- `sensitivity.py`：参数灵敏性分析。
- `run.py`：统一求解入口。

结果统一写入 `结果输出/`。

## 增强版图表

- MATLAB 入口：`01MATLAB绘图代码/fig31_resource.m`
- 图表目录：`03图片输出/`
- 论文图表说明：`04论文图表说明/第三问模型结果图表分析_论文终稿.docx`
- 样式追踪：`样式追踪表/tab_q3_figure_style_tracking.csv`
