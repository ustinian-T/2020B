clc;
clear;
close all;

addpath(genpath(pwd));
paperStyle();

dataPath = '../02数据文件/';
outPath  = '../03图片输出/';

checkData(dataPath);

fig31_resource(dataPath,outPath);
fig32_heatmap(dataPath,outPath);
fig33_gamma(dataPath,outPath);
fig34_compare(dataPath,outPath);
fig35_regret(dataPath,outPath);
fig36_scale(dataPath,outPath);
fig37_rolling(dataPath,outPath);

disp('第三问图表全部生成完成。');
