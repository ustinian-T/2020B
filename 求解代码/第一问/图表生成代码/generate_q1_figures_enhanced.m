%% 第一问增强版 MATLAB 论文图表
% 只读取仓库已有 CSV，不修改模型结果，不覆盖基础版图表。
% 运行环境：MATLAB R2023b

clear; close all; clc;

set(0, 'DefaultTextFontName', 'Microsoft YaHei');
set(0, 'DefaultAxesFontName', 'Microsoft YaHei');
set(0, 'DefaultAxesFontSize', 11);
set(0, 'DefaultTextFontSize', 11);

natureColors = [
    110 143 178;
    125 164 148;
    234 182 122;
    229 167 154;
    193 110 113;
    171 200 229;
    216 160 193;
    159 141 184;
    208 208 138
] / 255;

scriptDir = fileparts(mfilename('fullpath'));
projectRoot = fileparts(fileparts(fileparts(scriptDir)));
dataDir = fullfile(projectRoot, '求解代码', '第一问', '结果输出');
figureDir = fullfile(projectRoot, '求解代码', '第一问', 'figures_enhanced');
if ~exist(figureDir, 'dir'), mkdir(figureDir); end

T1 = readChineseTable(fullfile(dataDir, '第一关逐日策略.csv'));
T2 = readChineseTable(fullfile(dataDir, '第二关逐日策略.csv'));
TS = readChineseTable(fullfile(dataDir, '灵敏性分析.csv'));

assert(height(T1) == 25 && height(T2) == 31, '逐日策略记录数异常');
assert(T1.('剩余资金数')(end) == 10470, '第一关终端财富异常');
assert(T2.('剩余资金数')(end) == 12730, '第二关终端财富异常');
assert(all([T1.('剩余水量')(end), T1.('剩余食物量')(end), ...
            T2.('剩余水量')(end), T2.('剩余食物量')(end)] == 0), ...
       '终点库存应为零');

%% 图5-1 增强版策略故事线
f1 = figure('Position', [60 60 1180 720], 'Color', 'w');
tl1 = tiledlayout(2, 1, 'TileSpacing', 'compact', 'Padding', 'compact');
drawStrategyStory(nexttile, T1, 'a 第一关策略故事线', natureColors, true);
drawStrategyStory(nexttile, T2, 'b 第二关策略故事线', natureColors, false);
title(tl1, '两关逐日行动、天气与关键决策', 'FontSize', 15, ...
    'FontWeight', 'bold');
exportgraphics(f1, fullfile(figureDir, 'fig_q1_strategy_storyboard.png'), ...
    'Resolution', 300, 'BackgroundColor', 'w');

%% 图5-2 增强版资源约束图
f2 = figure('Position', [60 60 1180 690], 'Color', 'w');
tl2 = tiledlayout(2, 1, 'TileSpacing', 'compact', 'Padding', 'compact');
drawResourceRibbon(nexttile, T1, 'a 第一关资源余量与负重率', natureColors);
drawResourceRibbon(nexttile, T2, 'b 第二关资源余量与负重率', natureColors);
title(tl2, '库存消耗、阶段补给与负重约束', 'FontSize', 15, ...
    'FontWeight', 'bold');
exportgraphics(f2, fullfile(figureDir, 'fig_q1_resource_ribbon.png'), ...
    'Resolution', 300, 'BackgroundColor', 'w');

%% 图5-3 增强版事件现金流
f3 = figure('Position', [60 60 1180 680], 'Color', 'w');
tl3 = tiledlayout(2, 1, 'TileSpacing', 'compact', 'Padding', 'compact');
drawCashWaterfall(nexttile, T1, 'a 第一关关键事件现金流', natureColors);
drawCashWaterfall(nexttile, T2, 'b 第二关关键事件现金流', natureColors);
title(tl3, '采购支出、挖矿收入与累计财富', 'FontSize', 15, ...
    'FontWeight', 'bold');
exportgraphics(f3, fullfile(figureDir, 'fig_q1_cashflow_waterfall.png'), ...
    'Resolution', 300, 'BackgroundColor', 'w');

