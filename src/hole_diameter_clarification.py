"""Поиск отверстий внутри детали с интерактивным подтверждением оператором."""
from __future__ import annotations
import json,re
from dataclasses import asdict,dataclass
from pathlib import Path
PATTERN=re.compile(r"(?:[Ø⌀Фф]|\b(?:DIA|D|ДИАМЕТР)\s*)\s*[:=]?\s*(\d+(?:[.,]\d+)?)",re.I)
@dataclass(frozen=True)
class Circle:x:int;y:int;radius:int
@dataclass(frozen=True)
class HoleSpec:count:int;diameter:float;source:str
class ClarificationRequired(RuntimeError):pass

def _automatic_figure_roi(image):
 import cv2
 gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY);binary=cv2.adaptiveThreshold(gray,255,cv2.ADAPTIVE_THRESH_GAUSSIAN_C,cv2.THRESH_BINARY_INV,41,12);joined=cv2.morphologyEx(binary,cv2.MORPH_CLOSE,cv2.getStructuringElement(cv2.MORPH_RECT,(9,9)),iterations=2);contours,_=cv2.findContours(joined,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE);height,width=gray.shape;page=height*width;candidates=[]
 for contour in contours:
  x,y,w,h=cv2.boundingRect(contour);box=w*h
  if page*.08<=box<=page*.82 and w>=width*.15 and h>=height*.15:candidates.append((box*(.5+cv2.contourArea(contour)/max(box,1)),x,y,w,h))
 if not candidates:return None
 _,x,y,w,h=max(candidates);margin=max(4,round(min(width,height)*.01));return max(0,x-margin),max(0,y-margin),min(width-x+margin,w+2*margin),min(height-y+margin,h+2*margin)
def _manual_figure_roi(image):
 try:
  import tkinter as tk
  from PIL import Image,ImageTk
  import cv2
  source=Image.fromarray(cv2.cvtColor(image,cv2.COLOR_BGR2RGB));shown=source.copy();shown.thumbnail((1000,700));sx=source.width/shown.width;sy=source.height/shown.height;root=tk.Tk();root.title("Укажите область детали");tk.Label(root,text="Мышью обведите только саму деталь, без размеров и надписей",font=("Arial",14,"bold")).pack(pady=8);photo=ImageTk.PhotoImage(shown);canvas=tk.Canvas(root,width=shown.width,height=shown.height,cursor="cross");canvas.pack();canvas.create_image(0,0,image=photo,anchor="nw");state={}
  def down(e):state.update(x0=e.x,y0=e.y,rectangle=canvas.create_rectangle(e.x,e.y,e.x,e.y,outline="red",width=3))
  def move(e):
   if "rectangle" in state:canvas.coords(state["rectangle"],state["x0"],state["y0"],e.x,e.y);state.update(x1=e.x,y1=e.y)
  def accept():
   if "x1" not in state:return
   x0,x1=sorted((state["x0"],state["x1"]));y0,y1=sorted((state["y0"],state["y1"]));state["answer"]=(round(x0*sx),round(y0*sy),round((x1-x0)*sx),round((y1-y0)*sy));root.destroy()
  canvas.bind("<Button-1>",down);canvas.bind("<B1-Motion>",move);tk.Button(root,text="Использовать выделенную область",command=accept,bg="#2e7d32",fg="white",font=("Arial",13)).pack(pady=8);root.protocol("WM_DELETE_WINDOW",root.destroy);root.mainloop();return state.get("answer")
 except (ImportError,tk.TclError):return None
