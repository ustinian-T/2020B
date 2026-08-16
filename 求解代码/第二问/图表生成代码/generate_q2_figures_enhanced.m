%% 第二问增强版图表生成脚本
% 严格读取仓库中已有结果，不重新求解，不改写任何模型输出。

clear; close all; clc;

%% 数据读取
scriptPath = mfilename('fullpath');
if isempty(scriptPath)
    scriptPath = which('generate_q2_figures_enhanced');
end
q2Root = fileparts(fileparts(scriptPath));
resultDir = fullfile(q2Root, '结果输出');
figureDir = fullfile(q2Root, 'figures_enhanced');
if ~exist(figureDir, 'dir')
    mkdir(figureDir);
end

scenario = readtable(fullfile(resultDir, '第三关1024全情景检验.csv'), ...
    'VariableNamingRule', 'preserve', 'TextType', 'string');
policy = readtable(fullfile(resultDir, '第三关在线策略树.csv'), ...
    'VariableNamingRule', 'preserve', 'TextType', 'string');
gammaData = readtable(fullfile(resultDir, '第四关Gamma安全下界.csv'), ...
    'VariableNamingRule', 'preserve', 'TextType', 'string');
gammaSens = readtable(fullfile(resultDir, '第四关Gamma灵敏性分析.csv'), ...
    'VariableNamingRule', 'preserve', 'TextType', 'string');
stormSens = readtable(fullfile(resultDir, '第四关沙暴概率灵敏性分析.csv'), ...
    'VariableNamingRule', 'preserve', 'TextType', 'string');
mcMetrics = readtable(fullfile(resultDir, '第四关蒙特卡洛指标对比.csv'), ...
    'VariableNamingRule', 'preserve', 'TextType', 'string');
mcDetail = readtable(fullfile(resultDir, '第四关蒙特卡洛逐情景结果.csv'), ...
    'VariableNamingRule', 'preserve', 'TextType', 'string');
weatherMat = readtable(fullfile(resultDir, '第四关天气转移矩阵.csv'), ...
    'VariableNamingRule', 'preserve', 'TextType', 'string');

%% 变量整理
weatherSequence = string(scenario.("天气序列"));
onlineWealth = double(scenario.("在线终端财富"));
oracleWealth = double(scenario.("Oracle终端财富"));
regret = double(scenario.("Regret"));
firstThreeHistory = extractBetween(weatherSequence, 1, 3);
firstThreeHot = count(firstThreeHistory, "H");

gammaValue = double(gammaData.("Gamma"));
latestArrival = double(gammaData.("最迟保证到达日"));
initialWater = double(gammaData.("初购水"));
initialFood = double(gammaData.("初购食物"));
cashAfterPurchase = double(gammaData.("初购后现金"));
guaranteedWealth = double(gammaData.("保证财富下界"));

gammaAll = double(gammaSens.("Gamma"));
gammaSuccess = 100 * double(gammaSens.("成功率"));
gammaMean = double(gammaSens.("成功样本平均财富"));
gammaQ05 = double(gammaSens.("5%分位财富"));
gammaWater = double(gammaSens.("初购水"));
gammaFood = double(gammaSens.("初购食物"));
gammaCash = double(gammaSens.("初购后现金"));

stormFactor = double(stormSens.("沙暴概率倍率"));
stormSuccess = 100 * double(stormSens.("成功率"));
stormMean = double(stormSens.("成功样本平均财富"));
stormQ05 = double(stormSens.("5%分位财富"));
stormArrival = double(stormSens.("平均到达日"));

strategyKey = ["第二问鲁棒决策模型(Gamma=6)", "低保护简单方案(Gamma=2)", ...
    "第一问已知天气固定方案"];
strategyLabel = ["鲁棒策略 Γ6", "低保护策略 Γ2", "固定天气方案"];
strategyColor = [82 132 173; 78 151 146; 211 154 65] / 255;
metricStrategy = string(mcMetrics.("strategy"));
metricOrder = zeros(1, 3);
for k = 1:3
    metricOrder(k) = find(metricStrategy == strategyKey(k), 1);
end
metricSuccess = double(mcMetrics.("success_rate"));
metricMean = double(mcMetrics.("mean_wealth"));
metricQ05 = double(mcMetrics.("q05_wealth"));
metricMeanRegret = double(mcMetrics.("mean_regret"));
metricMaxRegret = double(mcMetrics.("maximum_regret"));
metricSuccessCount = double(mcMetrics.("success_count"));
mcSuccess = 100 * metricSuccess(metricOrder);
mcMean = metricMean(metricOrder);
mcQ05 = metricQ05(metricOrder);
mcMeanRegret = metricMeanRegret(metricOrder);
mcMaxRegret = metricMaxRegret(metricOrder);
mcSuccessCount = metricSuccessCount(metricOrder);

detailStrategy = string(mcDetail.("strategy"));
detailSuccess = lower(string(mcDetail.("success"))) == "true";
detailWealth = str2double(string(mcDetail.("final_wealth")));
detailRegret = str2double(string(mcDetail.("regret")));
wealthGroups = cell(3, 1);
regretGroups = cell(3, 1);
for k = 1:3
    mask = detailStrategy == strategyKey(k) & detailSuccess;
    wealthGroups{k} = detailWealth(mask);
    regretGroups{k} = detailRegret(mask);
end

%% 统一样式
fontChinese = 'Microsoft YaHei';
fontLatin = 'Times New Roman';
navy = [47, 76, 107] / 255;
blue = [82, 132, 173] / 255;
teal = [78, 151, 146] / 255;
gold = [211, 154, 65] / 255;
rose = [187, 101, 91] / 255;
purple = [120, 91, 164] / 255;
lightGray = [0.89, 0.90, 0.91];
gridColor = [0.84, 0.86, 0.88];
ink = [0.17, 0.18, 0.20];

