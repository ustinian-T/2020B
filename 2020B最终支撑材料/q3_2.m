%% 第三问（Q3_2）MATLAB 论文图表

clear; close all; clc;

%% 全局样式设置（对应 paperStyle.m）
set(groot,'defaultFigureColor','w');
set(groot,'defaultAxesFontName','Microsoft YaHei');
set(groot,'defaultTextFontName','Microsoft YaHei');
set(groot,'defaultAxesFontSize',12);
set(groot,'defaultTextFontSize',12);
set(groot,'defaultAxesLineWidth',1.1);
set(groot,'defaultLineLineWidth',2.0);
set(groot,'defaultAxesBox','on');
set(groot,'defaultAxesXGrid','on');
set(groot,'defaultAxesYGrid','on');
set(groot,'defaultAxesGridAlpha',0.18);
set(groot,'defaultAxesGridLineStyle','-');
set(groot,'defaultLegendBox','off');

%% 颜色定义
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

%% 路径设置
scriptDir = fileparts(mfilename('fullpath'));
projectRoot = fullfile(scriptDir, '..', '..');  % 向上2层到Q3代码附件
dataPath = fullfile(projectRoot, '结果验证');   % 数据目录（注意：数据在结果验证中）
figureDir = fullfile(scriptDir, '图表');        % 图表输出目录
if ~exist(figureDir, 'dir'), mkdir(figureDir); end

%% 数据检查
checkData(dataPath);

%% 图3-2 参数敏感性热力图
fig32_heatmap(dataPath, figureDir);

%% 图3-3 Gamma 鲁棒权衡分析
fig33_gamma(dataPath, figureDir);

%% 图3-4 基准与消融实验
fig34_compare(dataPath, figureDir);

%% 图3-5 Ex-post-Regret 分析
fig35_regret(dataPath, figureDir);

%% 图3-6 玩家规模扩展分析
fig36_scale(dataPath, figureDir);

%% 图3-7 逐日滚动策略轨迹
fig37_rolling(dataPath, figureDir);

fprintf('第三问（Q3_2）图表全部生成完成。\n');

%% 局部函数
function checkData(root)
    files = {
        '第五关/第五关灵敏度分析.csv'
        '第六关/第六关Gamma灵敏度.csv'
        '第六关/第六关参数灵敏度.csv'
        '第六关/第六关初始采购邻域灵敏度.csv'
        '第六关/第六关基准对比.csv'
        '第六关/第六关消融实验.csv'
        '第六关/第六关Ex-post-Regret上界.csv'
        '第六关/第六关玩家数推广试验.csv'
        '第六关/第六关逐日滚动策略.csv'
        '第六关/第六关经验重采样.csv'
        '第六关/第六关模型检验摘要.json'
        '第六关/第六关小规模精确对照.json'
        };

    disp('===== 数据检查 =====');
    for i = 1:numel(files)
        f = fullfile(root, files{i});
        if isfile(f)
            fprintf('[OK] %s\n', files{i});
        else
            fprintf('[Missing] %s\n', files{i});
        end
    end
end

function T = readDataTable(filePath, varNames)
    if nargin < 2
        try
            T = readtable(filePath, 'Encoding', 'UTF-8', 'VariableNamingRule', 'preserve');
        catch
            T = readtable(filePath, 'VariableNamingRule', 'preserve');
        end
    else
        opts = detectImportOptions(filePath, 'Encoding', 'UTF-8');
        opts.VariableNames = varNames;
        T = readtable(filePath, opts);
    end
end

function T = rdTable(f, varNames)
    % 兼容旧接口：与 readDataTable 相同，支持指定列名
    T = readDataTable(f, varNames);
end

function exportImage(figHandle, outPath, fileName)
    if ~exist(outPath, 'dir'), mkdir(outPath); end
    fullName = fullfile(outPath, [fileName, '.png']);
    try
        exportgraphics(figHandle, fullName, 'Resolution', 600, 'BackgroundColor', 'white');
    catch
        print(figHandle, fullName, '-dpng', '-r600');
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

