function exportImage(figHandle,outPath,fileName)
if ~exist(outPath,'dir')
    mkdir(outPath);
end
fullName = fullfile(outPath,[fileName,'.png']);
try
    exportgraphics(figHandle,fullName,'Resolution',600,'BackgroundColor','white');
catch
    print(figHandle,fullName,'-dpng','-r600');
end
end
