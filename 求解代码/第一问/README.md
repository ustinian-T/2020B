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

## 模块

- `config.py`：官方参数、30 天天气、两关地图和功能节点。
- `preprocess.py`：地图完整性、连通性和 BFS 距离检查。
- `rules.py`：天气—行动消耗与动作合法性。
- `solver.py`：完整逐日有限期优化模型及 HiGHS 精确求解。
- `checker.py`：脱离求解器内部状态的逐日规则复算。
- `run.py`：统一求解两关并生成 JSON/CSV。

结果统一写入 `结果输出/`。公共 `数据/Result.xlsx` 只作为模板，不会原地覆盖。
