function fig35_regret(dataPath,outPath)
filePath = fullfile(dataPath,'第六关','第六关Ex-post-Regret上界.csv');
if ~isfile(filePath)
    warning('缺少文件: %s',filePath);
    return;
end
T = readDataTable(filePath);
C = natureColors();
fig = figure('Position',[80 60 1320 620],'Color','w');

subplot(1,2,1); hold on;
for i = 1:height(T)
    plot([i i],[T.online_wealth(i) T.oracle_upper_bound(i)],'-','Color',[0.65 0.65 0.65],'LineWidth',2.2);
end
s1 = scatter(1:height(T),T.online_wealth,110,'o','filled','MarkerFaceColor',C(1,:),'MarkerEdgeColor','w','LineWidth',1.0);
s2 = scatter(1:height(T),T.oracle_upper_bound,130,'s','filled','MarkerFaceColor',C(3,:),'MarkerEdgeColor','w','LineWidth',1.0);
for i = 1:height(T)
    text(i-0.08,T.online_wealth(i)-1300,sprintf('%.0f',T.online_wealth(i)),'FontSize',9,'Color',C(1,:));
    text(i-0.10,T.oracle_upper_bound(i)+900,sprintf('%.0f',T.oracle_upper_bound(i)),'FontSize',9,'Color',C(3,:));
end
xlim([0.5 height(T)+0.5]);
set(gca,'XTick',1:height(T),'XTickLabel',compose('玩家%d',T.player));
ylabel('收益'); title('（a）在线收益与 Oracle 上界','FontWeight','bold');
legend([s1 s2],{'在线收益','Oracle 上界'},'Location','northwest');

subplot(1,2,2);
ratio = T.regret ./ T.oracle_upper_bound;
b = bar(T.player,ratio*100,0.55,'FaceColor',C(5,:),'EdgeColor','none'); hold on;
plot(T.player,ratio*100,'-o','Color',[0.35 0.12 0.12],'MarkerFaceColor',[0.35 0.12 0.12]);
for i = 1:height(T)
    text(T.player(i),ratio(i)*100 + 1.2,sprintf('%.1f%%',ratio(i)*100),'HorizontalAlignment','center','FontSize',10,'FontWeight','bold');
end
xlabel('玩家编号'); ylabel('Regret 占 Oracle 比例（%）'); title('（b）Ex-post-Regret 相对比例','FontWeight','bold');

sgtitle('图3-5 Ex-post-Regret 分析','FontSize',18,'FontWeight','bold');
exportImage(fig,outPath,'图3-5Ex-post-Regret分析');
end