function cmap = softRedBlue()
    base = [49 54 149; 69 117 180; 116 173 209; 255 255 255; 253 174 97; 215 48 39] / 255;
    x = linspace(0, 1, size(base, 1));
    xi = linspace(0, 1, 256);
    cmap = interp1(x, base, xi);
end

function cmap = natureMap(modeName)
    if nargin < 1, modeName = 'diverging'; end
    C = natureColors();
    switch lower(modeName)
        case 'bluegreen'
            anchors = [C(1, :); C(6, :); C(2, :)];
        case 'purpleyellow'
            anchors = [C(8, :); 0.97 0.96 0.93; C(3, :)];
        otherwise
            anchors = [C(1, :); 0.97 0.97 0.96; C(5, :)];
    end
    x = linspace(0, 1, size(anchors, 1));
    xi = linspace(0, 1, 256);
    cmap = interp1(x, anchors, xi, 'pchip');
end

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

function fig32_heatmap(dataPath, outPath)
    file1 = fullfile(dataPath, '第六关', '第六关参数灵敏度.csv');
    file2 = fullfile(dataPath, '第六关', '第六关初始采购邻域灵敏度.csv');
    if ~isfile(file1)
        warning('缺少文件: %s', file1);
        return;
    end
    T1 = readDataTable(file1);
    C = natureColors();
    fig = figure('Position', [70 60 1400 650], 'Color', 'w');

    subplot(1, 2, 1);
    params = unique(T1.('参数'), 'stable');
    vals = unique(T1.('参数值'), 'stable');
    M = nan(numel(params), numel(vals));
    for i = 1:height(T1)
        r = find(strcmp(string(params), string(T1.('参数')(i))), 1);
        c = find(vals == T1.('参数值')(i), 1);
        M(r, c) = T1.('最坏财富下界')(i);
    end
    imagesc(M, 'AlphaData', ~isnan(M));
    colormap(gca, natureMap('diverging'));
    set(gca, 'XTick', 1:numel(vals), 'XTickLabel', vals, 'YTick', 1:numel(params), 'YTickLabel', cellstr(string(params)), ...
        'TickDir', 'out', 'LineWidth', 1.0);
    xtickangle(30);
    cb1 = colorbar; cb1.Label.String = '最坏财富下界';
    xlabel('参数值'); ylabel('参数'); title('（a）核心参数灵敏度', 'FontWeight', 'bold');
    caxis([nanmin(M(:)) nanmax(M(:))]);
    for i = 1:size(M, 1)
        for j = 1:size(M, 2)
            if ~isnan(M(i, j))
                tcol = [0 0 0];
                if M(i, j) > mean(M(~isnan(M)))
                    tcol = [1 1 1] * 0.05;
                end
                text(j, i, sprintf('%.0f', M(i, j)), 'HorizontalAlignment', 'center', 'FontSize', 11, 'FontWeight', 'bold', 'Color', tcol);
            end
        end
    end

    subplot(1, 2, 2);
    if isfile(file2)
        T2 = readDataTable(file2);
        xvals = unique(T2.('食物偏移'), 'stable');
        yvals = unique(T2.('水偏移'), 'stable');
        N = nan(numel(yvals), numel(xvals));
        for i = 1:height(T2)
            r = find(yvals == T2.('水偏移')(i), 1);
            c = find(xvals == T2.('食物偏移')(i), 1);
            N(r, c) = T2.('最坏财富下界')(i);
        end
        imagesc(N, 'AlphaData', ~isnan(N));
        colormap(gca, natureMap('diverging'));
        set(gca, 'XTick', 1:numel(xvals), 'XTickLabel', xvals, 'YTick', 1:numel(yvals), 'YTickLabel', yvals, ...
            'TickDir', 'out', 'LineWidth', 1.0);
        cb2 = colorbar; cb2.Label.String = '最坏财富下界';
        xlabel('食物偏移'); ylabel('水偏移'); title('（b）初始采购邻域灵敏度', 'FontWeight', 'bold');
        caxis([nanmin(N(:)) nanmax(N(:))]);
        for i = 1:size(N, 1)
            for j = 1:size(N, 2)
                if ~isnan(N(i, j))
                    tcol = [0 0 0];
                    if N(i, j) > mean(N(~isnan(N)))
                        tcol = [1 1 1] * 0.05;
                    end
                    text(j, i, sprintf('%.0f', N(i, j)), 'HorizontalAlignment', 'center', 'FontSize', 11, 'FontWeight', 'bold', 'Color', tcol);
                end
            end
        end
        hold on;
        if islogical(T2.('是否推荐点'))
            rec = T2.('是否推荐点');
        else
            rec = strcmpi(string(T2.('是否推荐点')), 'True') | strcmpi(string(T2.('是否推荐点')), 'true');
        end
        idx = find(rec);
        for ii = idx(:)'
            cx = find(xvals == T2.('食物偏移')(ii), 1);
            cy = find(yvals == T2.('水偏移')(ii), 1);
            plot(cx, cy, 'p', 'MarkerSize', 22, 'MarkerFaceColor', C(3, :), 'MarkerEdgeColor', 'k', 'LineWidth', 1.3);
            rectangle('Position', [cx - 0.5, cy - 0.5, 1, 1], 'EdgeColor', 'w', 'LineWidth', 2.0, 'LineStyle', '--');
        end
    else
        axis off;
        text(0.5, 0.5, '未找到第六关初始采购邻域灵敏度.csv', 'HorizontalAlignment', 'center');
    end

    sgtitle('图3-2 参数敏感性热力图', 'FontSize', 18, 'FontWeight', 'bold');
    exportImage(fig, outPath, '图3-2参数敏感性热力图');
