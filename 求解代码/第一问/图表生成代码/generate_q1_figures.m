%% 第一问 MATLAB 论文图表生成脚本
% 数据来源：求解代码/第一问/结果输出中的真实 CSV 结果
% 运行环境：MATLAB R2023b

clear; close all; clc;

%% 公共初始化
try
    set(0, 'DefaultTextFontName', 'SimHei');
    set(0, 'DefaultAxesFontName', 'SimHei');
catch
    set(0, 'DefaultTextFontName', 'Microsoft YaHei');
    set(0, 'DefaultAxesFontName', 'Microsoft YaHei');
end
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
figureDir = fullfile(projectRoot, '求解代码', '第一问', 'figures');
if ~exist(figureDir, 'dir')
    mkdir(figureDir);
end

firstFile = fullfile(dataDir, '第一关逐日策略.csv');
secondFile = fullfile(dataDir, '第二关逐日策略.csv');
sensitivityFile = fullfile(dataDir, '灵敏性分析.csv');

opts1 = detectImportOptions(firstFile, 'Encoding', 'UTF-8', 'VariableNamingRule', 'preserve');
opts2 = detectImportOptions(secondFile, 'Encoding', 'UTF-8', 'VariableNamingRule', 'preserve');
optsS = detectImportOptions(sensitivityFile, 'Encoding', 'UTF-8', 'VariableNamingRule', 'preserve');
T1 = readtable(firstFile, opts1);
T2 = readtable(secondFile, opts2);
TS = readtable(sensitivityFile, optsS);

% 数据源一致性断言，防止误用旧结果或截断文件。
assert(height(T1) == 25 && height(T2) == 31, '逐日策略记录数量与预期不一致');
assert(T1.('剩余资金数')(end) == 10470, '第一关终端财富与求解摘要不一致');
assert(T2.('剩余资金数')(end) == 12730, '第二关终端财富与求解摘要不一致');
assert(T1.('剩余水量')(end) == 0 && T1.('剩余食物量')(end) == 0, '第一关终点库存不为零');
assert(T2.('剩余水量')(end) == 0 && T2.('剩余食物量')(end) == 0, '第二关终点库存不为零');

%% 图5-1 数据读取与变量整理
% 仅使用第1天至到达日的天气和行动，不把第0天起点采购视为耗时行动。
figure1 = figure('Position', [80 80 1200 680], 'Color', 'w');
layout1 = tiledlayout(2, 1, 'TileSpacing', 'compact', 'Padding', 'compact');
drawActionTimeline(nexttile, T1, 'a 第一关行动与天气', natureColors);
drawActionTimeline(nexttile, T2, 'b 第二关行动与天气', natureColors);
title(layout1, '两关逐日行动与天气阶段', 'FontSize', 15, 'FontWeight', 'bold');
exportgraphics(figure1, fullfile(figureDir, 'fig_q1_strategy_timeline.png'), ...
    'Resolution', 300, 'BackgroundColor', 'w');

%% 图5-2 数据读取与变量整理
% 水和食物使用箱，负重率由仓库 CSV 中的真实总负重除以官方上限得到。
figure2 = figure('Position', [60 50 1200 820], 'Color', 'w');
layout2 = tiledlayout(2, 2, 'TileSpacing', 'compact', 'Padding', 'compact');
drawInventory(nexttile, T1, 'a 第一关水食库存', natureColors);
drawInventory(nexttile, T2, 'b 第二关水食库存', natureColors);
drawLoadRate(nexttile, T1, 'c 第一关负重率', natureColors);
drawLoadRate(nexttile, T2, 'd 第二关负重率', natureColors);
title(layout2, '两关资源库存与负重约束变化', 'FontSize', 15, 'FontWeight', 'bold');
exportgraphics(figure2, fullfile(figureDir, 'fig_q1_resource_dashboard.png'), ...
    'Resolution', 300, 'BackgroundColor', 'w');

%% 图5-3 数据读取与变量整理
% 资金是日末状态量，阶梯线用于突出采购扣款和挖矿增收的分段变化。
figure3 = figure('Position', [80 80 1050 620], 'Color', 'w');
hold on;
h1 = stairs(T1.('日期'), T1.('剩余资金数'), '-o', ...
    'Color', natureColors(1,:), 'LineWidth', 2, 'MarkerSize', 4, ...
    'MarkerFaceColor', natureColors(1,:));
h2 = stairs(T2.('日期'), T2.('剩余资金数'), '--s', ...
    'Color', natureColors(2,:), 'LineWidth', 2, 'MarkerSize', 4, ...
    'MarkerFaceColor', natureColors(2,:));

markPurchaseDays(T1, natureColors(5,:));
markPurchaseDays(T2, natureColors(5,:));
text(T1.('日期')(end) - 0.3, T1.('剩余资金数')(end) + 300, '10470元', ...
    'HorizontalAlignment', 'right', 'FontSize', 10.5, 'Color', natureColors(1,:));
text(T2.('日期')(end) - 0.3, T2.('剩余资金数')(end) + 300, '12730元', ...
    'HorizontalAlignment', 'right', 'FontSize', 10.5, 'Color', natureColors(2,:));
