"""Photo-to-DXF watcher producing clean and fully dimensioned DXFs."""
from __future__ import annotations
import os, re, shutil, time
from pathlib import Path
import hole_diameter_clarification as holes

ROOT=Path(__file__).resolve().parent.parent; INBOX=ROOT/"новые фотографии"; OUTPUT=ROOT/"DXF"; DONE=INBOX/"_done"
EXTENSIONS={".png",".jpg",".jpeg",".tif",".tiff",".bmp",".heic"}; NUMBER=re.compile(r"(?<!\d)(\d+(?:[.,]\d+)?)(?!\d)")

def _ocr_numbers(source):
    try:
        import cv2, pytesseract
        image=cv2.imread(str(source))
        if image is None:return []
        return [float(v.replace(",",".")) for v in NUMBER.findall(pytesseract.image_to_string(image,config="--psm 11",lang="rus+eng"))]
    except (ImportError,RuntimeError,ValueError):return []

def _defaults(numbers,roi):
    large=sorted({v for v in numbers if v>=50},reverse=True)
    if len(large)>=2:
        a,b=large[:2]; portrait=roi is None or roi[3]>=roi[2]; width,height=(min(a,b),max(a,b)) if portrait else (max(a,b),min(a,b))
    else:width,height=395.,830.
    return width,height,[v for v in numbers if 0<v<min(width,height)*.25]

def _hole_defaults(circles,roi,width,height,small):
    result=[]
    for circle in circles:
        if roi:
            x0,y0,rw,rh=roi; nx=max(0.,min(1.,(circle.x-x0)/max(rw,1))); ny=max(0.,min(1.,(y0+rh-circle.y)/max(rh,1)))
            hs="слева" if nx<.5 else "справа"; vs="снизу" if ny<.5 else "сверху"; dx=min(nx,1-nx)*width; dy=min(ny,1-ny)*height
        else:hs,dx,vs,dy="справа",20.,"снизу",20.
        if small:dx=small[0];dy=small[1] if len(small)>1 else small[0]
        result.append((hs,max(0.,dx),vs,max(0.,dy)))
    return result

def _ask_geometry(width,height,defaults,diameter):
    import tkinter as tk
    from tkinter import messagebox,ttk
    root=tk.Tk(); root.title("Размеры и привязка отверстий"); root.attributes("-topmost",True)
    result={}; done=tk.BooleanVar(root,False); wv=tk.StringVar(value=f"{width:g}"); hv=tk.StringVar(value=f"{height:g}")
    tk.Label(root,text="Размеры и расстояния от размерных линий",font=("Arial",15,"bold")).grid(row=0,column=0,columnspan=6,padx=14,pady=10)
    tk.Label(root,text="Ширина, мм").grid(row=1,column=0);tk.Entry(root,textvariable=wv,width=12).grid(row=1,column=1)
    tk.Label(root,text="Высота, мм").grid(row=1,column=2);tk.Entry(root,textvariable=hv,width=12).grid(row=1,column=3)
    controls=[]
    for i,(hs,dx,vs,dy) in enumerate(defaults,1):
        a=tk.StringVar(value=hs);b=tk.StringVar(value=f"{dx:.1f}");c=tk.StringVar(value=vs);d=tk.StringVar(value=f"{dy:.1f}");controls.append((a,b,c,d));r=i+1
        tk.Label(root,text=f"Отверстие {i}: от").grid(row=r,column=0);ttk.Combobox(root,textvariable=a,values=("слева","справа"),state="readonly",width=8).grid(row=r,column=1)
        tk.Entry(root,textvariable=b,width=9).grid(row=r,column=2);tk.Label(root,text="мм; от").grid(row=r,column=3);ttk.Combobox(root,textvariable=c,values=("снизу","сверху"),state="readonly",width=8).grid(row=r,column=4);tk.Entry(root,textvariable=d,width=9).grid(row=r,column=5)
    last=len(controls)+2;tk.Label(root,text=f"Диаметр: {diameter:g} мм").grid(row=last,column=0,columnspan=6,pady=6)
    def finish(accepted):
        if accepted:
            try:
                w=float(wv.get().replace(",","."));h=float(hv.get().replace(",","."));specs=[]
                if w<=0 or h<=0:raise ValueError
                for hs,ds,vs,dv in controls:
                    dx=float(ds.get().replace(",","."));dy=float(dv.get().replace(",","."));x=dx if hs.get()=="слева" else w-dx;y=dy if vs.get()=="снизу" else h-dy
                    if dx<0 or dy<0 or not(0<=x<=w and 0<=y<=h):raise ValueError
                    specs.append({"x":x,"y":y,"h_side":hs.get(),"h_distance":dx,"v_side":vs.get(),"v_distance":dy})
            except ValueError:
                messagebox.showerror("Ошибка","Проверьте размеры и привязки",parent=root);return
            result.update(width=w,height=h,holes=specs)
        root.withdraw();root.update_idletasks();done.set(True)
    tk.Button(root,text="Создать DXF",command=lambda:finish(True),bg="#2e7d32",fg="white",font=("Arial",13)).grid(row=last+1,column=0,columnspan=3,pady=12)
    tk.Button(root,text="Отмена",command=lambda:finish(False),font=("Arial",13)).grid(row=last+1,column=3,columnspan=3,pady=12)
    root.protocol("WM_DELETE_WINDOW",lambda:finish(False));root.update_idletasks();root.lift();root.focus_force();root.grab_set()
    try:root.wait_variable(done)
    finally:
        try:root.grab_release()
        except tk.TclError:pass
        try:root.destroy()
        except tk.TclError:pass
    return result or None