end

function fig33_gamma(dataPath, outPath)
    filePath = fullfile(dataPath, '第六关', '第六关Gamma灵敏度.csv');
    if ~isfile(filePath)
        warning('缺少文件: %s', filePath);
        return;
    end
    T = sortrows(readDataTable(filePath), 'Gamma');
    C = natureColors();
    fig = figure('Position', [80 60 1320 620], 'Color', 'w');

    subplot(1, 2, 1); hold on;
    yyaxis left
    plot(T.Gamma, T.('最坏财富下界'), '-o', 'Color', C(1, :), 'MarkerFaceColor', C(1, :), 'MarkerSize', 8);
    fill([T.Gamma; flipud(T.Gamma)], [T.('最坏财富下界') * 0.995; flipud(T.('最坏财富下界') * 1.005)], C(6, :), ...
        'FaceAlpha', 0.25, 'EdgeColor', 'none');
    plot(T.Gamma, T.('最坏财富下界'), '-o', 'Color', C(1, :), 'MarkerFaceColor', C(1, :), 'MarkerSize', 8);
    ylabel('最坏财富下界');
    g = gca; g.YAxis(1).Color = C(1, :);

    yyaxis right
    plot(T.Gamma, T.('保证用时'), '-s', 'Color', C(5, :), 'MarkerFaceColor', C(5, :), 'MarkerSize', 7);
    plot(T.Gamma, T.('挖矿天数'), '-^', 'Color', C(2, :), 'MarkerFaceColor', C(2, :), 'MarkerSize', 7);
    ylabel('保证用时 / 挖矿天数');
    g.YAxis(2).Color = C(5, :);
    xlabel('Gamma');
    title('（a）收益下界与策略代价', 'FontWeight', 'bold');
    legend({'收益下界波动带', '最坏财富下界', '保证用时', '挖矿天数'}, 'Location', 'southwest');

    subplot(1, 2, 2);
    B = bar(T.Gamma, [T.('初始水') T.('初始食物')], 0.72, 'LineStyle', 'none');
    B(1).FaceColor = C(1, :);
    B(2).FaceColor = C(2, :);
    hold on;
    for i = 1:numel(T.Gamma)
        text(T.Gamma(i) - 0.17, T.('初始水')(i) + 2, sprintf('%d', T.('初始水')(i)), 'HorizontalAlignment', 'center', 'FontSize', 9);
        text(T.Gamma(i) + 0.17, T.('初始食物')(i) + 2, sprintf('%d', T.('初始食物')(i)), 'HorizontalAlignment', 'center', 'FontSize', 9);
    end
    xlabel('Gamma'); ylabel('初始采购量'); title('（b）初始采购方案变化', 'FontWeight', 'bold');
    legend({'初始水', '初始食物'}, 'Location', 'northwest');

    sgtitle('图3-3 Gamma 鲁棒权衡分析', 'FontSize', 18, 'FontWeight', 'bold');
    exportImage(fig, outPath, '图3-3Gamma鲁棒权衡分析');
