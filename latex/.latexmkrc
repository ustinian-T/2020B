# latexmk 配置文件，让 `latexmk 2020B.tex` 或 IDE 一键构建自动走 XeLaTeX。
# cumcmthesis.cls 内置 \RequireXeTeX，pdflatex 会被立刻中断。

# 5 = xelatex（1=pdflatex, 2=ps, 3=dvipdf, 4=lualatex, 5=xelatex）
$pdf_mode = 5;

# 本模板用 \begin{thebibliography} ... \bibitem 列举参考文献，不读 .bib。
# 关闭 bibtex/biber 自动运行，避免 latexmk 误启 bibtex 失败。
$bibtex_use = 0;
$biber = 0;

# 中间产物全部落在当前目录，便于仓库根 .gitignore 的 *.aux/*.log/synctex 等模式统一忽略。
$out_dir = '.';

# 同步生成 synctex.gz，正反向跳转编辑器均可用。
$synctex = 1;

# 把 pdflatex 命令替换为 xelatex，连带可选参数一并透传。
# 这样即使 IDE 默认 Build 命令带着 -pdf（TeXstudio / VS Code LaTeX Workshop 默认），
# latexmk 实际调用的仍然是 xelatex，编译可以正常完成。
$pdflatex = 'xelatex %O -synctex=1 -interaction=nonstopmode -file-line-error %S';
