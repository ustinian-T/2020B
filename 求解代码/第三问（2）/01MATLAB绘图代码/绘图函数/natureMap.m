function cmap = natureMap(modeName)
if nargin < 1
    modeName = 'diverging';
end
C = natureColors();
switch lower(modeName)
    case 'bluegreen'
        anchors = [C(1,:); C(6,:); C(2,:)];
    case 'purpleyellow'
        anchors = [C(8,:); 0.97 0.96 0.93; C(3,:)];
    otherwise
        anchors = [C(1,:); 0.97 0.97 0.96; C(5,:)];
end
x = linspace(0,1,size(anchors,1));
xi = linspace(0,1,256);
cmap = interp1(x,anchors,xi,'pchip');
end