%% 图5-4 增强版灵敏性棒棒糖图
f4 = figure('Position', [60 60 1180 620], 'Color', 'w');
tl4 = tiledlayout(1, 2, 'TileSpacing', 'compact', 'Padding', 'compact');
drawSensitivityLollipop(nexttile, TS, '第一关', 'a 第一关扰动响应', natureColors);
drawSensitivityLollipop(nexttile, TS, '第二关', 'b 第二关扰动响应', natureColors);
title(tl4, '参数扰动下最优财富响应排序', 'FontSize', 15, ...
    'FontWeight', 'bold');
exportgraphics(f4, fullfile(figureDir, 'fig_q1_sensitivity_lollipop.png'), ...
    'Resolution', 300, 'BackgroundColor', 'w');

%% 图5-5 增强版策略总览仪表盘
f5 = figure('Position', [60 50 1180 760], 'Color', 'w');
tl5 = tiledlayout(2, 2, 'TileSpacing', 'compact', 'Padding', 'compact');
drawActionComposition(nexttile, T1, T2, natureColors);
drawHeadlineWealth(nexttile, T1, T2, natureColors);
drawDecisionCounts(nexttile, T1, T2, natureColors);
drawSensitivityEnvelope(nexttile, TS, natureColors);
title(tl5, '第一问两关最优策略核心结果总览', 'FontSize', 15, ...
    'FontWeight', 'bold');
exportgraphics(f5, fullfile(figureDir, 'fig_q1_strategy_dashboard.png'), ...
    'Resolution', 300, 'BackgroundColor', 'w');

close([f1 f2 f3 f4 f5]);
fprintf('增强版图表已生成至 %s\n', figureDir);

%% 局部函数
function T = readChineseTable(fileName)
    opts = detectImportOptions(fileName, 'Encoding', 'UTF-8', ...
        'VariableNamingRule', 'preserve');
    T = readtable(fileName, opts);
end

function drawStrategyStory(ax, T, panelTitle, C, showLegend)
    hold(ax, 'on');
    keep = T.('日期') > 0;
    d = T.('日期')(keep);
    a = string(T.('行动')(keep));
    w = string(T.('天气')(keep));
    y = zeros(size(d));
    y(a == "行走") = 1;
    y(a == "停留") = 2;
    y(a == "挖矿") = 3;

    weatherNames = ["晴朗", "高温", "沙暴"];
    weatherCols = [C(9,:); C(4,:); C(6,:)];
    for k = 1:numel(d)
        wi = find(weatherNames == w(k), 1);
        if isempty(wi), wi = 1; end
        patch(ax, [d(k)-0.5 d(k)+0.5 d(k)+0.5 d(k)-0.5], ...
            [0.55 0.55 3.45 3.45], weatherCols(wi,:), ...
            'FaceAlpha', 0.13, 'EdgeColor', 'none');
    end

    plot(ax, d, y, '-', 'Color', [0.32 0.32 0.32], 'LineWidth', 1.25);
    actionNames = ["行走", "停留", "挖矿"];
    actionCols = C([1 3 2],:);
    actionMarks = {'o','s','d'};
    for j = 1:3
        m = a == actionNames(j);
        scatter(ax, d(m), y(m), 68, actionCols(j,:), actionMarks{j}, ...
            'filled', 'MarkerEdgeColor', 'w', 'LineWidth', 0.8);
    end

    buy = T.('购买水量')(keep) + T.('购买食物量')(keep) > 0;
    for x = reshape(d(buy), 1, [])
        xline(ax, x, ':', 'Color', C(5,:), 'LineWidth', 1.2);
    end
    scatter(ax, d(buy), 2.48*ones(sum(buy),1), 72, C(5,:), 'p', ...
        'filled', 'MarkerEdgeColor', 'w', 'LineWidth', 0.7);
    mine = a == "挖矿";
    if any(mine)
        starts = find(mine & [true; ~mine(1:end-1)]);
        ends = find(mine & [~mine(2:end); true]);
        for k = 1:numel(starts)
            xmid = mean([d(starts(k)), d(ends(k))]);
            text(ax, xmid, 3.28, sprintf('挖矿阶段 %.0f天', ...
                ends(k)-starts(k)+1), 'HorizontalAlignment', 'center', ...
                'FontSize', 10, 'Color', C(2,:));
        end
    end

    text(ax, d(end), 0.67, sprintf('到达 第%.0f天', d(end)), ...
        'HorizontalAlignment', 'right', 'FontWeight', 'bold', ...
        'FontSize', 10.5, 'Color', C(1,:));
    if showLegend
        h = gobjects(6,1);
        for j = 1:3
            h(j) = scatter(ax, nan, nan, 60, actionCols(j,:), actionMarks{j}, 'filled');
        end
        h(4) = patch(ax, nan, nan, weatherCols(1,:), 'FaceAlpha', 0.22, 'EdgeColor', 'none');
        h(5) = patch(ax, nan, nan, weatherCols(2,:), 'FaceAlpha', 0.22, 'EdgeColor', 'none');
        h(6) = patch(ax, nan, nan, weatherCols(3,:), 'FaceAlpha', 0.22, 'EdgeColor', 'none');
        h(7) = scatter(ax, nan, nan, 60, C(5,:), 'p', 'filled');
        legend(ax, h, {'行走','停留','挖矿','晴朗','高温','沙暴','补给'}, ...
            'Location', 'northoutside', 'NumColumns', 7, 'FontSize', 10);
    end
    set(ax, 'Color', 'w', 'FontSize', 10.5, 'YTick', 1:3, ...
        'YTickLabel', {'行走','停留','挖矿'}, 'XTick', 1:2:max(d), ...
        'XLim', [0.5 max(d)+0.5], 'YLim', [0.5 3.52]);
    grid(ax, 'on'); box(ax, 'on');
    set(ax, 'GridAlpha', 0.18, 'GridLineStyle', '--', 'YGrid', 'off');
    title(ax, panelTitle, 'FontSize', 12.5, 'FontWeight', 'bold');
    xlabel(ax, '日期/天', 'FontSize', 12.5);