set(gca, 'Color', 'w', 'FontSize', 11, 'XTick', 0:2:30);
grid on; box on;
set(gca, 'GridAlpha', 0.3, 'GridLineStyle', '--');
title('两关逐日资金阶梯变化', 'FontSize', 15, 'FontWeight', 'bold', ...
    'HorizontalAlignment', 'center');
xlabel('日期/天', 'FontSize', 12.5);
ylabel('剩余资金/元', 'FontSize', 12.5);
legend([h1 h2], {'第一关', '第二关'}, 'Location', 'northwest', 'FontSize', 11);
xlim([0 30]);
ylim([2800 13400]);
exportgraphics(figure3, fullfile(figureDir, 'fig_q1_cash_stairs.png'), ...
    'Resolution', 300, 'BackgroundColor', 'w');

%% 图5-4 数据读取与变量整理
% 对每个扰动场景计算相对本关基准最优财富的真实差值。
figure4 = figure('Position', [70 50 1200 760], 'Color', 'w');
layout4 = tiledlayout(1, 2, 'TileSpacing', 'compact', 'Padding', 'compact');
drawSensitivity(nexttile, TS, '第一关', 'a 第一关财富变化', natureColors);
drawSensitivity(nexttile, TS, '第二关', 'b 第二关财富变化', natureColors);
title(layout4, '参数扰动下最优财富变化', 'FontSize', 15, 'FontWeight', 'bold');
exportgraphics(figure4, fullfile(figureDir, 'fig_q1_sensitivity_diverging.png'), ...
    'Resolution', 300, 'BackgroundColor', 'w');

close([figure1 figure2 figure3 figure4]);
fprintf('第一问图表已生成至 %s\n', figureDir);

%% 局部函数
function drawActionTimeline(ax, T, panelTitle, natureColors)
    hold(ax, 'on');
    days = T.('日期');
    actions = string(T.('行动'));
    weather = string(T.('天气'));
    keep = days > 0;
    days = days(keep);
    actions = actions(keep);
    weather = weather(keep);

    actionNames = ["行走", "停留", "挖矿"];
    actionColors = natureColors([1 3 2], :);
    actionChars = ["行", "停", "矿"];
    for k = 1:numel(days)
        idx = find(actionNames == actions(k), 1);
        if isempty(idx)
            idx = 1;
        end
        rectangle(ax, 'Position', [days(k)-0.47, 0.78, 0.94, 0.42], ...
            'FaceColor', actionColors(idx,:), 'EdgeColor', 'w', 'LineWidth', 0.5);
        text(ax, days(k), 0.99, actionChars(idx), 'HorizontalAlignment', 'center', ...
            'FontSize', 10, 'Color', 'k');
    end

    weatherNames = ["晴朗", "高温", "沙暴"];
    markers = {'o', '^', 's'};
    for j = 1:numel(weatherNames)
        mask = weather == weatherNames(j);
        plot(ax, days(mask), 1.47 * ones(sum(mask), 1), markers{j}, ...
            'Color', [0.25 0.25 0.25], 'MarkerSize', 6, 'LineWidth', 1.2, ...
            'MarkerFaceColor', 'w', 'LineStyle', 'none');
    end

    p1 = patch(ax, nan, nan, actionColors(1,:), 'EdgeColor', 'none');
    p2 = patch(ax, nan, nan, actionColors(2,:), 'EdgeColor', 'none');
    p3 = patch(ax, nan, nan, actionColors(3,:), 'EdgeColor', 'none');
    w1 = plot(ax, nan, nan, 'ko', 'MarkerFaceColor', 'w', 'LineWidth', 1.2);
    w2 = plot(ax, nan, nan, 'k^', 'MarkerFaceColor', 'w', 'LineWidth', 1.2);
    w3 = plot(ax, nan, nan, 'ks', 'MarkerFaceColor', 'w', 'LineWidth', 1.2);
    legend(ax, [p1 p2 p3 w1 w2 w3], ...
        {'行走', '停留', '挖矿', '晴朗', '高温', '沙暴'}, ...
        'Location', 'northoutside', 'NumColumns', 6, 'FontSize', 10);
    set(ax, 'Color', 'w', 'FontSize', 11, 'YTick', [], ...
        'XTick', 1:2:max(days), 'XLim', [0.5 max(days)+0.5], 'YLim', [0.68 1.66]);
    grid(ax, 'on'); box(ax, 'on');
    set(ax, 'GridAlpha', 0.22, 'GridLineStyle', '--', 'YGrid', 'off');
    title(ax, panelTitle, 'FontSize', 12.5, 'FontWeight', 'bold', ...
        'HorizontalAlignment', 'center');
    xlabel(ax, '日期/天', 'FontSize', 12.5);
end

