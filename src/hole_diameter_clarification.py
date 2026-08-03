"""Русскоязычное графическое уточнение диаметра отверстий."""
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

def detect_holes(source):
    try: import cv2
    except ImportError as e: raise RuntimeError("Для поиска отверстий требуется opencv-python") from e
    image=cv2.imread(str(source));
    if image is None: return [],None
    gray=cv2.medianBlur(cv2.cvtColor(image,cv2.COLOR_BGR2GRAY),5); side=min(gray.shape[:2])
    raw=cv2.HoughCircles(gray,cv2.HOUGH_GRADIENT,1.2,max(12,side//30),param1=100,param2=28,minRadius=max(3,side//300),maxRadius=max(8,side//5))
    circles=[] if raw is None else [Circle(round(x),round(y),round(r)) for x,y,r in raw[0]]
    return sorted(circles,key=lambda c:(c.y,c.x)),image

def read_diameter(source):
    try:
        import cv2,pytesseract
        image=cv2.imread(str(source)); text=pytesseract.image_to_string(image,config="--psm 11",lang="rus+eng") if image is not None else ""
    except (ImportError,RuntimeError): return None
    match=PATTERN.search(text); return float(match.group(1).replace(",",".")) if match else None

def preview(image,circles,path):
    import cv2
    result=image.copy()
    for number,c in enumerate(circles,1): cv2.circle(result,(c.x,c.y),c.radius,(0,0,255),3); cv2.putText(result,str(number),(c.x+c.radius+3,c.y),cv2.FONT_HERSHEY_SIMPLEX,.7,(0,0,255),2)
    cv2.imwrite(str(path),result)

def ask(path,count):
    try:
        import tkinter as tk
        from tkinter import messagebox
        from PIL import Image,ImageTk
        root=tk.Tk(); root.title("Уточнение диаметра отверстий"); root.geometry("900x760")
        tk.Label(root,text=f"Найдено отверстий: {count}",font=("Arial",16,"bold")).pack(pady=8); tk.Label(root,text="На чертеже не указан диаметр. Красным отмечены найденные отверстия.").pack()
        image=Image.open(path); image.thumbnail((840,560)); photo=ImageTk.PhotoImage(image); panel=tk.Label(root,image=photo); panel.image=photo; panel.pack(pady=8)
        row=tk.Frame(root); row.pack(); tk.Label(row,text="Общий диаметр отверстий, мм:",font=("Arial",13)).pack(side="left"); value=tk.StringVar(); entry=tk.Entry(row,textvariable=value,font=("Arial",13)); entry.pack(side="left",padx=8); entry.focus_set(); answer={}
        def accept():
            try: number=float(value.get().strip().replace(",",".")); assert number>0
            except (ValueError,AssertionError): messagebox.showerror("Ошибка","Введите положительный диаметр, например 12,5"); return
            answer["value"]=number; root.destroy()
        tk.Button(root,text="Подтвердить",command=accept,bg="#2e7d32",fg="white",font=("Arial",13)).pack(pady=8); root.protocol("WM_DELETE_WINDOW",root.destroy); root.mainloop(); return answer.get("value")
    except (ImportError,tk.TclError): return None

def resolve(source,output):
    source,output=Path(source),Path(output); saved=output/f"{source.stem}_hole_diameter.json"
    if saved.exists():
        data=json.loads(saved.read_text(encoding="utf-8")); return HoleSpec(int(data["count"]),float(data["diameter"]),data.get("source","operator"))
    circles,image=detect_holes(source)
    if not circles: return None
    diameter=read_diameter(source)
    if diameter is not None: return HoleSpec(len(circles),diameter,"drawing_ocr")
    picture=output/f"{source.stem}_holes_to_clarify.png"; preview(image,circles,picture); question=output/f"{source.stem}_hole_question.json"
    question.write_text(json.dumps({"status":"ожидается_диаметр","файл":source.name,"количество_отверстий":len(circles),"вопрос":"Какой общий диаметр отверстий, мм?","изображение":picture.name},ensure_ascii=False,indent=2),encoding="utf-8")
    diameter=ask(picture,len(circles))
    if diameter is None: raise ClarificationRequired(f"Укажите диаметр {len(circles)} отверстий")
    spec=HoleSpec(len(circles),diameter,"operator"); saved.write_text(json.dumps(asdict(spec),ensure_ascii=False,indent=2),encoding="utf-8"); question.unlink(missing_ok=True); return spec

def add_to_info_dxf(path,spec):
    try: import ezdxf
    except ImportError as e: raise RuntimeError("Для записи диаметра требуется ezdxf") from e
    doc=ezdxf.readfile(path); msp=doc.modelspace()
    if "HOLE_INFO" not in doc.layers: doc.layers.add("HOLE_INFO",color=3)
    msp.add_mtext(f"{spec.count} ОТВ. ⌀{spec.diameter:g} мм",dxfattribs={"layer":"HOLE_INFO","char_height":5}).set_location((0,10)); doc.saveas(path)