set(groot, 'defaultFigureColor', 'w');
set(groot, 'defaultAxesColor', 'w');
set(groot, 'defaultAxesFontName', fontChinese);
set(groot, 'defaultAxesFontSize', 11);
set(groot, 'defaultTextFontName', fontChinese);

%% 图一 简洁决策树与叶节点结果矩阵
leafOrder = ["SSS", "SSH", "SHS", "SHH", "HSS", "HSH", "HHS", "HHH"];
leafOnline = zeros(1, 8);
leafOracle = zeros(1, 8);
leafRegret = zeros(1, 8);
for k = 1:8
    mask = firstThreeHistory == leafOrder(k);
    leafOnline(k) = mean(onlineWealth(mask));
    leafOracle(k) = mean(oracleWealth(mask));
    leafRegret(k) = mean(regret(mask));
end

fig = figure('Position', [60, 50, 1580, 920], 'Color', 'w');
axTree = axes(fig, 'Position', [0.07, 0.38, 0.86, 0.52]);
hold(axTree, 'on');
xLevel = [0, 1, 2, 3];
yLevel = {0, [-2, 2], [-3, -1, 1, 3], -3.5:1:3.5};
historyByLevel = {{""}, {"S", "H"}, ...
    {"SS", "SH", "HS", "HH"}, cellstr(leafOrder)};

for level = 1:3
    histories = string(historyByLevel{level + 1});
    for k = 1:numel(histories)
        history = histories(k);
        parent = extractBefore(history, strlength(history));
        if level == 1
            parentY = 0;
        else
            parentHistories = string(historyByLevel{level});
            parentY = yLevel{level}(find(parentHistories == parent, 1));
        end
        branchCode = extractAfter(history, strlength(history) - 1);
        if branchCode == "S"
            branchColor = teal;
            branchStyle = '-';
            branchLabel = '晴朗';
        else
            branchColor = rose;
            branchStyle = '--';
            branchLabel = '高温';
        end
        currentY = yLevel{level + 1}(k);
        plot(axTree, [xLevel(level), xLevel(level + 1)], [parentY, currentY], ...
            'Color', branchColor, 'LineStyle', branchStyle, 'LineWidth', 1.7, ...
            'HandleVisibility', 'off');
        text(axTree, xLevel(level) + 0.50, 0.5 * (parentY + currentY) + 0.12, ...
            branchLabel, 'HorizontalAlignment', 'center', 'FontSize', 9.5, ...
            'Color', branchColor, 'BackgroundColor', 'w', 'Margin', 1);
    end
end

scatter(axTree, 0, 0, 250, gold, 'filled', 'MarkerEdgeColor', 'w', 'LineWidth', 1.2);
text(axTree, 0, 0.48, '统一采购', 'HorizontalAlignment', 'center', ...
    'FontWeight', 'bold', 'FontSize', 11, 'Color', navy);
text(axTree, 0, -0.58, '水食各54箱  现金9190元', 'HorizontalAlignment', 'center', ...
    'FontSize', 9.5, 'Color', ink);

for level = 1:2
    histories = string(historyByLevel{level + 1});
    for k = 1:numel(histories)
        history = histories(k);
        row = policy(policy.("天气历史") == history, :);
        target = row.("目标节点")(1);
        scatter(axTree, level, yLevel{level + 1}(k), 170, 'w', 'filled', ...
            'MarkerEdgeColor', blue, 'LineWidth', 1.7);
        text(axTree, level, yLevel{level + 1}(k) + 0.33, history, ...
            'HorizontalAlignment', 'center', 'FontName', fontLatin, ...
            'FontSize', 10.5, 'FontWeight', 'bold', 'Color', navy);
        text(axTree, level, yLevel{level + 1}(k) - 0.34, ...
            sprintf('走向节点 %.0f', target), 'HorizontalAlignment', 'center', ...
            'FontSize', 9.2, 'Color', ink);
    end
end

wealthMin = min(leafOnline);
wealthMax = max(leafOnline);
for k = 1:8
    tone = (leafOnline(k) - wealthMin) / max(wealthMax - wealthMin, 1);
    fillColor = (1 - tone) * [0.91, 0.94, 0.96] + tone * navy;
    rectangle(axTree, 'Position', [2.91, yLevel{4}(k) - 0.18, 0.18, 0.36], ...
        'Curvature', 0.18, 'FaceColor', fillColor, 'EdgeColor', 'w', 'LineWidth', 0.8);
    text(axTree, 3, yLevel{4}(k) + 0.34, leafOrder(k), ...
        'HorizontalAlignment', 'center', 'FontName', fontLatin, ...
        'FontWeight', 'bold', 'FontSize', 10, 'Color', navy);
end

for level = 0:3
    labels = {'初始采购', '第1天决策', '第2天决策', '第3天到达'};
    text(axTree, level, 4.14, labels{level + 1}, ...
        'HorizontalAlignment', 'center', 'FontWeight', 'bold', ...
        'FontSize', 11.5, 'Color', navy);
end
axis(axTree, 'off');
xlim(axTree, [-0.30, 3.28]);
ylim(axTree, [-4.2, 4.45]);
title(axTree, '第三关前三日非前视策略与叶节点结果', ...
    'FontSize', 16, 'FontWeight', 'bold', 'Color', navy);

axHeat = axes(fig, 'Position', [0.155, 0.10, 0.73, 0.21]);
matrixValue = [leafOnline; leafOracle; leafRegret];
matrixScaled = zeros(size(matrixValue));
for row = 1:3
    values = matrixValue(row, :);
    matrixScaled(row, :) = (values - min(values)) / max(max(values) - min(values), 1);
