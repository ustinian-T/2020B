function C = natureColors(idx)
base = [
110 143 178;
125 164 148;
234 182 122;
229 167 154;
193 110 113;
171 200 229;
216 160 193;
159 141 184;
208 208 138] / 255;
if nargin < 1
    C = base;
else
    C = base(idx,:);
end
end