def _circles_in_roi(image,roi):
 import cv2,numpy as np
 x0,y0,width,height=roi;crop=image[y0:y0+height,x0:x0+width];gray=cv2.GaussianBlur(cv2.cvtColor(crop,cv2.COLOR_BGR2GRAY),(5,5),1.2);side=min(width,height);edges=cv2.Canny(gray,60,150);raw=cv2.HoughCircles(gray,cv2.HOUGH_GRADIENT,1.1,max(12,side//18),param1=120,param2=22,minRadius=max(3,side//120),maxRadius=max(7,side//18));accepted=[]
 if raw is not None:
  for cx,cy,radius in raw[0]:
   cx,cy,radius=(round(cx),round(cy),round(radius));hits=0
   for angle in np.linspace(0,2*np.pi,96,endpoint=False):
    px=round(cx+radius*np.cos(angle));py=round(cy+radius*np.sin(angle));xa=max(0,px-2);xb=min(width,px+3);ya=max(0,py-2);yb=min(height,py+3);hits+=int(xa<xb and ya<yb and np.any(edges[ya:yb,xa:xb]))
   if hits/96>=.62:accepted.append(Circle(cx+x0,cy+y0,radius))
 result=[]
 for circle in sorted(accepted,key=lambda c:(c.y,c.x)):
  if not any((circle.x-old.x)**2+(circle.y-old.y)**2<=max(circle.radius,old.radius)**2 for old in result):result.append(circle)
 return result
def detect_holes(source):
 try:import cv2
 except ImportError as error:raise RuntimeError("Для поиска отверстий требуется opencv-python") from error
 image=cv2.imread(str(source))
 if image is None:return [],None
 roi=_automatic_figure_roi(image)
 if roi is None:
  roi=_manual_figure_roi(image)
  if roi is None:raise ClarificationRequired("Не удалось определить область детали")
 circles=_circles_in_roi(image,roi)
 if len(circles)>12:
  roi=_manual_figure_roi(image)
  if roi is None:raise ClarificationRequired("Выделите только область детали")
  circles=_circles_in_roi(image,roi)
 if len(circles)>20:raise ClarificationRequired("Слишком много сомнительных окружностей")
 return circles,image
def read_diameter(source):
 try:
  import cv2,pytesseract
  image=cv2.imread(str(source));text=pytesseract.image_to_string(image,config="--psm 11",lang="rus+eng") if image is not None else ""
 except (ImportError,RuntimeError):return None
 match=PATTERN.search(text);return float(match.group(1).replace(",",".")) if match else None
def toggle_nearest(circles,active,x,y,scale_x=1,scale_y=1):
 distances=[((circle.x/scale_x-x)**2+(circle.y/scale_y-y)**2,index) for index,circle in enumerate(circles)]
 if not distances:return active
 distance,index=min(distances);circle=circles[index];limit=max(14,circle.radius/max(scale_x,scale_y)*2.2)
 if distance<=limit*limit:
  active=set(active);active.remove(index) if index in active else active.add(index)
 return active
def confirm_holes(image,circles,recognized_diameter=None):
 try:
  import tkinter as tk
  from tkinter import messagebox
  from PIL import Image,ImageTk
  import cv2
  source=Image.fromarray(cv2.cvtColor(image,cv2.COLOR_BGR2RGB));shown=source.copy();shown.thumbnail((1000,650));sx=source.width/shown.width;sy=source.height/shown.height;root=tk.Tk();root.title("Подтверждение отверстий");tk.Label(root,text="Нажмите на ошибочные красные отметки — они станут серыми",font=("Arial",15,"bold")).pack(pady=6);tk.Label(root,text="Красные — подтверждённые отверстия, серые — исключённые").pack();photo=ImageTk.PhotoImage(shown);canvas=tk.Canvas(root,width=shown.width,height=shown.height);canvas.pack(pady=6);active=set(range(len(circles)));count=tk.StringVar(value=str(len(active)));diameter=tk.StringVar(value="" if recognized_diameter is None else f"{recognized_diameter:g}")
  def redraw():
   canvas.delete("all");canvas.create_image(0,0,image=photo,anchor="nw")
   for index,circle in enumerate(circles):
    x=circle.x/sx;y=circle.y/sy;r=max(6,circle.radius/max(sx,sy));color="red" if index in active else "#888888";canvas.create_oval(x-r,y-r,x+r,y+r,outline=color,width=3);canvas.create_text(x+r+8,y,text=str(index+1),fill=color,font=("Arial",12,"bold"))
   count.set(str(len(active)))
  def click(event):
   nonlocal active;active=toggle_nearest(circles,active,event.x,event.y,sx,sy);redraw()
  def accept():
   try:confirmed=int(count.get());value=float(diameter.get().strip().replace(",","."));assert confirmed>=0 and value>0
   except (ValueError,AssertionError):messagebox.showerror("Ошибка","Проверьте количество и введите положительный диаметр, например 12,5");return
   result.update(count=confirmed,diameter=value,active=sorted(active));root.destroy()
  controls=tk.Frame(root);controls.pack();tk.Label(controls,text="Подтверждённое количество:").grid(row=0,column=0);tk.Entry(controls,textvariable=count,width=8).grid(row=0,column=1,padx=6);tk.Label(controls,text="Общий диаметр, мм:").grid(row=0,column=2);tk.Entry(controls,textvariable=diameter,width=10).grid(row=0,column=3,padx=6);tk.Button(root,text="Подтвердить",command=accept,bg="#2e7d32",fg="white",font=("Arial",13)).pack(pady=8);canvas.bind("<Button-1>",click);root.protocol("WM_DELETE_WINDOW",root.destroy);result={};redraw();root.mainloop();return result or None
 except (ImportError,tk.TclError):return None
def preview(image,circles,path):
 import cv2
 result=image.copy()
 for number,circle in enumerate(circles,1):cv2.circle(result,(circle.x,circle.y),circle.radius,(0,0,255),3);cv2.putText(result,str(number),(circle.x+circle.radius+3,circle.y),cv2.FONT_HERSHEY_SIMPLEX,.7,(0,0,255),2)
 cv2.imwrite(str(path),result)
def resolve(source,output):
 source,output=Path(source),Path(output);saved=output/f"{source.stem}_hole_diameter.json"
 if saved.exists():
  data=json.loads(saved.read_text(encoding="utf-8"));return HoleSpec(int(data["count"]),float(data["diameter"]),data.get("source","operator"))
 circles,image=detect_holes(source)
 if not circles:return None
 recognized=read_diameter(source);answer=confirm_holes(image,circles,recognized)
 if answer is None:
  picture=output/f"{source.stem}_holes_to_clarify.png";preview(image,circles,picture);raise ClarificationRequired("Подтвердите правильные отверстия и их диаметр")
 if answer["count"]==0:return None
 selected=[circles[index] for index in answer["active"]];picture=output/f"{source.stem}_confirmed_holes.png";preview(image,selected,picture);spec=HoleSpec(answer["count"],answer["diameter"],"operator_confirmed");saved.write_text(json.dumps({**asdict(spec),"selected_marks":[index+1 for index in answer["active"]]},ensure_ascii=False,indent=2),encoding="utf-8");return spec
def add_to_info_dxf(path,spec):
 try:import ezdxf
 except ImportError as error:raise RuntimeError("Для записи диаметра требуется ezdxf") from error
 document=ezdxf.readfile(path);model=document.modelspace()
 if "HOLE_INFO" not in document.layers:document.layers.add("HOLE_INFO",color=3)
 model.add_mtext(f"{spec.count} ОТВ. ⌀{spec.diameter:g} мм",dxfattribs={"layer":"HOLE_INFO","char_height":5}).set_location((0,10));document.saveas(path)