end

function fig34_compare(dataPath, outPath)
    file1 = fullfile(dataPath, '第六关', '第六关基准对比.csv');
    file2 = fullfile(dataPath, '第六关', '第六关消融实验.csv');
    if ~isfile(file1) || ~isfile(file2)
        warning('缺少基准或消融实验文件');
        return;
    end
    T1 = readDataTable(file1);
    T2 = readDataTable(file2);
    C = natureColors();
    fig = figure('Position', [70 60 1400 620], 'Color', 'w');
    subplot(1, 2, 1); localCompare(T1, '基准', '（a）基准模型对比', C);
    subplot(1, 2, 2); localCompare(T2, '版本', '（b）消融实验对比', C);
    sgtitle('图3-4 基准与消融实验', 'FontSize', 18, 'FontWeight', 'bold');
    exportImage(fig, outPath, '图3-4基准与消融实验');
end

function localCompare(T, nameField, panelTitle, C)
    nameList = cellstr(string(T.(nameField)));
    wealth = T.('平均终端财富');
    days = T.('执行天数');
    success = false(height(T), 1);
    if islogical(T.('成功'))
        success = T.('成功');
    else
        success = strcmpi(string(T.('成功')), 'true');
    end
    successWealth = wealth(success & ~isnan(wealth));
    if isempty(successWealth)
        refMax = 1;
    else
        refMax = max(successWealth);
    end
    showWealth = wealth;
    showWealth(~success | isnan(showWealth)) = refMax * 0.08;

    b = bar(showWealth, 0.62, 'FaceColor', 'flat', 'EdgeColor', 'none'); hold on;
    colorData = repmat(C(6, :), numel(showWealth), 1);
    for i = 1:numel(showWealth)
        if success(i)
            colorData(i, :) = C(1, :);
        else
            colorData(i, :) = [0.82 0.82 0.82];
        end
    end
    b.CData = colorData;

    yyaxis right
    plot(1:numel(days), days, '-o', 'Color', [0.2 0.2 0.2], 'MarkerFaceColor', [0.2 0.2 0.2], 'MarkerSize', 8);
    ylabel('执行天数');
    yyaxis left
    ylabel('平均终端财富');
    set(gca, 'XTick', 1:numel(nameList), 'XTickLabel', nameList);
    xtickangle(18);

    for i = 1:numel(nameList)
        if success(i)
            text(i, showWealth(i) + refMax * 0.03, sprintf('%.0f', showWealth(i)), 'HorizontalAlignment', 'center', 'FontSize', 10, 'FontWeight', 'bold');
        else
            text(i, showWealth(i) + refMax * 0.02, '不可行', 'HorizontalAlignment', 'center', 'FontSize', 10, 'Color', [0.35 0.35 0.35], 'FontWeight', 'bold');
        end
    end

    title(panelTitle, 'FontWeight', 'bold');