end

function drawResourceRibbon(ax, T, panelTitle, C)
    hold(ax, 'on');
    d = T.('日期');
    waterPct = T.('剩余水量') / T.('剩余水量')(1) * 100;
    foodPct = T.('剩余食物量') / T.('剩余食物量')(1) * 100;
    loadPct = T.('总负重kg') / 1200 * 100;
    ymax = max([125; waterPct; foodPct]);

    patch(ax, [d(1) d(end) d(end) d(1)], [0 0 20 20], C(4,:), ...
        'FaceAlpha', 0.14, 'EdgeColor', 'none');
    ar = area(ax, d, loadPct, 'FaceColor', C(6,:), 'FaceAlpha', 0.32, ...
        'EdgeColor', C(1,:), 'LineWidth', 1.25);
    h1 = plot(ax, d, waterPct, '-o', 'Color', C(1,:), 'LineWidth', 2, ...
        'MarkerSize', 4, 'MarkerFaceColor', 'w');
    h2 = plot(ax, d, foodPct, '--s', 'Color', C(2,:), 'LineWidth', 2, ...
        'MarkerSize', 4, 'MarkerFaceColor', 'w');
    yline(ax, 100, ':', '初始水平', 'Color', [0.35 0.35 0.35], ...
        'LineWidth', 1, 'FontSize', 10, 'LabelHorizontalAlignment', 'left');

    buy = T.('购买水量') + T.('购买食物量') > 0 & d > 0;
    for idx = reshape(find(buy), 1, [])
        xline(ax, d(idx), ':', 'Color', C(5,:), 'LineWidth', 1.15);
        scatter(ax, d(idx), waterPct(idx), 70, C(1,:), '^', 'filled', ...
            'MarkerEdgeColor', 'k', 'LineWidth', 0.6);
        scatter(ax, d(idx), foodPct(idx), 70, C(2,:), 'v', 'filled', ...
            'MarkerEdgeColor', 'k', 'LineWidth', 0.6);
    end

    text(ax, d(1)+0.25, 8, '低余量区', 'Color', C(5,:), 'FontSize', 10);
    text(ax, d(end)-0.25, 7, '终点库存归零', 'HorizontalAlignment', 'right', ...
        'Color', C(5,:), 'FontWeight', 'bold', 'FontSize', 10);
    set(ax, 'Color', 'w', 'FontSize', 10.5, 'XLim', [d(1) d(end)], ...
        'YLim', [0 ymax+8], 'XTick', 0:2:max(d));
    grid(ax, 'on'); box(ax, 'on');
    set(ax, 'GridAlpha', 0.2, 'GridLineStyle', '--');
    title(ax, panelTitle, 'FontSize', 12.5, 'FontWeight', 'bold');
    xlabel(ax, '日期/天', 'FontSize', 12.5);
    ylabel(ax, '相对初始水平/%', 'FontSize', 12.5);
    hbuy = scatter(ax, nan, nan, 65, C(5,:), '^', 'filled', ...
        'MarkerEdgeColor', 'k', 'LineWidth', 0.6);
    legend(ax, [h1 h2 ar hbuy], {'水余量','食物余量','负重率','补给日'}, ...
        'Location', 'northeast', 'NumColumns', 4, 'FontSize', 10);
