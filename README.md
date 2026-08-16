# 2020B 穿越沙漠

2020 年高教社杯全国大学生数学建模竞赛 B 题“穿越沙漠”的建模、求解与论文材料仓库。当前已完成第一问的两关确定性单玩家最优策略求解、独立规则复算、灵敏性分析、结果表填写、求解报告、可视化图表与 LaTeX 论文底稿；第二、第三问占位目录已建立，后续物料按相同约定继续归档。

## 第一问结果

| 关卡 | 最优终端财富 | 到达日 | 初始购买（水/食物） | 有效挖矿天数 |
| --- | ---: | ---: | ---: | ---: |
| 第一关 | 10470 元 | 第 24 天 | 178 / 333 箱 | 7 天 |
| 第二关 | 12730 元 | 第 30 天 | 130 / 405 箱 | 13 天 |

两关均由 SciPy `milp` 调用 HiGHS 精确求解，MIP gap 为 0；输出策略另由独立 checker 按题目规则逐日复算。图 5-1–图 5-5 由 `求解代码/第一问/图表生成代码/` 下的 MATLAB 脚本读取上述 CSV 后生成，已通过纯白底、Nature 色板、样式不超 2 次等论文级校验。

## 仓库目录结构

仓库按 **“按问分组 + 子专题命名（中文为主）”** 组织。第一问已完整展开；第二、第三问占位目录以同名约定预留。

```text
2020B/
├── README.md                                  本说明
├── .gitignore
├── docs/                                      设计文档与计划
│   └── superpowers/                           求解与建模的过程文档
├── 题目/                                      原题、附件、官方结果模板
├── 数据/                                      各问公用数据
├── 建模文件/                                  建模手册与过程文档（按问）
│   └── 第一问建模手册_已知天气单玩家最优策略.docx
├── 求解报告/                                  已完成的求解报告（DOCX）
│   └── 第一问求解报告.docx
├── latex/                                     LaTeX 论文工作区
│   ├── 2020B.tex                              采用 CUMCM v2.6 文档类的论文底稿
│   ├── 2020B.pdf                              同上的参考渲染
│   └── cumcmthesis.cls                        随仓库提供的 CUMCM 文档类
└── 求解代码/                                  按问分组的求解物料
    ├── 第一问/
    │   ├── README.md
    │   ├── 建模思路/                          建模推导、问题分析、Bellman/MILP 路线选择
    │   ├── 模型求解/                          Python 求解器、规则、复算器、灵敏性脚本
    │   ├── 图表生成代码/                      MATLAB 增强版论文图表脚本
    │   ├── figures_enhanced/                  增强版图表 PNG
    │   ├── 样式追踪表/                        增强版图表样式使用追踪 CSV
    │   ├── 结果输出/                          CSV/JSON/Excel 结果（提交中）
    │   ├── 结果验证/                          图表验证报告与图注（Markdown）
    │   ├── 论文草稿/                          增强版论文图表稿及参考 PDF
    │   ├── 导出结果.mjs                       结果表导出脚本
    │   ├── 生成求解报告.py                    Word 求解报告生成脚本
    │   └── tests/                             本地复算测试目录（不入库，见下）
    ├── 第二问/                                占位（README 约定见下）
    ├── 第三问（1）/                           占位
    └── 第三问（2）/                           占位
```

**约定说明：**

- **“按问分组”**：每个 `求解代码/<问>/` 自成一个完整单元，包含 `建模思路/`、`模型求解/` 或 `图表生成代码/`、`figures_enhanced/`、`结果输出/`、`结果验证/`、`论文草稿/` 等子目录。第二、第三问动工后，沿用同一套子目录命名。
- **`tests/` 不入库**：求解代码下的 `tests/` 目录保留在本地以便复算，符合“测试代码不上传”的方针，已在 `.gitignore` 中以 `求解代码/**/tests/` 规则屏蔽。
- **`figures_enhanced/` 保留英文目录名**：增强版 LaTeX 稿使用 `\graphicspath{{../figures_enhanced/}}` 相对路径，MATLAB 脚本也将五张增强版 PNG 统一写入该目录。
- **Office 临时锁文件 `~$*.docx`**：被 `.gitignore` 忽略，关闭 Word 后会自动消失。

