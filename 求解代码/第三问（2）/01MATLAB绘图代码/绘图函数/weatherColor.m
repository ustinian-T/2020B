function c = weatherColor(name)
name = char(string(name));
if contains(name,'高温')
    c = [243 222 191] / 255;
elseif contains(name,'沙暴')
    c = [224 206 173] / 255;
elseif contains(name,'晴')
    c = [220 234 244] / 255;
else
    c = [235 235 235] / 255;
end
end
