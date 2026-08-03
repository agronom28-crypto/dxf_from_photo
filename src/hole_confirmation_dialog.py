import json, os, sys, tkinter as tk
from pathlib import Path
import cv2, numpy as np
from PIL import Image, ImageTk
import hole_diameter_clarification as holes
source=Path(sys.argv[1]);x0,y0,w,h=map(int,json.loads(sys.argv[2]));response=Path(sys.argv[3]);image=cv2.imread(str(source))
if image is None:os._exit(3)
crop=image[y0:y0+h,x0:x0+w]
if crop.size==0:os._exit(4)
gray=cv2.cvtColor(crop,cv2.COLOR_BGR2GRAY);gray=cv2.createCLAHE(2.0,(8,8)).apply(gray);blur=cv2.GaussianBlur(gray,(5,5),1.2);side=min(w,h);minimum=max(2,int(side*.004));maximum=max(minimum+2,int(side*.035));raw=[]
for p2 in (24,20,17):
 found=cv2.HoughCircles(blur,cv2.HOUGH_GRADIENT,1.2,max(12,int(side*.04)),param1=100,param2=p2,minRadius=minimum,maxRadius=maximum)
 if found is not None:
  for cx,cy,r in found[0]:raw.append((float(cx),float(cy),float(r),p2))
candidates=[]
for cx,cy,r,score in sorted(raw,key=lambda item:-item[3]):
 if cx-r<3 or cy-r<3 or cx+r>w-3 or cy+r>h-3:continue
 yy,xx=np.ogrid[:h,:w];ring=np.abs(np.sqrt((xx-cx)**2+(yy-cy)**2)-r)<=max(1.5,r*.18);contrast=float(np.std(gray[ring])) if np.any(ring) else 0
 if contrast<12:continue
 if any((px-cx)**2+(py-cy)**2<max(pr,r,8)**2 for px,py,pr in candidates):continue
 candidates.append((cx,cy,r))
 if len(candidates)>=40:break
active=set(range(len(candidates)));root=tk.Tk();root.title("Подтверждение отверстий");root.attributes("-topmost",True);scale=min(1100/w,680/h,1.0);shown=cv2.resize(crop,(int(w*scale),int(h*scale)),interpolation=cv2.INTER_AREA);photo=ImageTk.PhotoImage(Image.fromarray(cv2.cvtColor(shown,cv2.COLOR_BGR2RGB)));canvas=tk.Canvas(root,width=shown.shape[1],height=shown.shape[0]);canvas.pack(padx=8,pady=8);canvas.create_image(0,0,image=photo,anchor="nw")
def redraw():
 canvas.delete("mark")
 for i,(cx,cy,r) in enumerate(candidates):
  color="red" if i in active else "gray";canvas.create_oval((cx-r)*scale,(cy-r)*scale,(cx+r)*scale,(cy+r)*scale,outline=color,width=3,tags="mark");canvas.create_text(cx*scale,cy*scale,text=str(i+1),fill=color,font=("Arial",10,"bold"),tags="mark")
 count.set(str(len(active)))
def toggle(event):
 if not candidates:return
 px,py=event.x/scale,event.y/scale;i=min(range(len(candidates)),key=lambda n:(candidates[n][0]-px)**2+(candidates[n][1]-py)**2);cx,cy,r=candidates[i]
 if (cx-px)**2+(cy-py)**2<=max(12,r*1.8)**2:
  active.discard(i) if i in active else active.add(i);redraw()
def clear_all():active.clear();redraw()
def select_all():active.update(range(len(candidates)));redraw()
def finish(code):
 if code==0:
  try:diameter=float(diameter_var.get().replace(",","."))
  except ValueError:return
  selected=[{"x":x0+candidates[i][0],"y":y0+candidates[i][1]} for i in sorted(active)];temp=response.with_suffix(".tmp");temp.write_text(json.dumps({"count":len(selected),"diameter":diameter,"circles":selected},ensure_ascii=False),encoding="utf-8");temp.replace(response)
 root.withdraw();root.update_idletasks();root.after(20,lambda:os._exit(code))
canvas.bind("<Button-1>",toggle);count=tk.StringVar();automatic=holes.read_diameter(source);diameter_var=tk.StringVar(value=f"{automatic:g}" if automatic else "10");redraw();panel=tk.Frame(root);panel.pack(fill="x",padx=8,pady=6);tk.Label(panel,text="Найдено:").pack(side="left");tk.Entry(panel,textvariable=count,width=5,state="readonly").pack(side="left",padx=4);tk.Button(panel,text="Снять все отверстия",command=clear_all).pack(side="left",padx=8);tk.Button(panel,text="Выбрать все",command=select_all).pack(side="left");tk.Label(panel,text="Диаметр, мм:").pack(side="left",padx=(18,4));tk.Entry(panel,textvariable=diameter_var,width=8).pack(side="left");tk.Button(panel,text="Подтвердить",command=lambda:finish(0),bg="#2e7d32",fg="white").pack(side="right",padx=4);tk.Button(panel,text="Отмена",command=lambda:finish(2)).pack(side="right")
root.protocol("WM_DELETE_WINDOW",lambda:finish(2));root.lift();root.focus_force();root.mainloop()
