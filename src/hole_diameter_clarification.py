"""Поиск отверстий только внутри области детали и русское уточнение диаметра."""
from __future__ import annotations
import json,re
from dataclasses import dataclass,asdict
from pathlib import Path
PATTERN=re.compile(r"(?:[Ø⌀Фф]|\b(?:DIA|D|ДИАМЕТР)\s*)\s*[:=]?\s*(\d+(?:[.,]\d+)?)",re.I)
@dataclass(frozen=True)
class Circle: x:int; y:int; radius:int
@dataclass(frozen=True)
class HoleSpec: count:int; diameter:float; source:str
class ClarificationRequired(RuntimeError): pass

def _automatic_figure_roi(image):
    import cv2
    gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY); binary=cv2.adaptiveThreshold(gray,255,cv2.ADAPTIVE_THRESH_GAUSSIAN_C,cv2.THRESH_BINARY_INV,41,12)
    kernel=cv2.getStructuringElement(cv2.MORPH_RECT,(9,9)); joined=cv2.morphologyEx(binary,cv2.MORPH_CLOSE,kernel,iterations=2)
    contours,_=cv2.findContours(joined,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE); height,width=gray.shape; page=height*width; candidates=[]
    for contour in contours:
        x,y,w,h=cv2.boundingRect(contour); box=w*h
        if page*.08<=box<=page*.82 and w>=width*.15 and h>=height*.15:
            extent=cv2.contourArea(contour)/max(box,1); candidates.append((box*(.5+extent),x,y,w,h))
    if not candidates:return None
    _,x,y,w,h=max(candidates); margin=max(4,round(min(width,height)*.01)); return max(0,x-margin),max(0,y-margin),min(width-x+margin,w+2*margin),min(height-y+margin,h+2*margin)

def _manual_figure_roi(image):
    try:
        import tkinter as tk
        from PIL import Image,ImageTk
        import cv2
        rgb=cv2.cvtColor(image,cv2.COLOR_BGR2RGB); source=Image.fromarray(rgb); shown=source.copy(); shown.thumbnail((1000,700)); sx=source.width/shown.width; sy=source.height/shown.height
        root=tk.Tk(); root.title("Укажите область детали"); tk.Label(root,text="Мышью обведите только саму деталь, без размерных линий и надписей",font=("Arial",14,"bold")).pack(pady=8)
        photo=ImageTk.PhotoImage(shown); canvas=tk.Canvas(root,width=shown.width,height=shown.height,cursor="cross"); canvas.pack(); canvas.create_image(0,0,image=photo,anchor="nw"); state={}
        def down(event): state.update(x0=event.x,y0=event.y); state["rectangle"]=canvas.create_rectangle(event.x,event.y,event.x,event.y,outline="red",width=3)
        def move(event):
            if "rectangle" in state:canvas.coords(state["rectangle"],state["x0"],state["y0"],event.x,event.y);state.update(x1=event.x,y1=event.y)
        def accept():
            if "x1" not in state:return
            x0,x1=sorted((state["x0"],state["x1"]));y0,y1=sorted((state["y0"],state["y1"]));state["answer"]=(round(x0*sx),round(y0*sy),round((x1-x0)*sx),round((y1-y0)*sy));root.destroy()
        canvas.bind("<Button-1>",down);canvas.bind("<B1-Motion>",move);tk.Button(root,text="Использовать выделенную область",command=accept,font=("Arial",13),bg="#2e7d32",fg="white").pack(pady=8);root.protocol("WM_DELETE_WINDOW",root.destroy);root.mainloop();return state.get("answer")
    except (ImportError,tk.TclError):return None

