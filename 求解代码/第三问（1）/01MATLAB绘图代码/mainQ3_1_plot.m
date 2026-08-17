%% 第三问（1）第五关图表生成入口
% 图3-1 第五关双玩家资源演化
%
% 运行方式：
%   在 MATLAB 命令行执行：mainQ3_1_plot
%   或直接按 F5 运行
%
% 依赖：
%   - 02数据文件/第五关/第五关玩家逐日策略.csv
%   - 01MATLAB绘图代码/绘图函数/*.m

clc;
clear;
close all;

addpath(genpath(pwd));
paperStyle();

dataPath = '../02数据文件/';
outPath  = '../03图片输出/';

checkData(dataPath);

fig31_resource(dataPath, outPath);

disp('第三问（1）第五关图表生成完成。');