end

function drawCashWaterfall(ax, T, panelTitle, C)
    hold(ax, 'on');
    cash = T.('剩余资金数');
    days = T.('日期');
    delta = diff(cash);
    rows = find(delta ~= 0) + 1;
    changes = delta(rows-1);
    n = numel(rows);
    levels = [cash(1); cash(rows)];
    labels = strings(n+1,1);
    labels(1) = "起点余额";
    for k = 1:n
        if T.('购买水量')(rows(k)) + T.('购买食物量')(rows(k)) > 0
            labels(k+1) = sprintf('第%.0f天补给', days(rows(k)));
        else
            labels(k+1) = sprintf('第%.0f天挖矿', days(rows(k)));
        end
    end

    for k = 1:n
        low = min(levels(k), levels(k+1));
        ht = abs(changes(k));
        col = C(2,:);
        if changes(k) < 0, col = C(5,:); end
        rectangle(ax, 'Position', [k+0.64, low, 0.72, ht], ...
            'FaceColor', col, 'EdgeColor', 'w', 'LineWidth', 0.8);
        plot(ax, [k+0.36 k+0.64], [levels(k) levels(k)], '-', ...
            'Color', [0.55 0.55 0.55], 'LineWidth', 1);
        if changes(k) < 0
            text(ax, k+1, low-0.035*range(cash), sprintf('%.0f', changes(k)), ...
                'HorizontalAlignment', 'center', 'VerticalAlignment', 'top', ...
                'Color', C(5,:), 'FontSize', 10);
        end
    end
    hc = plot(ax, 1:n+1, levels, '-o', 'Color', C(1,:), 'LineWidth', 2, ...
        'MarkerSize', 4.5, 'MarkerFaceColor', 'w');
    text(ax, 0.97, 0.88, sprintf('终端财富 %.0f元', levels(end)), ...
        'Units', 'normalized', 'HorizontalAlignment', 'right', ...
        'FontWeight', 'bold', 'Color', C(1,:), 'FontSize', 10.5, ...
        'BackgroundColor', 'w', 'EdgeColor', C(6,:), 'Margin', 4);
    hp = patch(ax, nan, nan, C(2,:), 'EdgeColor', 'none');
    hn = patch(ax, nan, nan, C(5,:), 'EdgeColor', 'none');
    legend(ax, [hp hn hc], {'挖矿收入','补给支出','累计财富'}, ...
        'Location', 'northwest', 'NumColumns', 3, 'FontSize', 10);
    pad = max(350, 0.13*range(cash));
    set(ax, 'Color', 'w', 'FontSize', 10.5, 'XTick', 1:n+1, ...
        'XTickLabel', labels, 'XTickLabelRotation', 30, ...
        'XLim', [0.45 n+1.55], 'YLim', [min(levels)-pad max(levels)+pad]);
    grid(ax, 'on'); box(ax, 'on');
    set(ax, 'GridAlpha', 0.2, 'GridLineStyle', '--', 'XGrid', 'off');
    title(ax, panelTitle, 'FontSize', 12.5, 'FontWeight', 'bold');
    ylabel(ax, '财富/元', 'FontSize', 12.5);