end
imagesc(axHeat, 1:8, 1:3, matrixScaled);
colormap(axHeat, natureMap([0.94, 0.96, 0.97], navy, 128));
axHeat.XTick = 1:8;
axHeat.XTickLabel = leafOrder;
axHeat.YTick = 1:3;
axHeat.YTickLabel = {'在线财富/元', '完全信息财富均值/元', '后悔值均值/元'};
axHeat.TickLength = [0, 0];
axHeat.Box = 'off';
xlabel(axHeat, '前三日天气历史  每个叶节点含128个完整情景', 'FontSize', 11.5);
for row = 1:3
    for column = 1:8
        if matrixScaled(row, column) > 0.58
            textColor = [1, 1, 1];
        else
            textColor = ink;
        end
        if row == 2 || row == 3
            label = sprintf('%.2f', matrixValue(row, column));
        else
            label = sprintf('%.0f', matrixValue(row, column));
        end
        text(axHeat, column, row, label, 'HorizontalAlignment', 'center', ...
            'FontName', fontLatin, 'FontSize', 9.5, 'FontWeight', 'bold', ...
            'Color', textColor);
    end
end
exportgraphics(fig, fullfile(figureDir, 'fig_q2_policy_tree.png'), ...
    'Resolution', 300, 'BackgroundColor', 'white');
close(fig);

%% 图二 1024情景排序差距带
[sortedRegret, sortIndex] = sort(regret, 'ascend');
sortedOnline = onlineWealth(sortIndex);
sortedOracle = oracleWealth(sortIndex);
scenarioRank = (1:numel(sortedRegret))';
[stepX, stepOnline] = stairs(scenarioRank, sortedOnline);
[~, stepOracle] = stairs(scenarioRank, sortedOracle);
[regretLevel, ~, regretGroup] = unique(sortedRegret, 'stable');
regretCount = accumarray(regretGroup, 1);
regretEnd = cumsum(regretCount);
regretStart = [1; regretEnd(1:end-1) + 1];
gapPalette = natureMap([0.61, 0.78, 0.87], [0.76, 0.34, 0.30], numel(regretLevel));

fig = figure('Position', [70, 80, 1380, 820], 'Color', 'w');
layout = tiledlayout(fig, 5, 1, 'TileSpacing', 'compact', 'Padding', 'compact');
ax = nexttile(layout, [4, 1]);
hold(ax, 'on');
ax.Color = [0.988, 0.989, 0.990];
for k = 1:numel(regretLevel)
    segmentIndex = regretStart(k):regretEnd(k);
    [segmentX, segmentOnline] = stairs(scenarioRank(segmentIndex), sortedOnline(segmentIndex));
    [~, segmentOracle] = stairs(scenarioRank(segmentIndex), sortedOracle(segmentIndex));
    patch(ax, [segmentX; flipud(segmentX)], ...
        [segmentOnline; flipud(segmentOracle)], gapPalette(k, :), ...
        'FaceAlpha', 0.30, 'EdgeColor', 'none', 'HandleVisibility', 'off');
end
onlineGlow = 0.72 * blue + 0.28;
oracleGlow = 0.72 * teal + 0.28;
stairs(ax, scenarioRank, sortedOnline, '-', 'Color', onlineGlow, ...
    'LineWidth', 5.4, 'HandleVisibility', 'off');
stairs(ax, scenarioRank, sortedOracle, '-', 'Color', oracleGlow, ...
    'LineWidth', 5.4, 'HandleVisibility', 'off');
hOnline = stairs(ax, scenarioRank, sortedOnline, '-', 'Color', blue, 'LineWidth', 2.2);
hOracle = stairs(ax, scenarioRank, sortedOracle, '-', 'Color', teal, 'LineWidth', 2.2);

for k = 1:numel(regretLevel)
    boundary = regretEnd(k) + 0.5;
    if k < numel(regretLevel)
        xline(ax, boundary, ':', 'Color', [0.82, 0.83, 0.84], ...
            'LineWidth', 0.8, 'HandleVisibility', 'off');
    end
    centerX = round((regretStart(k) + regretEnd(k)) / 2);
    scatter(ax, centerX, sortedOnline(centerX), 34, blue, 'filled', ...
        'MarkerEdgeColor', 'w', 'LineWidth', 0.8, 'HandleVisibility', 'off');
    scatter(ax, centerX, sortedOracle(centerX), 34, teal, 'filled', ...
        'MarkerEdgeColor', 'w', 'LineWidth', 0.8, 'HandleVisibility', 'off');
end

xlim(ax, [1, numel(sortedRegret)]);
ylim(ax, [9150, 9710]);
ylabel(ax, '终端财富/元', 'FontSize', 12.5);
grid(ax, 'on');
ax.XGrid = 'off';
ax.GridColor = gridColor;
ax.GridAlpha = 0.48;
ax.Box = 'off';
ax.TickDir = 'out';
ax.XTickLabel = [];
legend(ax, [hOnline, hOracle], {'在线策略', '完全信息策略'}, ...
    'Location', 'northwest', 'Orientation', 'horizontal', ...
    'Box', 'off', 'FontSize', 10.5);
meanRegret = mean(regret);
zeroShare = mean(regret == 0) * 100;
text(ax, 1000, 9685, sprintf('平均后悔值 %.2f 元', meanRegret), ...
    'HorizontalAlignment', 'right', 'FontSize', 10.5, ...
    'FontWeight', 'bold', 'Color', rose);
