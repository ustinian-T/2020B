# 2020B 穿越沙漠

2020 年高教社杯全国大学生数学建模竞赛 B 题“穿越沙漠”的建模、求解与论文材料仓库。当前已完成第一问的两关确定性单玩家最优策略求解、独立规则复算、灵敏性分析、结果表填写和求解报告；暂未制作可视化图形。

## 第一问结果

| 关卡 | 最优终端财富 | 到达日 | 初始购买（水/食物） | 有效挖矿天数 |
| --- | ---: | ---: | ---: | ---: |
| 第一关 | 10470 元 | 第 24 天 | 178 / 333 箱 | 7 天 |
| 第二关 | 12730 元 | 第 30 天 | 130 / 405 箱 | 13 天 |

两关均由 SciPy `milp` 调用 HiGHS 精确求解，MIP gap 为 0；输出策略另由独立 checker 按题目规则逐日复算。

## 目录说明

- `题目/`：原题、附件与官方结果模板。
- `数据/`：各问公用数据。
- `建模文件/`：建模手册和过程文档。
- `求解代码/第一问/模型求解/`：配置、预处理、规则、优化器、复算器和灵敏性分析代码。
- `求解代码/第一问/结果输出/`：两关逐日策略、摘要、灵敏性分析与已填写结果表。
- `求解报告/第一问求解报告.docx`：供论文撰写使用的完整第一问报告。
- `latex/`：LaTeX 论文工作区。

## 运行方法

环境建议为 Python 3.10，并安装 `numpy`、`scipy`、`pytest` 与 `python-docx`。

```powershell
python -m pytest "求解代码\第一问\tests" -q
python -m 模型求解.run
python -m 模型求解.sensitivity
python "生成求解报告.py"
```

后三条命令请在 `求解代码/第一问` 目录下执行。结果表导出脚本依赖本项目使用的文档/表格运行时，常规复算只需读取 CSV 与 JSON 输出。

## LaTeX 论文排版

论文模板在 `latex/2020B.tex`，使用全国大学生数学建模竞赛官方文档类 `cumcmthesis`。该文档类**不是** TeX Live / MiKTeX 自带的，但已随仓库提供（`latex/cumcmthesis.cls`），clone 后即可编译，无需额外下载。

### 环境要求

- **编译引擎**：必须用 XeLaTeX，不能用 pdflatex（`cls` 内有 `\RequireXeTeX` 强制检查）。
- **文档类**：`latex/cumcmthesis.cls` 与 `2020B.tex` 同级，LaTeX 会优先从当前目录读取，无需安装到系统。该文件来自竞赛官方 LaTeX 模板（cumcmthesis v2.6），升级模板时可自行覆盖。
- **中文字体**：`cls` 内写死 Times New Roman、Arial 以及宋体（SimSun）、楷体（simkai.ttf）、黑体等字体；Windows 全部自带，macOS / Linux 需安装对应中文字体，或在 `cls` 中改用 Fandol 等开源字体。

### 编译命令

```bash
cd latex
latexmk -xelatex 2020B.tex
# 或手动编译（交叉引用/目录需跑两遍）
xelatex 2020B.tex
```

`*.aux`、`*.log` 等编译产物已在 `.gitignore` 中忽略，无需提交。