def _document():
    import ezdxf
    doc=ezdxf.new("R12");doc.header["$INSUNITS"]=4
    for name,color in (("CUT",7),("HOLES",1),("DIM",3),("TEXT",2)):
        if name not in doc.layers:doc.layers.add(name,color=color)
    return doc

def _geometry(model,width,height,specs,diameter):
    model.add_polyline2d([(0,0),(width,0),(width,height),(0,height)],close=True,dxfattribs={"layer":"CUT"})
    for s in specs:model.add_circle((s["x"],s["y"]),diameter/2,dxfattribs={"layer":"HOLES"})

def _line(m,a,b):m.add_line(a,b,dxfattribs={"layer":"DIM"})
def _text(m,text,point,height=5):m.add_text(text,dxfattribs={"layer":"TEXT","height":height,"insert":point})
def _dimensions(m,w,h,specs,dia):
    off=max(15.,min(w,h)*.05);_line(m,(0,-off),(w,-off));_line(m,(0,0),(0,-off*1.25));_line(m,(w,0),(w,-off*1.25));_text(m,f"WIDTH {w:g} mm",(w*.35,-off*.85))
    _line(m,(w+off,0),(w+off,h));_line(m,(w,0),(w+off*1.25,0));_line(m,(w,h),(w+off*1.25,h));_text(m,f"HEIGHT {h:g} mm",(w+off*1.15,h*.45))
    for i,s in enumerate(specs,1):
        x,y=s["x"],s["y"];_line(m,(0 if s["h_side"]=="слева" else w,y),(x,y));_line(m,(x,0 if s["v_side"]=="снизу" else h),(x,y));_text(m,f"H{i}: DIA {dia:g}; {s['h_distance']:g} FROM {s['h_side'].upper()}; {s['v_distance']:g} FROM {s['v_side'].upper()}",(x+dia,y+dia+i*2),max(3.,min(w,h)*.012))

def _validate(path,count,info):
    import ezdxf
    entities=list(ezdxf.readfile(path).modelspace());cuts=[e for e in entities if e.dxftype()=="POLYLINE" and e.dxf.layer=="CUT"];circles=[e for e in entities if e.dxftype()=="CIRCLE" and e.dxf.layer=="HOLES"];dims=[e for e in entities if e.dxf.layer in {"DIM","TEXT"}]
    if len(cuts)!=1 or len(circles)!=count or (info and not dims) or (not info and dims):raise RuntimeError("Проверка DXF не пройдена")

def _write(stem,w,h,specs,dia):
    OUTPUT.mkdir(parents=True,exist_ok=True);clear=OUTPUT/f"{stem}_dxf_clear.dxf";info=OUTPUT/f"{stem}_dxf_info.dxf";ct=OUTPUT/f".{stem}_clear.tmp.dxf";it=OUTPUT/f".{stem}_info.tmp.dxf"
    a=_document();_geometry(a.modelspace(),w,h,specs,dia);a.saveas(ct);b=_document();_geometry(b.modelspace(),w,h,specs,dia);_dimensions(b.modelspace(),w,h,specs,dia);b.saveas(it);_validate(ct,len(specs),False);_validate(it,len(specs),True);ct.replace(clear);it.replace(info)

def process(source):
    circles,image=holes.detect_holes(source)
    if image is None:raise RuntimeError("Не удалось открыть изображение")
    confirmed=holes.confirm_holes(image,circles,holes.read_diameter(source))
    if confirmed is None:raise holes.ClarificationRequired("Отверстия не подтверждены")
    selected=[circles[i] for i in confirmed["active"] if 0<=i<len(circles)]
    if confirmed["count"]!=len(selected):raise holes.ClarificationRequired("Количество отверстий не совпадает")
    roi=holes._automatic_figure_roi(image) or holes._manual_figure_roi(image);w,h,small=_defaults(_ocr_numbers(source),roi);geometry=_ask_geometry(w,h,_hole_defaults(selected,roi,w,h,small),confirmed["diameter"])
    if geometry is None:raise holes.ClarificationRequired("Размеры не подтверждены")
    _write(source.stem,geometry["width"],geometry["height"],geometry["holes"],confirmed["diameter"]);DONE.mkdir(parents=True,exist_ok=True);target=DONE/source.name
    if target.exists():target=DONE/f"{source.stem}_{int(time.time())}{source.suffix}"
    shutil.move(str(source),str(target))

def _lock():
    import fcntl
    h=(ROOT/".watcher.lock").open("w")
    try:fcntl.flock(h,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError as e:raise RuntimeError("Обработчик уже запущен") from e
    h.write(str(os.getpid()));h.flush();return h

def main():
    lock=_lock();INBOX.mkdir(parents=True,exist_ok=True);DONE.mkdir(parents=True,exist_ok=True);OUTPUT.mkdir(parents=True,exist_ok=True);signatures={};paused=set();print(f"Слушаю: {INBOX}")
    while True:
        for source in [p for p in INBOX.iterdir() if p.is_file() and p.suffix.lower() in EXTENSIONS]:
            stat=source.stat();sig=(stat.st_size,stat.st_mtime_ns)
            if source in paused:
                if signatures.get(source)==sig:continue
                paused.remove(source)
            if signatures.get(source)!=sig:signatures[source]=sig;continue
            try:process(source);signatures.pop(source,None);print(f"Готово: {source.name}")
            except holes.ClarificationRequired as e:paused.add(source);print(f"Приостановлено: {e}")
            except Exception as e:paused.add(source);print(f"Ошибка: {source.name}: {e}")
        time.sleep(1)
if __name__=="__main__":main()
