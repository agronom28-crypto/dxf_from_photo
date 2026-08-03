import json, os, sys
from pathlib import Path
import hole_diameter_clarification as holes
source=Path(sys.argv[1]); response=Path(sys.argv[2])
circles,image=holes.detect_holes(source)
if image is None: os._exit(3)
confirmed=holes.confirm_holes(image,circles,holes.read_diameter(source))
if confirmed is None: os._exit(2)
selected=[]
for index in confirmed["active"]:
    if 0<=index<len(circles): selected.append({"x":float(circles[index].x),"y":float(circles[index].y)})
if int(confirmed["count"])!=len(selected): os._exit(4)
temp=response.with_suffix(".tmp"); temp.write_text(json.dumps({"count":len(selected),"diameter":float(confirmed["diameter"]),"circles":selected},ensure_ascii=False),encoding="utf-8"); temp.replace(response)
os._exit(0)