text(ax, 1000, 9645, sprintf('零后悔情景占比 %.2f%%', zeroShare), ...
    'HorizontalAlignment', 'right', 'FontSize', 10.0, 'Color', ink);

axStrip = nexttile(layout, 5);
imagesc(axStrip, scenarioRank', 1, sortedRegret');
colormap(axStrip, natureMap([0.84, 0.91, 0.94], rose, 256));
axStrip.YTick = [];
axStrip.Box = 'off';
axStrip.TickDir = 'out';
axStrip.XTick = [1, 256, 512, 768, 1024];
xlabel(axStrip, '情景序位  按后悔值从低到高排列', 'FontSize', 11.5);
hold(axStrip, 'on');
for k = 1:numel(regretLevel)
    centerX = (regretStart(k) + regretEnd(k)) / 2;
    if regretCount(k) >= 64
        text(axStrip, centerX, 1, sprintf('%.0f', regretLevel(k)), ...
            'HorizontalAlignment', 'center', 'VerticalAlignment', 'middle', ...
            'FontSize', 8.5, 'FontWeight', 'bold', 'Color', 'w');
    end
end
cb = colorbar(axStrip, 'eastoutside');
cb.Label.String = '后悔值/元';
cb.FontSize = 9.5;
title(layout, '第三关1024个情景下两类策略的财富差距', ...
    'FontSize', 16, 'FontWeight', 'bold', 'Color', navy);
exportgraphics(fig, fullfile(figureDir, 'fig_q2_scenario_heatmap.png'), ...
    'Resolution', 300, 'BackgroundColor', 'white');
close(fig);

%% 图三 财富层级到后悔值层级的情景流带图
[pairValue, ~, pairGroup] = unique([onlineWealth, regret], 'rows', 'sorted');
pairCount = accumarray(pairGroup, 1);
onlineLevel = unique(pairValue(:, 1), 'sorted');
regretLevel = unique(pairValue(:, 2), 'sorted');
onlineCount = zeros(numel(onlineLevel), 1);
regretCount = zeros(numel(regretLevel), 1);
for k = 1:numel(onlineLevel)
    onlineCount(k) = sum(pairCount(pairValue(:, 1) == onlineLevel(k)));
end
for k = 1:numel(regretLevel)
    regretCount(k) = sum(pairCount(pairValue(:, 2) == regretLevel(k)));
end

flowPalette = [blue; teal; gold; rose];
totalCount = numel(onlineWealth);
flowScale = 0.72 / totalCount;
leftGap = 0.035;
rightGap = 0.014;
leftBottom = zeros(numel(onlineLevel), 1);
rightBottom = zeros(numel(regretLevel), 1);
leftBottom(1) = 0.10;
rightBottom(1) = 0.075;
for k = 2:numel(onlineLevel)
    leftBottom(k) = leftBottom(k - 1) + onlineCount(k - 1) * flowScale + leftGap;
end
for k = 2:numel(regretLevel)
    rightBottom(k) = rightBottom(k - 1) + regretCount(k - 1) * flowScale + rightGap;
end
leftOffset = zeros(numel(onlineLevel), 1);
rightOffset = zeros(numel(regretLevel), 1);

fig = figure('Position', [90, 70, 1320, 820], 'Color', 'w');
ax = axes(fig, 'Position', [0.13, 0.11, 0.74, 0.76]);
hold(ax, 'on');
rectangle(ax, 'Position', [0.052, 0.052, 0.90, 0.88], ...
    'Curvature', [0.035, 0.035], 'FaceColor', [0.91, 0.92, 0.93], ...
    'EdgeColor', 'none');
rectangle(ax, 'Position', [0.045, 0.060, 0.90, 0.88], ...
    'Curvature', [0.035, 0.035], 'FaceColor', [0.988, 0.986, 0.981], ...
    'EdgeColor', [0.90, 0.88, 0.84], 'LineWidth', 0.8);
for k = 1:size(pairValue, 1)
    leftIndex = find(onlineLevel == pairValue(k, 1), 1);
    rightIndex = find(regretLevel == pairValue(k, 2), 1);
    bandHeight = pairCount(k) * flowScale;
    yLeft0 = leftBottom(leftIndex) + leftOffset(leftIndex);
    yLeft1 = yLeft0 + bandHeight;
    yRight0 = rightBottom(rightIndex) + rightOffset(rightIndex);
    yRight1 = yRight0 + bandHeight;
    drawFlowBand(ax, 0.18, 0.82, yLeft0, yLeft1, yRight0, yRight1, ...
        flowPalette(leftIndex, :), 0.46);
    leftOffset(leftIndex) = leftOffset(leftIndex) + bandHeight;
    rightOffset(rightIndex) = rightOffset(rightIndex) + bandHeight;
    if pairCount(k) >= 64
        text(ax, 0.50, mean([yLeft0, yLeft1, yRight0, yRight1]), ...
            sprintf('%d个情景', pairCount(k)), 'HorizontalAlignment', 'center', ...
            'FontSize', 9.0, 'FontWeight', 'bold', 'Color', navy);
    end
end

for k = 1:numel(onlineLevel)
    nodeY = leftBottom(k);
    nodeH = onlineCount(k) * flowScale;
    rectangle(ax, 'Position', [0.146, nodeY - 0.004, 0.043, nodeH], ...
        'FaceColor', [0.82, 0.83, 0.84], ...
        'EdgeColor', 'none');
    rectangle(ax, 'Position', [0.14, nodeY, 0.04, nodeH], ...
        'FaceColor', flowPalette(k, :), 'EdgeColor', 'w', 'LineWidth', 1.0);
    highlightColor = 0.60 * flowPalette(k, :) + 0.40;
    rectangle(ax, 'Position', [0.144, nodeY + 0.04 * nodeH, 0.006, 0.92 * nodeH], ...
        'FaceColor', highlightColor, 'EdgeColor', 'none');
    text(ax, 0.125, nodeY + nodeH / 2, ...
        sprintf('%.0f元  %d个', onlineLevel(k), onlineCount(k)), ...
        'HorizontalAlignment', 'right', 'VerticalAlignment', 'middle', ...
        'FontSize', 10.2, 'FontWeight', 'bold', 'Color', flowPalette(k, :));