end

function drawSensitivityLollipop(ax, TS, levelName, panelTitle, C)
    levels = string(TS.('关卡'));
    params = string(TS.('参数'));
    values = string(TS.('参数值'));
    wealth = TS.('最优终端财富');
    base = wealth(levels == levelName & params == "基准");
    mask = levels == levelName & params ~= "基准";
    delta = wealth(mask) - base;
    labels = params(mask) + "  " + values(mask);
    [~, order] = sort(abs(delta), 'descend');
    delta = delta(order);
    labels = labels(order);
    y = 1:numel(delta);
    hold(ax, 'on');
    span = max(abs(delta));
    for k = 1:numel(delta)
        col = C(1,:); mark = 'o';
        if delta(k) < 0, col = C(5,:); mark = 'd'; end
        plot(ax, [0 delta(k)], [y(k) y(k)], '-', 'Color', col, 'LineWidth', 3);
        scatter(ax, delta(k), y(k), 85, col, mark, 'filled', ...
            'MarkerEdgeColor', 'w', 'LineWidth', 0.8);
        if delta(k) >= 0
            text(ax, delta(k)+0.04*span, y(k), sprintf('+%.0f', delta(k)), ...
                'HorizontalAlignment', 'left', 'FontSize', 10);
        else
            text(ax, delta(k)-0.04*span, y(k), sprintf('%.0f', delta(k)), ...
                'HorizontalAlignment', 'right', 'FontSize', 10);
        end
    end
    xline(ax, 0, '-', '基准', 'Color', [0.3 0.3 0.3], 'LineWidth', 1.2, ...
        'FontSize', 10, 'LabelHorizontalAlignment', 'center');
    text(ax, 0.97, 0.08, sprintf('基准财富 %.0f元', base), ...
        'Units', 'normalized', 'HorizontalAlignment', 'right', ...
        'BackgroundColor', [0.97 0.97 0.97], 'EdgeColor', C(6,:), ...
        'Margin', 5, 'FontSize', 10.5);
    set(ax, 'Color', 'w', 'FontSize', 10.5, 'YTick', y, ...
        'YTickLabel', labels, 'YDir', 'reverse', ...
        'XLim', [-1.35*span 1.35*span]);
    grid(ax, 'on'); box(ax, 'on');
    set(ax, 'GridAlpha', 0.18, 'GridLineStyle', '--', 'YGrid', 'off');
    title(ax, panelTitle, 'FontSize', 12.5, 'FontWeight', 'bold');
    xlabel(ax, '相对基准财富变化/元', 'FontSize', 12.5);
end

function drawActionComposition(ax, T1, T2, C)
    actionNames = ["行走", "停留", "挖矿"];
    M = zeros(2,3);
    TT = {T1,T2};
    for i = 1:2
        a = string(TT{i}.('行动'));
        for j = 1:3, M(i,j) = sum(a == actionNames(j)); end
    end
    b = bar(ax, M, 'stacked', 'BarWidth', 0.62);
    colorOrder = [1 3 2];
    for j = 1:3, b(j).FaceColor = C(colorOrder(j),:); end
    set(ax, 'Color', 'w', 'FontSize', 10.5, 'XTickLabel', {'第一关','第二关'});
    grid(ax, 'on'); box(ax, 'on'); set(ax, 'GridAlpha', 0.2, 'GridLineStyle', '--');
    title(ax, 'a 行动天数构成', 'FontSize', 12.5, 'FontWeight', 'bold');
    ylabel(ax, '天数/天', 'FontSize', 12.5);
    legend(ax, {'行走','停留','挖矿'}, 'Location', 'northwest', ...
        'NumColumns', 3, 'FontSize', 10);
end

