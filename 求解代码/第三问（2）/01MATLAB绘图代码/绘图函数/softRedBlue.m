function cmap = softRedBlue()
base = [49 54 149; 69 117 180; 116 173 209; 255 255 255; 253 174 97; 215 48 39] / 255;
x = linspace(0,1,size(base,1));
xi = linspace(0,1,256);
cmap = interp1(x,base,xi);
end