end
for k = 1:numel(regretLevel)
    nodeY = rightBottom(k);
    nodeH = regretCount(k) * flowScale;
    leftIndex = find(onlineLevel == pairValue(find(pairValue(:, 2) == regretLevel(k), 1), 1), 1);
    rectangle(ax, 'Position', [0.826, nodeY - 0.003, 0.043, nodeH], ...
        'FaceColor', [0.82, 0.83, 0.84], ...
        'EdgeColor', 'none');
    rectangle(ax, 'Position', [0.82, nodeY, 0.04, nodeH], ...
        'FaceColor', flowPalette(leftIndex, :), 'EdgeColor', 'w', 'LineWidth', 0.9);
    highlightColor = 0.60 * flowPalette(leftIndex, :) + 0.40;
    rectangle(ax, 'Position', [0.824, nodeY + 0.05 * nodeH, 0.006, 0.90 * nodeH], ...
        'FaceColor', highlightColor, 'EdgeColor', 'none');
    text(ax, 0.875, nodeY + nodeH / 2, ...
        sprintf('%.0f元  %d个', regretLevel(k), regretCount(k)), ...
        'HorizontalAlignment', 'left', 'VerticalAlignment', 'middle', ...
        'FontSize', 9.5, 'Color', ink);
end

xlim(ax, [0, 1]);
ylim(ax, [0, 1]);
axis(ax, 'off');
text(ax, 0.16, 0.97, '在线终端财富', 'HorizontalAlignment', 'center', ...
    'FontSize', 12.5, 'FontWeight', 'bold', 'Color', navy);
text(ax, 0.84, 0.97, '后悔值', 'HorizontalAlignment', 'center', ...
    'FontSize', 12.5, 'FontWeight', 'bold', 'Color', navy);
title(ax, '第三关1024个情景的财富与后悔值流向', ...
    'FontSize', 16, 'FontWeight', 'bold', 'Color', navy);
text(ax, 0.50, 0.015, '每个情景仅计入一条流带  图中频数合计为1024', ...
    'HorizontalAlignment', 'center', 'FontSize', 9.5, ...
    'Color', [0.45, 0.47, 0.49]);
exportgraphics(fig, fullfile(figureDir, 'fig_q2_regret_distribution.png'), ...
    'Resolution', 300, 'BackgroundColor', 'white');
close(fig);

%% 图四 第四关稳健前沿与资源配置
waterCost = 5 * gammaWater;
foodCost = 10 * gammaFood;
fig = figure('Position', [40, 30, 1640, 1040], 'Color', 'w');
layout = tiledlayout(fig, 2, 2, 'TileSpacing', 'compact', 'Padding', 'compact');

axFront = nexttile(layout, [1, 2]);
hold(axFront, 'on');
yyaxis(axFront, 'left');
patch(axFront, [6.5 9.35 9.35 6.5], [0 0 105 105], [0.92 0.93 0.94], ...
    'EdgeColor', 'none', 'FaceAlpha', 0.75, 'HandleVisibility', 'off');
area(axFront, gammaAll, gammaSuccess, 'FaceColor', rose, 'FaceAlpha', 0.10, ...
    'EdgeColor', 'none', 'HandleVisibility', 'off');
hSuccess = plot(axFront, gammaAll, gammaSuccess, '-o', 'Color', rose, ...
    'LineWidth', 2.6, 'MarkerSize', 7, 'MarkerFaceColor', 'w');
plot(axFront, 6, gammaSuccess(7), 'o', 'Color', rose, 'MarkerFaceColor', rose, ...
    'MarkerSize', 12, 'LineWidth', 2, 'HandleVisibility', 'off');
ylabel(axFront, '成功率  百分比');
ylim(axFront, [0 105]);
axFront.YColor = ink;

yyaxis(axFront, 'right');
patch(axFront, [gammaAll; flipud(gammaAll)], [gammaMean; flipud(gammaQ05)], ...
    blue, 'FaceAlpha', 0.12, 'EdgeColor', 'none', 'HandleVisibility', 'off');
hMean = plot(axFront, gammaAll, gammaMean, '-^', 'Color', blue, 'LineWidth', 2.3, ...
    'MarkerSize', 7, 'MarkerFaceColor', blue);
hQ05 = plot(axFront, gammaAll, gammaQ05, '--v', 'Color', teal, 'LineWidth', 2.3, ...
    'MarkerSize', 7, 'MarkerFaceColor', 'w');
ylabel(axFront, '成功样本财富  元');
ylim(axFront, [6800 8250]);
axFront.YColor = ink;
plot(axFront, [6 6], [6800 8250], ':', 'Color', navy, 'LineWidth', 1.7, ...
    'HandleVisibility', 'off');
text(axFront, 6.12, 8175, '题内保护锚点 Γ6', 'Color', navy, ...
    'FontSize', 10.5, 'FontWeight', 'bold');
text(axFront, 7.65, 8100, '扩展压力测试 Γ7至Γ9', 'Color', [0.40 0.42 0.45], ...
    'FontSize', 10.5, 'HorizontalAlignment', 'center');