end

function fig35_regret(dataPath, outPath)
    filePath = fullfile(dataPath, '第六关', '第六关Ex-post-Regret上界.csv');
    if ~isfile(filePath)
        warning('缺少文件: %s', filePath);
        return;
    end
    T = readDataTable(filePath);
    C = natureColors();
    fig = figure('Position', [80 60 1320 620], 'Color', 'w');

    subplot(1, 2, 1); hold on;
    for i = 1:height(T)
        plot([i i], [T.online_wealth(i) T.oracle_upper_bound(i)], '-', 'Color', [0.65 0.65 0.65], 'LineWidth', 2.2);
    end
    s1 = scatter(1:height(T), T.online_wealth, 110, 'o', 'filled', 'MarkerFaceColor', C(1, :), 'MarkerEdgeColor', 'w', 'LineWidth', 1.0);
    s2 = scatter(1:height(T), T.oracle_upper_bound, 130, 's', 'filled', 'MarkerFaceColor', C(3, :), 'MarkerEdgeColor', 'w', 'LineWidth', 1.0);
    for i = 1:height(T)
        text(i - 0.08, T.online_wealth(i) - 1300, sprintf('%.0f', T.online_wealth(i)), 'FontSize', 9, 'Color', C(1, :));
        text(i - 0.10, T.oracle_upper_bound(i) + 900, sprintf('%.0f', T.oracle_upper_bound(i)), 'FontSize', 9, 'Color', C(3, :));
    end
    xlim([0.5 height(T) + 0.5]);
    set(gca, 'XTick', 1:height(T), 'XTickLabel', compose('玩家%d', T.player));
    ylabel('收益'); title('（a）在线收益与 Oracle 上界', 'FontWeight', 'bold');
    legend([s1 s2], {'在线收益', 'Oracle 上界'}, 'Location', 'northwest');

    subplot(1, 2, 2);
    ratio = T.regret ./ T.oracle_upper_bound;
    b = bar(T.player, ratio * 100, 0.55, 'FaceColor', C(5, :), 'EdgeColor', 'none'); hold on;
    plot(T.player, ratio * 100, '-o', 'Color', [0.35 0.12 0.12], 'MarkerFaceColor', [0.35 0.12 0.12]);
    for i = 1:height(T)
        text(T.player(i), ratio(i) * 100 + 1.2, sprintf('%.1f%%', ratio(i) * 100), 'HorizontalAlignment', 'center', 'FontSize', 10, 'FontWeight', 'bold');
    end
    xlabel('玩家编号'); ylabel('Regret 占 Oracle 比例（%）'); title('（b）Ex-post-Regret 相对比例', 'FontWeight', 'bold');

    sgtitle('图3-5 Ex-post-Regret 分析', 'FontSize', 18, 'FontWeight', 'bold');
    exportImage(fig, outPath, '图3-5Ex-post-Regret分析');
end

