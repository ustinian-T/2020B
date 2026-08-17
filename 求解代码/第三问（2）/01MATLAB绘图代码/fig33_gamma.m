function fig33_gamma(dataPath,outPath)
filePath = fullfile(dataPath,'第六关','第六关Gamma灵敏度.csv');
if ~isfile(filePath)
    warning('缺少文件: %s',filePath);
    return;
end
T = sortrows(readDataTable(filePath),'Gamma');
C = natureColors();
fig = figure('Position',[80 60 1320 620],'Color','w');

subplot(1,2,1); hold on;
yyaxis left
plot(T.Gamma,T.('最坏财富下界'),'-o','Color',C(1,:),'MarkerFaceColor',C(1,:),'MarkerSize',8);
fill([T.Gamma; flipud(T.Gamma)],[T.('最坏财富下界')*0.995; flipud(T.('最坏财富下界')*1.005)],C(6,:),...
    'FaceAlpha',0.25,'EdgeColor','none');
plot(T.Gamma,T.('最坏财富下界'),'-o','Color',C(1,:),'MarkerFaceColor',C(1,:),'MarkerSize',8);
ylabel('最坏财富下界');
g = gca; g.YAxis(1).Color = C(1,:);

yyaxis right
plot(T.Gamma,T.('保证用时'),'-s','Color',C(5,:),'MarkerFaceColor',C(5,:),'MarkerSize',7);
plot(T.Gamma,T.('挖矿天数'),'-^','Color',C(2,:),'MarkerFaceColor',C(2,:),'MarkerSize',7);
ylabel('保证用时 / 挖矿天数');
g.YAxis(2).Color = C(5,:);
xlabel('Gamma');
title('（a）收益下界与策略代价','FontWeight','bold');
legend({'收益下界波动带','最坏财富下界','保证用时','挖矿天数'},'Location','southwest');

subplot(1,2,2);
B = bar(T.Gamma,[T.('初始水') T.('初始食物')],0.72,'LineStyle','none');
B(1).FaceColor = C(1,:);
B(2).FaceColor = C(2,:);
hold on;
for i = 1:numel(T.Gamma)
    text(T.Gamma(i)-0.17,T.('初始水')(i)+2,sprintf('%d',T.('初始水')(i)),'HorizontalAlignment','center','FontSize',9);
    text(T.Gamma(i)+0.17,T.('初始食物')(i)+2,sprintf('%d',T.('初始食物')(i)),'HorizontalAlignment','center','FontSize',9);
end
xlabel('Gamma'); ylabel('初始采购量'); title('（b）初始采购方案变化','FontWeight','bold');
legend({'初始水','初始食物'},'Location','northwest');

sgtitle('图3-3 Gamma 鲁棒权衡分析','FontSize',18,'FontWeight','bold');
exportImage(fig,outPath,'图3-3Gamma鲁棒权衡分析');
end