text(axFront, 6.08, 7460, sprintf('成功率 %.2f%%\n均值 %.0f元\n低分位 %.0f元', ...
    gammaSuccess(7), gammaMean(7), gammaQ05(7)), 'Color', ink, 'FontSize', 10.5, ...
    'BackgroundColor', [0.97 0.98 0.99], 'EdgeColor', lightGray, 'Margin', 6);
xlabel(axFront, '沙暴预算 Γ');
xlim(axFront, [-0.2 9.25]);
axFront.XTick = 0:9;
styleAxes(axFront, gridColor);
legend(axFront, [hSuccess hMean hQ05], {'成功率', '成功样本平均财富', '5%分位财富'}, ...
    'Location', 'southoutside', 'Orientation', 'horizontal', 'Box', 'off');
title(axFront, '稳健性提高带来可行率跃升与财富让渡', ...
    'FontSize', 14, 'FontWeight', 'bold', 'Color', navy);

axResource = nexttile(layout, 3);
b = bar(axResource, gammaAll, [waterCost foodCost gammaCash], 0.70, 'stacked', ...
    'EdgeColor', 'w', 'LineWidth', 0.7);
b(1).FaceColor = blue; b(2).FaceColor = teal; b(3).FaceColor = [0.76 0.82 0.89];
hold(axResource, 'on');
plot(axResource, [6.5 6.5], [0 10000], ':', 'Color', navy, 'LineWidth', 1.5, ...
    'HandleVisibility', 'off');
for k = [1 4 7 10]
    text(axResource, gammaAll(k), 10180, sprintf('水食各%.0f箱', gammaWater(k)), ...
        'HorizontalAlignment', 'center', 'FontSize', 9.5, 'Color', ink);
end
xlabel(axResource, '沙暴预算 Γ'); ylabel(axResource, '初始资金构成  元');
ylim(axResource, [0 10800]); axResource.XTick = 0:9;
styleAxes(axResource, gridColor);
legend(axResource, b, {'购水支出', '购食支出', '初购后现金'}, ...
    'Location', 'southoutside', 'Orientation', 'horizontal', 'Box', 'off');
title(axResource, '一万元预算的资源替换路径', 'FontSize', 13.5, ...
    'FontWeight', 'bold', 'Color', navy);

axArrival = nexttile(layout, 4);
hold(axArrival, 'on');
for k = 1:numel(gammaValue)
    plot(axArrival, [8 latestArrival(k)], [gammaValue(k) gammaValue(k)], ...
        '-', 'Color', [0.84 0.87 0.89], 'LineWidth', 6, 'HandleVisibility', 'off');
end
scatter(axArrival, latestArrival, gammaValue, 110, guaranteedWealth, 'filled', ...
    'MarkerEdgeColor', 'w', 'LineWidth', 1.2);
plot(axArrival, latestArrival, gammaValue, '-', 'Color', gold, 'LineWidth', 2.1, ...
    'HandleVisibility', 'off');
for k = 1:numel(gammaValue)
    text(axArrival, latestArrival(k) + 0.12, gammaValue(k), ...
        sprintf('第%.0f天  %.0f元', latestArrival(k), guaranteedWealth(k)), ...
        'VerticalAlignment', 'middle', 'FontSize', 9.6, 'Color', ink);
end
colormap(axArrival, natureMap(teal, purple, 64));
cb = colorbar(axArrival); cb.Label.String = '保证财富下界  元'; cb.Box = 'off';
xlabel(axArrival, '最迟保证到达日'); ylabel(axArrival, '沙暴预算 Γ');
xlim(axArrival, [7.7 15.2]); ylim(axArrival, [-0.5 6.5]);
axArrival.YTick = 0:6; axArrival.YDir = 'reverse';
styleAxes(axArrival, gridColor);
title(axArrival, '题内范围的安全到达阶梯', 'FontSize', 13.5, ...
    'FontWeight', 'bold', 'Color', navy);

title(layout, '第四关沙暴预算的稳健前沿与资源代价', ...
    'FontSize', 16, 'FontWeight', 'bold', 'Color', navy);
exportgraphics(fig, fullfile(figureDir, 'fig_q2_q4_robust_frontier.png'), ...
    'Resolution', 300, 'BackgroundColor', 'white');
close(fig);

%% 图五 第四关三策略样本外证据
fig = figure('Position', [40, 30, 1660, 1040], 'Color', 'w');
layout = tiledlayout(fig, 2, 2, 'TileSpacing', 'compact', 'Padding', 'compact');
axDots = nexttile(layout, [2 1]);
hold(axDots, 'on');
gridX = repmat(1:100, 1, 100);
gridY = repelem(1:100, 100);
for g = 1:3
    yBase = (4 - g) * 118;
    outcomeColor = repmat([0.84 0.85 0.86], 10000, 1);
    outcomeColor(1:mcSuccessCount(g), :) = repmat(strategyColor(g, :), mcSuccessCount(g), 1);
    scatter(axDots, gridX, yBase + gridY, 7, outcomeColor, 'filled', ...
        'MarkerFaceAlpha', 0.78, 'MarkerEdgeColor', 'none');
    text(axDots, -3, yBase + 52, strategyLabel(g), 'HorizontalAlignment', 'right', ...
        'FontWeight', 'bold', 'Color', navy, 'FontSize', 11);
    text(axDots, 105, yBase + 52, sprintf('成功 %.2f%%\n失败 %.2f%%', ...
        mcSuccess(g), 100 - mcSuccess(g)), 'FontSize', 10.5, 'Color', ink, ...
        'VerticalAlignment', 'middle');
end
xlim(axDots, [-28 128]); ylim(axDots, [112 458]);
axis(axDots, 'off');
title(axDots, '每个微点代表一条天气情景', 'FontSize', 13.5, ...
    'FontWeight', 'bold', 'Color', navy);