function fig36_scale(dataPath, outPath)
    filePath = fullfile(dataPath, '第六关', '第六关玩家数推广试验.csv');
    if ~isfile(filePath)
        warning('缺少文件: %s', filePath);
        return;
    end
    T = sortrows(readDataTable(filePath), '玩家数');
    C = natureColors();
    fig = figure('Position', [70 60 1450 540], 'Color', 'w');

    subplot(1, 3, 1); hold on;
    fill([T.('玩家数'); flipud(T.('玩家数'))], [repmat(min(T.('平均终端财富')) - 120, height(T), 1); flipud(T.('平均终端财富'))], C(6, :), ...
        'FaceAlpha', 0.35, 'EdgeColor', 'none');
    plot(T.('玩家数'), T.('平均终端财富'), '-o', 'Color', C(1, :), 'MarkerFaceColor', C(1, :), 'MarkerSize', 8);
    for i = 1:height(T)
        text(T.('玩家数')(i), T.('平均终端财富')(i) + 35, sprintf('%.0f', T.('平均终端财富')(i)), 'HorizontalAlignment', 'center', 'FontSize', 9);
    end
    xlabel('玩家数'); ylabel('平均终端财富'); title('（a）平均财富变化', 'FontWeight', 'bold');

    subplot(1, 3, 2); hold on;
    fill([T.('玩家数'); flipud(T.('玩家数'))], [repmat(min(T.('最差终端财富')) - 120, height(T), 1); flipud(T.('最差终端财富'))], C(2, :), ...
        'FaceAlpha', 0.20, 'EdgeColor', 'none');
    plot(T.('玩家数'), T.('最差终端财富'), '-s', 'Color', C(2, :), 'MarkerFaceColor', C(2, :), 'MarkerSize', 8);
    for i = 1:height(T)
        text(T.('玩家数')(i), T.('最差终端财富')(i) + 35, sprintf('%.0f', T.('最差终端财富')(i)), 'HorizontalAlignment', 'center', 'FontSize', 9);
    end
    xlabel('玩家数'); ylabel('最差终端财富'); title('（b）最差财富变化', 'FontWeight', 'bold');

    subplot(1, 3, 3);
    yyaxis left
    bar(T.('玩家数'), T.('L_conflict'), 0.55, 'FaceColor', C(3, :), 'EdgeColor', 'none');
    ylabel('冲突损失 L_{conflict}');
    yyaxis right
    plot(T.('玩家数'), T.('执行天数'), '-d', 'Color', [0.20 0.20 0.20], 'MarkerFaceColor', [0.20 0.20 0.20], 'MarkerSize', 7);
    ylabel('执行天数'); xlabel('玩家数'); title('（c）冲突损失与执行天数', 'FontWeight', 'bold');

    sgtitle('图3-6 玩家规模扩展分析', 'FontSize', 18, 'FontWeight', 'bold');
    exportImage(fig, outPath, '图3-6玩家规模扩展分析');
end

