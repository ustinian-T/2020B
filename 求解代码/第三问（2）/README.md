# 第三问（2）求解代码

本目录用于求解 2020 年高教社杯全国大学生数学建模竞赛 B 题第三问的**第六关**（多玩家鲁棒博弈策略）。

## 运行

### MATLAB 绘图

在 `01MATLAB绘图代码/` 目录下执行：

```matlab
mainQ3plot
```

或单独绘制各子图：

```matlab
fig32_heatmap    % 参数敏感性热力图
fig33_gamma      % Gamma 鲁棒权衡分析
fig34_compare    % 基准与消融实验对比
fig35_regret     % Ex-post-Regret 分析
fig36_scale      % 玩家规模扩展分析
fig37_rolling    % 逐日滚动策略轨迹
```

### Python 模型求解

在项目根目录执行：

```powershell
$env:PYTHONPATH='求解代码\第三问（2）'
python -m 模型求解.run
```

完整测试：

```powershell
python -m pytest 求解代码\第三问（2）\tests -q
```

灵敏性分析：

```powershell
python -m 模型求解.sensitivity
```

## 模块

- `config.py`：第六关参数配置（多玩家、Gamma 鲁棒性、滚动策略）。
- `game_rolling.py`：多玩家逐日滚动 Nash 均衡求解。
- `robust_value.py`：鲁棒价值函数与 Gamma 调节。
- `baselines.py`：基准策略（贪心、均匀、保守）。
- `transition.py`：状态转移与动作合法性检查。
- `data_loader.py`：CSV 数据加载与验证。
- `export.py`：结果导出（JSON/CSV）。
- `validator.py`：模型正确性验证。
- `validation_experiments.py`：消融实验与对照实验。
- `run.py`：统一求解入口。

结果统一写入 `结果输出/`。

## 增强版图表

- MATLAB 入口：`01MATLAB绘图代码/mainQ3plot.m`
- 图表目录：`03图片输出/`
- 论文图表说明：`04论文图表说明/第三问模型结果图表分析_论文终稿.docx`
- 样式追踪：`样式追踪表/tab_q3_figure_style_tracking.csv`