function drawHeadlineWealth(ax, T1, T2, C)
    vals = [T1.('剩余资金数')(end), T2.('剩余资金数')(end)];
    days = [T1.('日期')(end), T2.('日期')(end)];
    b = barh(ax, vals, 0.52, 'FaceColor', 'flat');
    b.CData = C([1 2],:);
    for i = 1:2
        text(ax, vals(i)+220, i, sprintf('%.0f元  第%.0f天到达', vals(i), days(i)), ...
            'VerticalAlignment', 'middle', 'FontSize', 10.5, 'FontWeight', 'bold');
    end
    set(ax, 'Color', 'w', 'FontSize', 10.5, 'YTick', 1:2, ...
        'YTickLabel', {'第一关','第二关'}, 'XLim', [0 max(vals)*1.28]);
    grid(ax, 'on'); box(ax, 'on'); set(ax, 'GridAlpha', 0.2, 'GridLineStyle', '--');
    title(ax, 'b 终端财富与到达日', 'FontSize', 12.5, 'FontWeight', 'bold');
    xlabel(ax, '终端财富/元', 'FontSize', 12.5);
end

function drawDecisionCounts(ax, T1, T2, C)
    TT = {T1,T2}; M = zeros(2,2);
    for i = 1:2
        d = TT{i}.('日期');
        M(i,1) = sum(TT{i}.('购买水量') + TT{i}.('购买食物量') > 0 & d > 0);
        M(i,2) = sum(string(TT{i}.('行动')) == "挖矿");
    end
    b = bar(ax, M, 'grouped', 'BarWidth', 0.72);
    b(1).FaceColor = C(3,:); b(2).FaceColor = C(2,:);
    for j = 1:2
        for i = 1:2
            text(ax, b(j).XEndPoints(i), b(j).YEndPoints(i)+0.25, ...
                sprintf('%.0f', M(i,j)), 'HorizontalAlignment', 'center', ...
                'FontSize', 10, 'FontWeight', 'bold');
        end
    end
    set(ax, 'Color', 'w', 'FontSize', 10.5, 'XTickLabel', {'第一关','第二关'});
    grid(ax, 'on'); box(ax, 'on'); set(ax, 'GridAlpha', 0.2, 'GridLineStyle', '--');
    title(ax, 'c 关键决策频次', 'FontSize', 12.5, 'FontWeight', 'bold');
    ylabel(ax, '次数/次', 'FontSize', 12.5);
    legend(ax, {'途中补给','挖矿'}, 'Location', 'northwest', ...
        'NumColumns', 2, 'FontSize', 10);
end

function drawSensitivityEnvelope(ax, TS, C)
    levels = string(TS.('关卡')); params = string(TS.('参数'));
    wealth = TS.('最优终端财富'); names = ["第一关","第二关"];
    M = zeros(2,2);
    for i = 1:2
        base = wealth(levels == names(i) & params == "基准");
        d = wealth(levels == names(i) & params ~= "基准") - base;
        M(i,:) = [min(d), max(d)];
    end
    hold(ax, 'on');
    for i = 1:2
        plot(ax, [M(i,1) M(i,2)], [i i], '-', 'Color', C(6,:), 'LineWidth', 8);
        scatter(ax, M(i,1), i, 80, C(5,:), 'd', 'filled', 'MarkerEdgeColor', 'w');
        scatter(ax, M(i,2), i, 80, C(1,:), 'o', 'filled', 'MarkerEdgeColor', 'w');
        text(ax, M(i,1)-55, i, sprintf('%.0f', M(i,1)), 'HorizontalAlignment', 'right', 'FontSize', 10);
        text(ax, M(i,2)+55, i, sprintf('+%.0f', M(i,2)), 'HorizontalAlignment', 'left', 'FontSize', 10);
    end
    xline(ax, 0, ':', '基准', 'Color', [0.3 0.3 0.3], 'LineWidth', 1.2, 'FontSize', 10);
    lim = max(abs(M), [], 'all')*1.25;
    set(ax, 'Color', 'w', 'FontSize', 10.5, 'YTick', 1:2, ...
        'YTickLabel', {'第一关','第二关'}, 'YDir', 'reverse', 'XLim', [-lim lim]);
    grid(ax, 'on'); box(ax, 'on'); set(ax, 'GridAlpha', 0.2, 'GridLineStyle', '--', 'YGrid', 'off');
    title(ax, 'd 灵敏性响应包络', 'FontSize', 12.5, 'FontWeight', 'bold');
    xlabel(ax, '财富变化/元', 'FontSize', 12.5);
end