def _circles_in_roi(image,roi):
    import cv2,numpy as np
    x0,y0,width,height=roi; crop=image[y0:y0+height,x0:x0+width]; gray=cv2.cvtColor(crop,cv2.COLOR_BGR2GRAY); gray=cv2.GaussianBlur(gray,(5,5),1.2); side=min(width,height); edges=cv2.Canny(gray,60,150)
    raw=cv2.HoughCircles(gray,cv2.HOUGH_GRADIENT,dp=1.1,minDist=max(12,side//18),param1=120,param2=22,minRadius=max(3,side//120),maxRadius=max(7,side//18))
    accepted=[]
    if raw is not None:
        for cx,cy,radius in raw[0]:
            cx,cy,radius=map(lambda value:int(round(value)),(cx,cy,radius)); hits=0; samples=96
            for angle in np.linspace(0,2*np.pi,samples,endpoint=False):
                px=int(round(cx+radius*np.cos(angle)));py=int(round(cy+radius*np.sin(angle))); xa=max(0,px-2);xb=min(width,px+3);ya=max(0,py-2);yb=min(height,py+3)
                if xa<xb and ya<yb and np.any(edges[ya:yb,xa:xb]):hits+=1
            if hits/samples>=.62:accepted.append(Circle(cx+x0,cy+y0,radius))
    accepted.sort(key=lambda c:(c.y,c.x)); result=[]
    for circle in accepted:
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
        if roi is None:raise ClarificationRequired("Не удалось определить область детали. Выделите её рамкой")
    circles=_circles_in_roi(image,roi)
    if len(circles)>12:
        selected=_manual_figure_roi(image)
        if selected is None:raise ClarificationRequired("Найдено слишком много окружностей. Выделите только область детали")
        circles=_circles_in_roi(image,selected)
    if len(circles)>12:raise ClarificationRequired("Не удалось надёжно отличить отверстия от линий чертежа")
    return circles,image

def read_diameter(source):
    try:
        import cv2,pytesseract
        image=cv2.imread(str(source));text=pytesseract.image_to_string(image,config="--psm 11",lang="rus+eng") if image is not None else ""
    except (ImportError,RuntimeError):return None
    match=PATTERN.search(text);return float(match.group(1).replace(",",".")) if match else None

def preview(image,circles,path):
    import cv2
    result=image.copy()
    for number,circle in enumerate(circles,1):cv2.circle(result,(circle.x,circle.y),circle.radius,(0,0,255),3);cv2.putText(result,str(number),(circle.x+circle.radius+3,circle.y),cv2.FONT_HERSHEY_SIMPLEX,.7,(0,0,255),2)
    cv2.imwrite(str(path),result)
def ask(path,count):
    try:
        import tkinter as tk
        from tkinter import messagebox
        from PIL import Image,ImageTk
        root=tk.Tk();root.title("Уточнение диаметра отверстий");root.geometry("900x760");tk.Label(root,text=f"Найдено отверстий: {count}",font=("Arial",16,"bold")).pack(pady=8);tk.Label(root,text="Проверьте красные отметки и укажите общий диаметр.").pack();image=Image.open(path);image.thumbnail((840,560));photo=ImageTk.PhotoImage(image);panel=tk.Label(root,image=photo);panel.image=photo;panel.pack(pady=8);row=tk.Frame(root);row.pack();tk.Label(row,text="Общий диаметр отверстий, мм:",font=("Arial",13)).pack(side="left");value=tk.StringVar();entry=tk.Entry(row,textvariable=value,font=("Arial",13));entry.pack(side="left",padx=8);entry.focus_set();answer={}
        def accept():
            try:number=float(value.get().strip().replace(",","."));assert number>0
            except (ValueError,AssertionError):messagebox.showerror("Ошибка","Введите положительный диаметр, например 12,5");return
            answer["value"]=number;root.destroy()
        tk.Button(root,text="Подтвердить",command=accept,bg="#2e7d32",fg="white",font=("Arial",13)).pack(pady=8);root.protocol("WM_DELETE_WINDOW",root.destroy);root.mainloop();return answer.get("value")
    except (ImportError,tk.TclError):return None
def resolve(source,output):
    source,output=Path(source),Path(output);saved=output/f"{source.stem}_hole_diameter.json"
    if saved.exists():
        data=json.loads(saved.read_text(encoding="utf-8"));return HoleSpec(int(data["count"]),float(data["diameter"]),data.get("source","operator"))
    circles,image=detect_holes(source)
    if not circles:return None
    diameter=read_diameter(source)
    if diameter is not None:return HoleSpec(len(circles),diameter,"drawing_ocr")
    picture=output/f"{source.stem}_holes_to_clarify.png";preview(image,circles,picture);question=output/f"{source.stem}_hole_question.json";question.write_text(json.dumps({"status":"ожидается_диаметр","файл":source.name,"количество_отверстий":len(circles),"вопрос":"Какой общий диаметр отверстий, мм?","изображение":picture.name},ensure_ascii=False,indent=2),encoding="utf-8");diameter=ask(picture,len(circles))
    if diameter is None:raise ClarificationRequired(f"Укажите диаметр {len(circles)} отверстий")
    spec=HoleSpec(len(circles),diameter,"operator");saved.write_text(json.dumps(asdict(spec),ensure_ascii=False,indent=2),encoding="utf-8");question.unlink(missing_ok=True);return spec
def add_to_info_dxf(path,spec):
    try:import ezdxf
    except ImportError as error:raise RuntimeError("Для записи диаметра требуется ezdxf") from error
    document=ezdxf.readfile(path);model=document.modelspace()
    if "HOLE_INFO" not in document.layers:document.layers.add("HOLE_INFO",color=3)
    model.add_mtext(f"{spec.count} ОТВ. ⌀{spec.diameter:g} мм",dxfattribs={"layer":"HOLE_INFO","char_height":5}).set_location((0,10));document.saveas(path)
