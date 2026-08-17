function checkData(root)
files = {
    '第五关/第五关玩家逐日策略.csv'
    '第五关/第五关灵敏度分析.csv'
    '第六关/第六关Gamma灵敏度.csv'
    '第六关/第六关参数灵敏度.csv'
    '第六关/第六关初始采购邻域灵敏度.csv'
    '第六关/第六关基准对比.csv'
    '第六关/第六关消融实验.csv'
    '第六关/第六关Ex-post-Regret上界.csv'
    '第六关/第六关玩家数推广试验.csv'
    '第六关/第六关逐日滚动策略.csv'};

disp('===== 数据检查 =====');
for i = 1:numel(files)
    f = fullfile(root,files{i});
    if isfile(f)
        fprintf('[OK] %s\n',files{i});
    else
        fprintf('[Missing] %s\n',files{i});
    end
end
end
