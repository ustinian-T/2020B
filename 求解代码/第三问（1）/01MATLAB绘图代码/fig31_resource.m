function fig31_resource(dataPath,outPath)
filePath = fullfile(dataPath,'第五关','第五关玩家逐日策略.csv');
if ~isfile(filePath)
    warning('缺少文件: %s',filePath);
    return;
end
T = readDataTable(filePath);
T = sortrows(T,{'玩家','日期'});
players = unique(T.('玩家'),'stable');
C = natureColors();
fig = figure('Position',[80 60 1200 700],'Color','w');

for k = 1:numel(players)
    D = T(T.('玩家') == players(k),:);
    ax = subplot(numel(players),1,k); hold(ax,'on');
    x = D.('日期');
    water = D.('剩余水');
    food  = D.('剩余食物');
    cashDelta = D.('剩余现金') - D.('剩余现金')(1);
    yMax = max([water; food; 1]) * 1.35;

    for i = 1:numel(x)
        bg = weatherColor(D.('天气')(i));
        patch(ax,[x(i)-0.48 x(i)+0.48 x(i)+0.48 x(i)-0.48],[0 0 yMax yMax],bg,...
            'FaceAlpha',0.35,'EdgeColor','none');
    end

    area(ax,x,water,'FaceColor',C(6,:),'FaceAlpha',0.22,'EdgeColor','none');
    area(ax,x,food,'FaceColor',C(2,:),'FaceAlpha',0.18,'EdgeColor','none');
    p1 = plot(ax,x,water,'-o','Color',C(1,:),'MarkerFaceColor',C(1,:),'MarkerSize',7);
    p2 = plot(ax,x,food,'-s','Color',C(2,:),'MarkerFaceColor',C(2,:),'MarkerSize',7);

    for i = 1:numel(x)
        mk = actionMarker(D.('行动')(i));
        scatter(ax,x(i),min(max(water(i),food(i)) + 0.10*yMax, 0.92*yMax),72,...
            'Marker',mk,'MarkerFaceColor',C(5,:),'MarkerEdgeColor',[0.25 0.25 0.25],'LineWidth',0.8);
        text(ax,x(i),0.97*yMax,char(string(D.('天气')(i))),...
            'HorizontalAlignment','center','VerticalAlignment','top','FontSize',10,'Color',[0.35 0.35 0.35]);
    end

    yyaxis(ax,'right');
    p3 = plot(ax,x,cashDelta,'-d','Color',C(3,:),'MarkerFaceColor',C(3,:),'MarkerSize',6);
    ylabel('现金变化量');
    ax.YAxis(2).Color = C(3,:);
    if all(abs(cashDelta) < 1e-9)
        ylim([-1 1]);
    end

    yyaxis(ax,'left');
    ylabel('水 / 食物');
    xlabel('日期');
    ylim([0 yMax]);
    ax.YAxis(1).Color = [0.2 0.2 0.2];
    title(sprintf('玩家%d 逐日资源轨迹',players(k)),'FontWeight','bold');
    legend([p1,p2,p3],{'剩余水','剩余食物','现金变化量'},'Location','northwest');
end

sgtitle('图3-1 第五关双玩家资源演化','FontSize',18,'FontWeight','bold');
exportImage(fig,outPath,'图3-1第五关双玩家资源演化');
end
