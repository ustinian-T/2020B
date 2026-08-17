function mk = actionMarker(actionName)
actionName = char(string(actionName));
if contains(actionName,'挖矿')
    mk = 'p';
elseif contains(actionName,'停留')
    mk = 's';
elseif contains(actionName,'购买')
    mk = '^';
else
    mk = 'o';
end
end