function drawInventory(ax, T, panelTitle, natureColors)
    hold(ax, 'on');
    days = T.('日期');
    water = T.('剩余水量');
    food = T.('剩余食物量');
    h1 = plot(ax, days, water, '-o', 'Color', natureColors(1,:), ...
        'LineWidth', 1.8, 'MarkerSize', 4, 'MarkerFaceColor', natureColors(1,:));
    h2 = plot(ax, days, food, '--s', 'Color', natureColors(2,:), ...
        'LineWidth', 1.8, 'MarkerSize', 4, 'MarkerFaceColor', natureColors(2,:));
    buyW = T.('购买水量') > 0 & days > 0;
    buyF = T.('购买食物量') > 0 & days > 0;
    scatter(ax, days(buyW)-0.12, water(buyW), 55, natureColors(1,:), '^', 'filled', ...
        'MarkerEdgeColor', 'k', 'LineWidth', 0.7);
    scatter(ax, days(buyF)+0.12, food(buyF), 55, natureColors(2,:), 'v', 'filled', ...
        'MarkerEdgeColor', 'k', 'LineWidth', 0.7);
    set(ax, 'Color', 'w', 'FontSize', 10.5, 'XTick', 0:4:max(days));
    grid(ax, 'on'); box(ax, 'on');
    set(ax, 'GridAlpha', 0.3, 'GridLineStyle', '--');
    title(ax, panelTitle, 'FontSize', 12.5, 'FontWeight', 'bold', ...
        'HorizontalAlignment', 'center');
    xlabel(ax, '日期/天', 'FontSize', 12.5);
    ylabel(ax, '剩余资源/箱', 'FontSize', 12.5);
    legend(ax, [h1 h2], {'水', '食物'}, 'Location', 'northeast', 'FontSize', 10);
end

function drawLoadRate(ax, T, panelTitle, natureColors)
    days = T.('日期');
    rate = T.('总负重kg') / 1200 * 100;
    area(ax, days, rate, 'FaceColor', natureColors(6,:), ...
        'FaceAlpha', 0.55, 'EdgeColor', natureColors(1,:), 'LineWidth', 1.7);
    hold(ax, 'on');
    yline(ax, 100, '--', '负重上限', 'Color', natureColors(5,:), ...
        'LineWidth', 1.3, 'FontSize', 10, 'LabelHorizontalAlignment', 'left');
    set(ax, 'Color', 'w', 'FontSize', 10.5, 'XTick', 0:4:max(days), ...
        'YLim', [0 106]);
    grid(ax, 'on'); box(ax, 'on');
    set(ax, 'GridAlpha', 0.3, 'GridLineStyle', '--');
    title(ax, panelTitle, 'FontSize', 12.5, 'FontWeight', 'bold', ...
        'HorizontalAlignment', 'center');
    xlabel(ax, '日期/天', 'FontSize', 12.5);
    ylabel(ax, '负重率/%', 'FontSize', 12.5);
end

function markPurchaseDays(T, color)
    mask = T.('购买水量') + T.('购买食物量') > 0 & T.('日期') > 0;
    scatter(T.('日期')(mask), T.('剩余资金数')(mask), 48, color, 'd', 'filled', ...
        'MarkerEdgeColor', 'k', 'LineWidth', 0.6);
end

function drawSensitivity(ax, TS, levelName, panelTitle, natureColors)
    levels = string(TS.('关卡'));
    params = string(TS.('参数'));
    values = string(TS.('参数值'));
    wealth = TS.('最优终端财富');
    baseMask = levels == levelName & params == "基准";
    baseWealth = wealth(baseMask);
    mask = levels == levelName & params ~= "基准";
    labels = params(mask) + " " + values(mask);
    delta = wealth(mask) - baseWealth;
    y = 1:numel(delta);

    b = barh(ax, y, delta, 0.68, 'FaceColor', 'flat');
    colors = zeros(numel(delta), 3);
    for k = 1:numel(delta)
        if delta(k) >= 0
            colors(k,:) = natureColors(1,:);
        else
            colors(k,:) = natureColors(5,:);
        end
    end
    b.CData = colors;
    hold(ax, 'on');
    xline(ax, 0, '-', 'Color', [0.25 0.25 0.25], 'LineWidth', 1.2);
    span = max(abs(delta));
    if span == 0
        span = 1;
    end
    for k = 1:numel(delta)
        if delta(k) >= 0
            text(ax, delta(k) + 0.035*span, y(k), sprintf('+%.0f', delta(k)), ...
                'HorizontalAlignment', 'left', 'FontSize', 10);
        else
            text(ax, delta(k) - 0.035*span, y(k), sprintf('%.0f', delta(k)), ...
                'HorizontalAlignment', 'right', 'FontSize', 10);
        end
    end
    set(ax, 'Color', 'w', 'FontSize', 10.5, 'YTick', y, ...
        'YTickLabel', labels, 'YDir', 'reverse', 'XLim', [-1.28*span 1.28*span]);
    grid(ax, 'on'); box(ax, 'on');
    set(ax, 'GridAlpha', 0.3, 'GridLineStyle', '--', 'YGrid', 'off');
    title(ax, panelTitle, 'FontSize', 12.5, 'FontWeight', 'bold', ...
        'HorizontalAlignment', 'center');
    xlabel(ax, '相对基准财富变化/元', 'FontSize', 12.5);
end