text(axDots, 50, 116, '彩色为成功情景  灰色为失败情景  每组共一万点', ...
    'HorizontalAlignment', 'center', 'FontSize', 10.5, 'Color', [0.45 0.47 0.49]);

axWealth = nexttile(layout, 2);
plotRidgePanel(axWealth, wealthGroups, strategyLabel, strategyColor, ...
    [6800 8550], 25, '终端财富  元', '成功样本财富分布', mcMean, mcQ05, ...
    {'均值', '5%分位'});

axRegret = nexttile(layout, 4);
plotRidgePanel(axRegret, regretGroups, strategyLabel, strategyColor, ...
    [0 1100], 20, '后悔值  元', '相对不可执行参照上界的后悔值', ...
    mcMeanRegret, mcMaxRegret, {'均值', '最大值'});

title(layout, '第四关三种策略的三万条样本外证据', ...
    'FontSize', 16, 'FontWeight', 'bold', 'Color', navy);
exportgraphics(fig, fullfile(figureDir, 'fig_q2_q4_strategy_evidence.png'), ...
    'Resolution', 300, 'BackgroundColor', 'white');
close(fig);

%% 图六 第四关稳健性复核
fig = figure('Position', [60, 60, 1580, 760], 'Color', 'w');
layout = tiledlayout(fig, 1, 2, 'TileSpacing', 'compact', 'Padding', 'compact');
axStorm = nexttile(layout, 1);
hold(axStorm, 'on');
yyaxis(axStorm, 'left');
for k = 1:numel(stormFactor)
    scatter(axStorm, stormFactor(k), stormSuccess(k), 70 + 22 * stormArrival(k), ...
        rose, 'filled', 'MarkerFaceAlpha', 0.75, 'MarkerEdgeColor', 'w', 'LineWidth', 1.1);
end
hStorm = plot(axStorm, stormFactor, stormSuccess, '-', 'Color', rose, 'LineWidth', 2.5);
ylabel(axStorm, '成功率  百分比'); ylim(axStorm, [95.5 100.2]); axStorm.YColor = ink;
yyaxis(axStorm, 'right');
patch(axStorm, [stormFactor; flipud(stormFactor)], [stormMean; flipud(stormQ05)], ...
    teal, 'FaceAlpha', 0.14, 'EdgeColor', 'none', 'HandleVisibility', 'off');
hStormMean = plot(axStorm, stormFactor, stormMean, '-^', 'Color', blue, ...
    'LineWidth', 2.3, 'MarkerFaceColor', blue, 'MarkerSize', 8);
hStormQ = plot(axStorm, stormFactor, stormQ05, '--v', 'Color', teal, ...
    'LineWidth', 2.3, 'MarkerFaceColor', 'w', 'MarkerSize', 8);
plot(axStorm, [1 1], [7100 7600], ':', 'Color', navy, 'LineWidth', 1.6, ...
    'HandleVisibility', 'off');
text(axStorm, 1.01, 7580, '题内估计基准', 'Color', navy, 'FontSize', 10.5);
for k = 1:numel(stormFactor)
    text(axStorm, stormFactor(k), stormQ05(k) - 24, sprintf('%.1f天', stormArrival(k)), ...
        'HorizontalAlignment', 'center', 'Color', ink, 'FontSize', 9.5);
end
ylabel(axStorm, '成功样本财富  元'); ylim(axStorm, [7100 7620]); axStorm.YColor = ink;
xlabel(axStorm, '沙暴概率倍率'); xlim(axStorm, [0.64 1.36]); axStorm.XTick = stormFactor';
styleAxes(axStorm, gridColor);
legend(axStorm, [hStorm hStormMean hStormQ], {'成功率', '平均财富', '5%分位财富'}, ...
    'Location', 'southoutside', 'Orientation', 'horizontal', 'Box', 'off');
title(axStorm, '沙暴概率扰动下的性能稳定性', 'FontSize', 14, ...
    'FontWeight', 'bold', 'Color', navy);

axHeat = nexttile(layout, 2);
matProb = [double(weatherMat.("晴朗")), double(weatherMat.("高温")), ...
    double(weatherMat.("沙暴"))];
imagesc(axHeat, matProb);
colormap(axHeat, natureMap([0.96 0.92 0.84], purple, 256));
caxis(axHeat, [0 0.60]);
axHeat.XTick = 1:3; axHeat.XTickLabel = {'次日晴朗', '次日高温', '次日沙暴'};
axHeat.YTick = 1:3; axHeat.YTickLabel = {'前日晴朗', '前日高温', '前日沙暴'};
axHeat.TickLength = [0 0]; axHeat.Box = 'off';
for r = 1:3
    for c = 1:3
        if matProb(r, c) > 0.42
            txtColor = 'w';
        else
            txtColor = ink;
        end
        text(axHeat, c, r, sprintf('%.2f', matProb(r, c)), ...
            'HorizontalAlignment', 'center', 'FontWeight', 'bold', ...
            'FontSize', 13, 'Color', txtColor);
    end
end
cb = colorbar(axHeat); cb.Label.String = '转移概率'; cb.Box = 'off';
title(axHeat, '名义天气转移矩阵', 'FontSize', 14, ...
    'FontWeight', 'bold', 'Color', navy);
xlabel(axHeat, '次日天气'); ylabel(axHeat, '前一日天气');

title(layout, '第四关沙暴扰动与天气机制的双重灵敏性复核', ...
    'FontSize', 16, 'FontWeight', 'bold', 'Color', navy);
