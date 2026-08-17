function fig37_rolling(dataPath,outPath)

close all; clc;

rootDir = fileparts(mfilename('fullpath'));
dataFile = fullfile(dataPath,...
    '..','02数据文件','第六关','第六关逐日滚动策略.csv');
outDir = fileparts(mfilename('fullpath'));
if ~exist(outDir, 'dir'), mkdir(outDir); end

FONT = 'SimHei';
inkNavy = [32 64 96]/255;
cSteel  = [80 128 160]/255;
cAmber  = [208 144 64]/255;
cBrick  = [176 96 80]/255;
cGray   = [0.55 0.55 0.55];
wxSunny = [0.83 0.93 0.93];
wxHot   = [0.98 0.90 0.78];
wxStorm = [0.86 0.86 0.86];

RL = rdTable(dataFile, ...
    {'Day','Wth','P','From','Act','To','BuyW','BuyF','Mult','CW','CF', ...
     'BuyCost','MineInc','After','Water','Food','Cash','Arrived','EqType','eps'});
pList = unique(RL.P).';
maxDay = max(RL.Day);

% 到达日与终端财富均从数据计算：
% 到达日 = 该玩家“已到终点=True”的首日；
% 终端财富 = 末日现金 + 剩余水食半价回收（水5元/箱、食品10元/箱）
arrStr = strcmp(string(RL.Arrived), 'True');
arriveDay  = arrayfun(@(p) min(RL.Day(RL.P == p & arrStr)), pList);
termWealth = arrayfun(@(p) termWealthOf(RL, p), pList);

f7 = figure('Color','w','Position',[60 60 1750 1450]);
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
        text(ax, rows4.Day(i), rows4.After(i)+1.15, '同行×4', ...
            'HorizontalAlignment','center', 'FontName', FONT, 'FontSize', 10, ...
            'Color', cBrick, 'FontWeight', 'bold');
    end
    ylim(ax, [0.5 25.8]); yticks(ax, [1 5 9 13 17 21 25]);
    xlim(ax, [0.5 maxDay+0.5]); xticks(ax, 1:maxDay);
    if k == 3
        xlabel(ax, '日期', 'FontName', FONT, 'FontSize', 10.5);
    end
    ylabel(ax, '区域', 'FontName', FONT, 'FontSize', 10.5);
    styleAxes(ax, 10.5);
    text(ax, 0.75, 24.2, sprintf('玩家%d', p), 'FontName', FONT, 'FontSize', 13, ...
        'FontWeight', 'bold', 'Color', inkNavy);
    text(ax, maxDay/2+0.5, 24.2, sprintf('第%d天到达终点 终端财富%.1f元', arriveDay(k), termWealth(k)), ...
        'HorizontalAlignment','center', 'FontName', FONT, 'FontSize', 11, ...
        'FontWeight', 'bold', 'Color', cBrick);
    if k == 1
        hSun = patch(ax, NaN, NaN, wxSunny, 'EdgeColor', 'none');
        hHot = patch(ax, NaN, NaN, wxHot, 'EdgeColor', 'none');
        hSto = patch(ax, NaN, NaN, wxStorm, 'EdgeColor', 'none');
        hTra = plot(ax, NaN, NaN, '-', 'Color', inkNavy, 'LineWidth', 2);
        hMov = plot(ax, NaN, NaN, 'o', 'Color', cSteel, 'MarkerFaceColor', 'w');
        hSta = plot(ax, NaN, NaN, 's', 'Color', cSteel, 'MarkerFaceColor', 'w');
        hMin = plot(ax, NaN, NaN, 'd', 'Color', cAmber, 'MarkerFaceColor', cAmber);
        hArr = plot(ax, NaN, NaN, 'p', 'Color', cBrick, 'MarkerFaceColor', cBrick);
        legend(ax, [hSun hHot hSto hTra hMov hSta hMin hArr], ...
            {'晴朗','高温','沙暴','位置轨迹','行走','停留','挖矿','到达终点'}, ...
            'FontName', FONT, 'FontSize', 10.5, 'Orientation', 'horizontal', ...
            'Location', 'southoutside', 'NumColumns', 8, 'Box', 'off');
    end
end

addTitle(t7, '图3-7 第六关三玩家逐日滚动策略轨迹', ...
    sprintf(['每日滚动重解阶段Nash并只执行当日均衡行动；全部日期均为纯策略均衡、当日ε=0；' ...
             '三玩家依次于第%d、%d、%d天到达终点'], arriveDay(1), arriveDay(2), arriveDay(3)));
outPng = fullfile(outDir, '图3-7 第六关三玩家逐日滚动策略轨迹.png');
print(f7, outPng, '-dpng', '-r300');
fprintf('图3-7 已输出：%s\n', outPng);

    % ================= 嵌套辅助函数 =================
    function T = rdTable(f, varNames)
        opts = detectImportOptions(f, 'Encoding', 'UTF-8');
        opts.VariableNames = varNames;
        T = readtable(f, opts);
    end

    function w = termWealthOf(T, p)
        rows = T(T.P == p, :);
        last = rows(end, :);
        w = last.Cash + last.Water*2.5 + last.Food*5;
    end

    function styleAxes(ax, fs)
        ax.FontName = FONT; ax.FontSize = fs;
        ax.Box = 'off'; ax.Color = 'w';
        ax.XColor = [0.2 0.2 0.2]; ax.YColor = [0.2 0.2 0.2];
    end

    function addTitle(ax, ttl, sub)
        title(ax, ttl, 'FontName', FONT, 'FontSize', 15, 'FontWeight', 'bold');
        subtitle(ax, sub, 'FontName', FONT, 'FontSize', 10.5, 'Color', [0.25 0.25 0.25]);
    end

    function addWeatherBands(ax, weatherList, yBot, yTop)
        for d = 1:numel(weatherList)
            w = weatherList{d};
            if strcmp(w, '晴朗'),  c = wxSunny;
            elseif strcmp(w, '高温'), c = wxHot;
            else, c = wxStorm; end
            patch(ax, [d-0.5 d+0.5 d+0.5 d-0.5], [yBot yBot yTop yTop], c, ...
                'FaceAlpha', 0.55, 'EdgeColor', 'none', 'HandleVisibility', 'off');
        end
    end
end