## 运行方法（第一问）

环境建议为 Python 3.10，并安装 `numpy`、`scipy`、`pytest` 与 `python-docx`。

```powershell
# 测试（tests/ 保留在本地，未上传）
python -m pytest "求解代码\第一问\tests" -q

# 求解 + 灵敏性
cd 求解代码\第一问
python -m 模型求解.run
python -m 模型求解.sensitivity
python "生成求解报告.py"
```

MATLAB 增强版图表脚本位于 `求解代码/第一问/图表生成代码/`，在 MATLAB R2023b 中运行后会将五张 PNG 写回 `求解代码/第一问/figures_enhanced/`。脚本只读取仓库已有 CSV，不会修改模型结果。

## LaTeX 论文排版

论文模板在 `latex/2020B.tex`，使用全国大学生数学建模竞赛官方文档类 `cumcmthesis`。该文档类**不是** TeX Live / MiKTeX 自带的，但已随仓库提供（`latex/cumcmthesis.cls` + `latex/.latexmkrc`），clone 后即可编译，无需额外下载或 IDE 设置。

### 环境要求

- **编译引擎**：必须用 XeLaTeX，不能用 pdflatex（`cls` 内有 `\RequireXeTeX` 强制检查，`pdflatex` 会立刻终止）。
- **文档类**：`latex/cumcmthesis.cls` 与 `2020B.tex` 同级，LaTeX 会优先从当前目录读取，无需安装到系统。该文件来自竞赛官方 LaTeX 模板（cumcmthesis v2.6），升级模板时可自行覆盖。
- **中文字体**：`cls` 内写死 Times New Roman、Arial 以及宋体（SimSun）、楷体（simkai.ttf）、黑体等字体；Windows 全部自带，macOS / Linux 需安装对应中文字体，或在 `cls` 中改用 Fandol 等开源字体。

### 编译命令

项目根已经在 `latex/.latexmkrc` 中把所有 latexmk 触发统一改写到 xelatex（包括 IDE 默认的 `-pdf` 调用），所以下列任何一种都能成功：

```bash
cd latex

# 推荐：什么都不用记
latexmk 2020B.tex

# IDE 默认（TeXstudio / VS Code LaTeX Workshop）带 -pdf 也能用
latexmk -synctex=1 -interaction=nonstopmode -file-line-error -pdf -outdir=. 2020B.tex

# 想完全显式指定
latexmk -xelatex 2020B.tex

# 完全脱离 latexmk
xelatex -synctex=1 -interaction=nonstopmode 2020B.tex
```

`*.aux`、`*.log`、`*.fdb_latexmk`、`*.fls`、`*.synctex.gz`、`*.xdv` 等编译产物已在仓库根 `.gitignore` 中忽略，IDE 反复构建不会脏仓库。

### 如何在 IDE 中配置

- **TeXstudio** → Options → Configure TeXstudio → Commands → "Build & View"，把命令从默认的 `latexmk -synctex=1 -interaction=nonstopmode -file-line-error -pdf` 改成 `latexmk -synctex=1 -interaction=nonstopmode -file-line-error -xelatex`（或者直接 `latexmk 2020B.tex`，由项目内的 `.latexmkrc` 替你接管）。
- **VS Code LaTeX Workshop** → settings.json 中把 `latex-workshop.latex.recipe.default` 指向 `latexmk (xelatex)` 这一条预置，或显式写 `"args": ["-xelatex"]`。
- 也可以**完全不改 IDE**：因为 `.latexmkrc` 已经把 pdflatex 调用偷偷换成 xelatex，IDE 默认 `-pdf` 命令也能跑通（上表第 2 行已实测）。

如果仍然看到 `* XeTeX is required to compile this document. * Sorry!`，说明你的 latexmk 没读到这个 `.latexmkrc`，常见原因：项目被以绝对路径调用且 `latex/` 不在当前目录，或 TeX Live 自带的系统级 `latexmkrc` 先读到。补一条 `latexmk -xelatex 2020B.tex` 强制指定即可绕开。