exportgraphics(fig, fullfile(figureDir, 'fig_q2_q4_robustness_validation.png'), ...
    'Resolution', 300, 'BackgroundColor', 'white');
close(fig);

fprintf('第二问参考样式优化图表已生成至 %s\n', figureDir);

%% 局部函数
function drawFlowBand(ax, xLeft, xRight, yLeft0, yLeft1, yRight0, yRight1, colorValue, alphaValue)
    t = linspace(0, 1, 100);
    smoothT = 3 * t .^ 2 - 2 * t .^ 3;
    xValue = xLeft + (xRight - xLeft) * t;
    lowerY = yLeft0 + (yRight0 - yLeft0) * smoothT;
    upperY = yLeft1 + (yRight1 - yLeft1) * smoothT;
    patch(ax, [xValue, fliplr(xValue)], ...
        [lowerY - 0.005, fliplr(upperY - 0.005)], ...
        [0.68, 0.69, 0.70], 'FaceAlpha', 0.12, 'EdgeColor', 'none');
    vertexColor = zeros(200, 3);
    for k = 1:100
        lightAmount = 0.18 + 0.22 * sin(pi * t(k));
        renderedColor = (1 - lightAmount) * colorValue + lightAmount;
        vertexColor(k, :) = renderedColor;
        vertexColor(201 - k, :) = renderedColor;
    end
    bandPatch = patch(ax, 'XData', [xValue, fliplr(xValue)], ...
        'YData', [lowerY, fliplr(upperY)], 'FaceColor', 'interp', ...
        'FaceAlpha', alphaValue, 'EdgeColor', 'none');
    bandPatch.FaceVertexCData = vertexColor;
    line(ax, xValue, upperY, 'Color', 0.55 * colorValue + 0.45, ...
        'LineWidth', 0.7, 'HandleVisibility', 'off');
end

function cmap = natureMap(startColor, endColor, count)
    t = linspace(0, 1, count)';
    cmap = (1 - t) .* startColor + t .* endColor;
end

function styleAxes(ax, gridColor)
    grid(ax, 'on');
    ax.GridLineStyle = ':';
    ax.GridAlpha = 0.32;
    ax.GridColor = gridColor;
    ax.Box = 'off';
    ax.TickDir = 'out';
    ax.LineWidth = 0.9;
end

function plotRidgePanel(ax, groups, labels, colors, xRange, binWidth, ...
        xLabelText, titleText, markerOne, markerTwo, markerLabels)
    hold(ax, 'on');
    edges = xRange(1):binWidth:xRange(2);
    centers = edges(1:end-1) + binWidth / 2;
    maxDensity = 0;
    densitySet = cell(3, 1);
    for g = 1:3
        values = groups{g};
        densitySet{g} = smoothdata(histcounts(values, edges, 'Normalization', 'pdf'), ...
            'gaussian', 7);
        maxDensity = max(maxDensity, max(densitySet{g}));
    end
    for g = 1:3
        y0 = 4 - g;
        ridge = 0.58 * densitySet{g} / maxDensity;
        fill(ax, [centers fliplr(centers)], [y0 + ridge y0 * ones(size(ridge))], ...
            colors(g, :), 'FaceAlpha', 0.38, 'EdgeColor', colors(g, :), ...
            'LineWidth', 1.1, 'HandleVisibility', 'off');
        values = groups{g};
        sampleIndex = unique(round(linspace(1, numel(values), min(850, numel(values)))));
        sampleValue = values(sampleIndex);
        deterministicJitter = 0.12 * sin((1:numel(sampleValue)) * 2.39996);
        scatter(ax, sampleValue, y0 - 0.18 + deterministicJitter, 7, colors(g, :), ...
            'filled', 'MarkerFaceAlpha', 0.18, 'MarkerEdgeColor', 'none', ...
            'HandleVisibility', 'off');
        plot(ax, markerOne(g), y0 + 0.78, 'd', 'MarkerFaceColor', colors(g, :), ...
            'MarkerEdgeColor', 'w', 'MarkerSize', 8, 'LineWidth', 1, ...
            'HandleVisibility', 'off');
        plot(ax, markerTwo(g), y0 + 0.78, 'v', 'MarkerFaceColor', 'w', ...
            'MarkerEdgeColor', colors(g, :), 'MarkerSize', 8, 'LineWidth', 1.5, ...
            'HandleVisibility', 'off');
        text(ax, xRange(2) - 0.02 * diff(xRange), y0 + 0.45, ...
            sprintf('%s %.0f  %s %.0f', markerLabels{1}, markerOne(g), ...
            markerLabels{2}, markerTwo(g)), 'HorizontalAlignment', 'right', ...
            'FontSize', 9.5, 'Color', [0.17 0.18 0.20]);
    end
    plot(ax, nan, nan, 'd', 'MarkerFaceColor', colors(1, :), 'MarkerEdgeColor', 'w');
    plot(ax, nan, nan, 'v', 'MarkerFaceColor', 'w', 'MarkerEdgeColor', colors(1, :));
    legend(ax, markerLabels, 'Location', 'northwest', 'Orientation', 'horizontal', ...
        'Box', 'off', 'FontSize', 9.5);
    xlim(ax, xRange); ylim(ax, [0.55 3.95]);
    ax.YTick = 1:3; ax.YTickLabel = fliplr(labels);
    ax.YGrid = 'off'; ax.XGrid = 'on'; ax.GridLineStyle = ':'; ax.GridAlpha = 0.26;
    ax.Box = 'off'; ax.TickDir = 'out';
    xlabel(ax, xLabelText); title(ax, titleText, 'FontSize', 13.5, ...
        'FontWeight', 'bold', 'Color', [47 76 107] / 255);
end