function fig37_rolling(dataPath, outPath)
    close all; clc;

    file = fullfile(dataPath, '第六关', '第六关逐日滚动策略.csv');
    if ~isfile(file)
        warning('缺少文件: %s', file);
        return;
    end

    FONT = 'SimHei';
    inkNavy = [32 64 96] / 255;
    cSteel = [80 128 160] / 255;
    cAmber = [208 144 64] / 255;
    cBrick = [176 96 80] / 255;
    cGray = [0.55 0.55 0.55];
    wxSunny = [0.83 0.93 0.93];
    wxHot = [0.98 0.90 0.78];
    wxStorm = [0.86 0.86 0.86];

    RL = readDataTable(file, ...
        {'Day', 'Wth', 'P', 'From', 'Act', 'To', 'BuyW', 'BuyF', 'Mult', 'CW', 'CF', ...
        'BuyCost', 'MineInc', 'After', 'Water', 'Food', 'Cash', 'Arrived', 'EqType', 'eps'});
    pList = unique(RL.P).';
    maxDay = max(RL.Day);

    % 到达日与终端财富均从数据计算
    arrStr = strcmp(string(RL.Arrived), 'True');
    arriveDay = arrayfun(@(p) min(RL.Day(RL.P == p & arrStr)), pList);
    termWealth = arrayfun(@(p) termWealthOf(RL, p), pList);

    f7 = figure('Color', 'w', 'Position', [60 60 1750 1450]);
    t7 = tiledlayout(f7, 3, 1, 'TileSpacing', 'compact', 'Padding', 'compact');

    for k = 1:3
        p = pList(k);
        rows = RL(RL.P == p, :);
        dayAll = rows.Day;
        nodes = rows.After;
        ax = nexttile(t7); hold(ax, 'on');
        wthByDay = strings(1, maxDay);
        for d = 1:maxDay
            tmpW = RL.Wth(RL.Day == d & RL.P == p);
            if ~isempty(tmpW)
                wthByDay(d) = tmpW(1);
            end
        end
        addWeatherBands(ax, cellstr(wthByDay), 0.5, 25.8);
        stairs(ax, dayAll, nodes, '-', 'Color', inkNavy, 'LineWidth', 2.0);
        for i = 1:numel(dayAll)
            a = rows.Act{i};
            if dayAll(i) == arriveDay(k)
                plot(ax, dayAll(i), nodes(i), 'p', 'Color', cBrick, 'MarkerSize', 17, ...
                    'MarkerFaceColor', cBrick, 'HandleVisibility', 'off');
            elseif strcmp(a, '挖矿')
                plot(ax, dayAll(i), nodes(i), 'd', 'Color', cAmber, 'MarkerSize', 10, ...
                    'MarkerFaceColor', cAmber, 'HandleVisibility', 'off');
            elseif strcmp(a, '退出')
                plot(ax, dayAll(i), nodes(i), 'x', 'Color', cGray, 'MarkerSize', 11, ...
                    'LineWidth', 2.2, 'HandleVisibility', 'off');
            elseif strcmp(a, '停留')
                plot(ax, dayAll(i), nodes(i), 's', 'Color', cSteel, 'MarkerSize', 9, ...
                    'MarkerFaceColor', 'w', 'HandleVisibility', 'off');
            else
                plot(ax, dayAll(i), nodes(i), 'o', 'Color', cSteel, 'MarkerSize', 9, ...
                    'MarkerFaceColor', 'w', 'HandleVisibility', 'off');
            end
        end
        rows4 = rows(rows.Mult == 4, :);
        for i = 1:height(rows4)
            text(ax, rows4.Day(i), rows4.After(i) + 1.15, '同行×4', ...
                'HorizontalAlignment', 'center', 'FontName', FONT, 'FontSize', 10, ...
                'Color', cBrick, 'FontWeight', 'bold');
        end
        ylim(ax, [0.5 25.8]); yticks(ax, [1 5 9 13 17 21 25]);
        xlim(ax, [0.5 maxDay + 0.5]); xticks(ax, 1:maxDay);
        if k == 3
            xlabel(ax, '日期', 'FontName', FONT, 'FontSize', 10.5);
        end
        ylabel(ax, sprintf('玩家 %d 所在节点', p), 'FontName', FONT, 'FontSize', 10.5);
        title(ax, sprintf('玩家 %d：终端财富 = %.0f，到达日 = 第%d天', p, termWealth(k), arriveDay(k)), ...
            'FontName', FONT, 'FontSize', 10.5);
    end

    sgtitle('图3-7 第六关三玩家逐日滚动策略轨迹', 'FontSize', 18, 'FontWeight', 'bold');
    exportImage(f7, outPath, '图3-7 第六关三玩家逐日滚动策略轨迹');
end

function w = termWealthOf(RL, p)
    rows = RL(RL.P == p, :);
    arrRows = rows(strcmp(string(rows.Arrived), 'True'), :);
    if isempty(arrRows)
        w = NaN;
    else
        last = arrRows(end, :);
        w = last.Cash + 0.5 * 5 * last.Water + 0.5 * 10 * last.Food;
    end
end

function addWeatherBands(ax, wthList, yLow, yHigh)
    if nargin < 4, yHigh = 1; end
    n = numel(wthList);
    if n == 0, return; end
    for i = 1:n
        if i < n
            xr = [i i + 1];
        else
            xr = [i i + 0.98];
        end
        c = weatherColor(wthList{i});
        patch(ax, [xr(1) xr(2) xr(2) xr(1)], [yLow yLow yHigh yHigh], c, ...
            'EdgeColor', 'none', 'FaceAlpha', 0.35, 'HandleVisibility', 'off');
    end
    xlim(ax, [0.5 n + 0.5]);
end
