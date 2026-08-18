function fig32_heatmap(dataPath,outPath)
file1 = fullfile(dataPath,'第六关','第六关参数灵敏度.csv');
file2 = fullfile(dataPath,'第六关','第六关初始采购邻域灵敏度.csv');
if ~isfile(file1)
    warning('缺少文件: %s',file1);
    return;
end
T1 = readDataTable(file1);
C = natureColors();
fig = figure('Position',[70 60 1400 650],'Color','w');

subplot(1,2,1);
params = unique(T1.('参数'),'stable');
vals = unique(T1.('参数值'),'stable');
M = nan(numel(params), numel(vals));
for i = 1:height(T1)
    r = find(strcmp(string(params),string(T1.('参数')(i))),1);
    c = find(vals == T1.('参数值')(i),1);
    M(r,c) = T1.('最坏财富下界')(i);
end
imagesc(M,'AlphaData',~isnan(M));
colormap(gca,natureMap('diverging'));
set(gca,'XTick',1:numel(vals),'XTickLabel',vals,'YTick',1:numel(params),'YTickLabel',cellstr(string(params)),...
    'TickDir','out','LineWidth',1.0);
xtickangle(30);
cb1 = colorbar; cb1.Label.String = '最坏财富下界';
xlabel('参数值'); ylabel('参数'); title('（a）核心参数灵敏度','FontWeight','bold');
caxis([nanmin(M(:)) nanmax(M(:))]);
for i = 1:size(M,1)
    for j = 1:size(M,2)
        if ~isnan(M(i,j))
            tcol = [0 0 0];
            if M(i,j) > mean(M(~isnan(M)))
                tcol = [1 1 1]*0.05;
            end
            text(j,i,sprintf('%.0f',M(i,j)),'HorizontalAlignment','center','FontSize',11,'FontWeight','bold','Color',tcol);
        end
    end
end

subplot(1,2,2);
if isfile(file2)
    T2 = readDataTable(file2);
    xvals = unique(T2.('食物偏移'),'stable');
    yvals = unique(T2.('水偏移'),'stable');
    N = nan(numel(yvals), numel(xvals));
    for i = 1:height(T2)
        r = find(yvals == T2.('水偏移')(i),1);
        c = find(xvals == T2.('食物偏移')(i),1);
        N(r,c) = T2.('最坏财富下界')(i);
    end
    imagesc(N,'AlphaData',~isnan(N));
    colormap(gca,natureMap('diverging'));
    set(gca,'XTick',1:numel(xvals),'XTickLabel',xvals,'YTick',1:numel(yvals),'YTickLabel',yvals,...
        'TickDir','out','LineWidth',1.0);
    cb2 = colorbar; cb2.Label.String = '最坏财富下界';
    xlabel('食物偏移'); ylabel('水偏移'); title('（b）初始采购邻域灵敏度','FontWeight','bold');
    caxis([nanmin(N(:)) nanmax(N(:))]);
    for i = 1:size(N,1)
        for j = 1:size(N,2)
            if ~isnan(N(i,j))
                tcol = [0 0 0];
                if N(i,j) > mean(N(~isnan(N)))
                    tcol = [1 1 1]*0.05;
                end
                text(j,i,sprintf('%.0f',N(i,j)),'HorizontalAlignment','center','FontSize',11,'FontWeight','bold','Color',tcol);
            end
        end
    end
    hold on;
    if islogical(T2.('是否推荐点'))
        rec = T2.('是否推荐点');
    else
        rec = strcmpi(string(T2.('是否推荐点')),'True') | strcmpi(string(T2.('是否推荐点')),'true');
    end
    idx = find(rec);
    for ii = idx(:)'
        cx = find(xvals == T2.('食物偏移')(ii),1);
        cy = find(yvals == T2.('水偏移')(ii),1);
        plot(cx,cy,'p','MarkerSize',22,'MarkerFaceColor',C(3,:),'MarkerEdgeColor','k','LineWidth',1.3);
        rectangle('Position',[cx-0.5,cy-0.5,1,1],'EdgeColor','w','LineWidth',2.0,'LineStyle','--');
    end
else
    axis off;
    text(0.5,0.5,'未找到第六关初始采购邻域灵敏度.csv','HorizontalAlignment','center');
end

sgtitle('图3-2 参数敏感性热力图','FontSize',18,'FontWeight','bold');
exportImage(fig,outPath,'图3-2参数敏感性热力图');
end
