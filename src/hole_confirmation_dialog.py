import json, os, sys, tempfile
from pathlib import Path
from types import SimpleNamespace
import cv2
import hole_diameter_clarification as holes
source=Path(sys.argv[1]); x0,y0,w,h=map(int,json.loads(sys.argv[2])); response=Path(sys.argv[3])
_,image=holes.detect_holes(source)
if image is None: os._exit(3)
crop=image[y0:y0+h,x0:x0+w]
if crop.size==0: os._exit(4)
handle,path=tempfile.mkstemp(suffix=".png"); os.close(handle); cv2.imwrite(path,crop)
try:
    circles,_=holes.detect_holes(Path(path)); candidates=list(circles); gray=cv2.cvtColor(crop,cv2.COLOR_BGR2GRAY); gray=cv2.createCLAHE(2.0,(8,8)).apply(gray); side=min(gray.shape[:2])
    for scale in (1.0,1.6,2.2):
        work=cv2.resize(gray,None,fx=scale,fy=scale,interpolation=cv2.INTER_CUBIC); work=cv2.GaussianBlur(work,(5,5),1.2)
        for threshold in (9,12,15,18,22):
            found=cv2.HoughCircles(work,cv2.HOUGH_GRADIENT,1.1,max(8,side//35)*scale,param1=70,param2=threshold,minRadius=max(2,int(2*scale)),maxRadius=max(5,int(side//12*scale)))
            if found is None:continue
            for cx,cy,radius in found[0]:
                cx=float(cx/scale); cy=float(cy/scale); radius=float(radius/scale)
                if any((float(item.x)-cx)**2+(float(item.y)-cy)**2<max(6.,radius)**2 for item in candidates):continue
                candidates.append(SimpleNamespace(x=cx,y=cy,r=radius,radius=radius))
    confirmed=holes.confirm_holes(crop,candidates,holes.read_diameter(source))
    if confirmed is None:os._exit(2)
    selected=[{"x":x0+float(candidates[i].x),"y":y0+float(candidates[i].y)} for i in confirmed["active"] if 0<=i<len(candidates)]
    if int(confirmed["count"])!=len(selected):os._exit(5)
    temp=response.with_suffix(".tmp"); temp.write_text(json.dumps({"count":len(selected),"diameter":float(confirmed["diameter"]),"circles":selected},ensure_ascii=False),encoding="utf-8"); temp.replace(response)
finally:
    try:os.unlink(path)
    except OSError:pass
os._exit(0)
