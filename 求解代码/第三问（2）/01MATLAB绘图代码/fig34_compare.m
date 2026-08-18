function fig34_compare(dataPath,outPath)
file1 = fullfile(dataPath,'第六关','第六关基准对比.csv');
file2 = fullfile(dataPath,'第六关','第六关消融实验.csv');
if ~isfile(file1) || ~isfile(file2)
    warning('缺少基准或消融实验文件');
    return;
end
T1 = readDataTable(file1);
T2 = readDataTable(file2);
C = natureColors();
fig = figure('Position',[70 60 1400 620],'Color','w');
subplot(1,2,1); localCompare(T1,'基准','（a）基准模型对比',C);
subplot(1,2,2); localCompare(T2,'版本','（b）消融实验对比',C);
sgtitle('图3-4 基准与消融实验','FontSize',18,'FontWeight','bold');
exportImage(fig,outPath,'图3-4基准与消融实验');
end

function localCompare(T,nameField,panelTitle,C)
nameList = cellstr(string(T.(nameField)));
wealth = T.('平均终端财富');
days = T.('执行天数');
success = false(height(T),1);
if islogical(T.('成功'))
    success = T.('成功');
else
    success = strcmpi(string(T.('成功')),'true');
end
successWealth = wealth(success & ~isnan(wealth));
if isempty(successWealth)
    refMax = 1;
else
    refMax = max(successWealth);
end
showWealth = wealth;
showWealth(~success | isnan(showWealth)) = refMax * 0.08;

b = bar(showWealth,0.62,'FaceColor','flat','EdgeColor','none'); hold on;
colorData = repmat(C(6,:),numel(showWealth),1);
for i = 1:numel(showWealth)
    if success(i)
        colorData(i,:) = C(1,:);
    else
        colorData(i,:) = [0.82 0.82 0.82];
    end
end
b.CData = colorData;

yyaxis right
plot(1:numel(days),days,'-o','Color',[0.2 0.2 0.2],'MarkerFaceColor',[0.2 0.2 0.2],'MarkerSize',8);
ylabel('执行天数');
yyaxis left
ylabel('平均终端财富');
set(gca,'XTick',1:numel(nameList),'XTickLabel',nameList);
xtickangle(18);

for i = 1:numel(nameList)
    if success(i)
        text(i,showWealth(i)+refMax*0.03,sprintf('%.0f',showWealth(i)),'HorizontalAlignment','center','FontSize',10,'FontWeight','bold');
    else
        text(i,showWealth(i)+refMax*0.02,'不可行','HorizontalAlignment','center','FontSize',10,'Color',[0.35 0.35 0.35],'FontWeight','bold');
    end
end

title(panelTitle,'FontWeight','bold');
end
