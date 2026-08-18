%% 第三问MATLAB论文图表

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

scriptDir = 'E:/数模练习册/2020题/B/Q3代码附件/图表代码/Q3_1';
chartCodeDir = fileparts(scriptDir);
q3Dir = fileparts(chartCodeDir);
dataDir = fullfile(q3Dir, '结果输出');
figureDir = fullfile(scriptDir, '图表');
if ~exist(figureDir, 'dir'), mkdir(figureDir); end

T31 = readtable(fullfile(dataDir, '第五关', '第五关玩家逐日策略.csv'), ...
    'Encoding', 'UTF-8', 'VariableNamingRule', 'preserve');

assert(size(T31, 1) > 0, '第五关玩家逐日策略数据为空');

%% 图3-1 第五关双玩家资源演化
T = sortrows(T31, {'玩家', '日期'});
players = unique(T.('玩家'), 'stable');
C = natureColors;
fig = figure('Position', [80 60 1200 700], 'Color', 'w');

for k = 1:numel(players)
    D = T(T.('玩家') == players(k), :);
    ax = subplot(numel(players), 1, k); hold(ax, 'on');
    x = D.('日期');
    water = D.('剩余水');
    food  = D.('剩余食物');
    cashDelta = D.('剩余现金') - D.('剩余现金')(1);
    yMax = max([water; food; 1]) * 1.35;

    for i = 1:numel(x)
        bg = weatherColor(D.('天气')(i));
        patch(ax, [x(i)-0.48 x(i)+0.48 x(i)+0.48 x(i)-0.48], ...
            [0 0 yMax yMax], bg, ...
            'FaceAlpha', 0.35, 'EdgeColor', 'none');
    end

    area(ax, x, water, 'FaceColor', C(6, :), 'FaceAlpha', 0.22, 'EdgeColor', 'none');
    area(ax, x, food, 'FaceColor', C(2, :), 'FaceAlpha', 0.18, 'EdgeColor', 'none');
    p1 = plot(ax, x, water, '-o', 'Color', C(1, :), 'MarkerFaceColor', C(1, :), 'MarkerSize', 7);
    p2 = plot(ax, x, food, '-s', 'Color', C(2, :), 'MarkerFaceColor', C(2, :), 'MarkerSize', 7);

    for i = 1:numel(x)
        mk = actionMarker(D.('行动')(i));
        scatter(ax, x(i), min(max(water(i), food(i)) + 0.10*yMax, 0.92*yMax), 72, ...
            'Marker', mk, 'MarkerFaceColor', C(5, :), 'MarkerEdgeColor', [0.25 0.25 0.25], 'LineWidth', 0.8);
        text(ax, x(i), 0.97*yMax, char(string(D.('天气')(i))), ...
            'HorizontalAlignment', 'center', 'VerticalAlignment', 'top', 'FontSize', 10, 'Color', [0.35 0.35 0.35]);
    end

    yyaxis(ax, 'right');
    p3 = plot(ax, x, cashDelta, '-d', 'Color', C(3, :), 'MarkerFaceColor', C(3, :), 'MarkerSize', 6);
    ylabel(ax, '现金变化量');
    ax.YAxis(2).Color = C(3, :);
    if all(abs(cashDelta) < 1e-9)
        ylim(ax, [-1 1]);
    end

    yyaxis(ax, 'left');
    ylabel(ax, '水 / 食物');
    xlabel(ax, '日期');
    ylim(ax, [0 yMax]);
    ax.YAxis(1).Color = [0.2 0.2 0.2];
    title(ax, sprintf('玩家%d 逐日资源轨迹', players(k)), 'FontWeight', 'bold');
    legend([p1, p2, p3], {'剩余水', '剩余食物', '现金变化量'}, 'Location', 'northwest');
end

sgtitle('图3-1 第五关双玩家资源演化', 'FontSize', 18, 'FontWeight', 'bold');

outputFile = fullfile(figureDir, 'q3_1_resource_evolution.png');
exportgraphics(fig, outputFile, 'Resolution', 600, 'BackgroundColor', 'white');

fprintf('第三问图表已生成至 %s\n', figureDir);

function mk = actionMarker(actionName)
actionName = char(string(actionName));
if contains(actionName, '挖矿')
    mk = 'p';
elseif contains(actionName, '停留')
    mk = 's';
elseif contains(actionName, '购买')
    mk = '^';
else
    mk = 'o';
end
end

function c = weatherColor(name)
name = char(string(name));
if contains(name, '高温')
    c = [243 222 191] / 255;
elseif contains(name, '沙暴')
    c = [224 206 173] / 255;
elseif contains(name, '晴')
    c = [220 234 244] / 255;
else
    c = [235 235 235] / 255;
end
end
