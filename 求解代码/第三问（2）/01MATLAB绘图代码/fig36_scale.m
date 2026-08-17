function fig36_scale(dataPath,outPath)
filePath = fullfile(dataPath,'第六关','第六关玩家数推广试验.csv');
if ~isfile(filePath)
    warning('缺少文件: %s',filePath);
    return;
end
T = sortrows(readDataTable(filePath),'玩家数');
C = natureColors();
fig = figure('Position',[70 60 1450 540],'Color','w');

subplot(1,3,1); hold on;
fill([T.('玩家数'); flipud(T.('玩家数'))],[repmat(min(T.('平均终端财富'))-120,height(T),1); flipud(T.('平均终端财富'))],C(6,:),...
    'FaceAlpha',0.35,'EdgeColor','none');
plot(T.('玩家数'),T.('平均终端财富'),'-o','Color',C(1,:),'MarkerFaceColor',C(1,:),'MarkerSize',8);
for i = 1:height(T)
    text(T.('玩家数')(i),T.('平均终端财富')(i)+35,sprintf('%.0f',T.('平均终端财富')(i)),'HorizontalAlignment','center','FontSize',9);
end
xlabel('玩家数'); ylabel('平均终端财富'); title('（a）平均财富变化','FontWeight','bold');

subplot(1,3,2); hold on;
fill([T.('玩家数'); flipud(T.('玩家数'))],[repmat(min(T.('最差终端财富'))-120,height(T),1); flipud(T.('最差终端财富'))],C(2,:),...
    'FaceAlpha',0.20,'EdgeColor','none');
plot(T.('玩家数'),T.('最差终端财富'),'-s','Color',C(2,:),'MarkerFaceColor',C(2,:),'MarkerSize',8);
for i = 1:height(T)
    text(T.('玩家数')(i),T.('最差终端财富')(i)+35,sprintf('%.0f',T.('最差终端财富')(i)),'HorizontalAlignment','center','FontSize',9);
end
xlabel('玩家数'); ylabel('最差终端财富'); title('（b）最差财富变化','FontWeight','bold');

subplot(1,3,3);
yyaxis left
bar(T.('玩家数'),T.('L_conflict'),0.55,'FaceColor',C(3,:),'EdgeColor','none');
ylabel('冲突损失 L_{conflict}');
yyaxis right
plot(T.('玩家数'),T.('执行天数'),'-d','Color',[0.20 0.20 0.20],'MarkerFaceColor',[0.20 0.20 0.20],'MarkerSize',7);
ylabel('执行天数'); xlabel('玩家数'); title('（c）冲突损失与执行天数','FontWeight','bold');

sgtitle('图3-6 玩家规模扩展分析','FontSize',18,'FontWeight','bold');
exportImage(fig,outPath,'图3-6玩家规模扩展分析');
end
