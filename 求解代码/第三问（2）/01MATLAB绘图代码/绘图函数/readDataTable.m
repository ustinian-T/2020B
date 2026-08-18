function T = readDataTable(filePath)
try
    T = readtable(filePath,'Encoding','UTF-8','VariableNamingRule','preserve');
catch
    T = readtable(filePath,'VariableNamingRule','preserve');
end
end
