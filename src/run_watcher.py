from __future__ import annotations
import json, os, re, shutil, subprocess, sys, time
from pathlib import Path
import hole_diameter_clarification as holes
ROOT=Path(__file__).resolve().parent.parent; INBOX=ROOT/"новые фотографии"; OUTPUT=ROOT/"DXF"; DONE=INBOX/"_done"
EXTENSIONS={".png",".jpg",".jpeg",".tif",".tiff",".bmp",".heic"}; NUMBER=re.compile(r"(?<!\d)(\d+(?:[.,]\d+)?)(?!\d)")
def _ocr(source):
    try:
        import cv2,pytesseract
        image=cv2.imread(str(source)); text=pytesseract.image_to_string(image,config="--psm 11",lang="rus+eng") if image is not None else ""
        return [float(v.replace(",",".")) for v in NUMBER.findall(text)]
    except (ImportError,RuntimeError,ValueError): return []
def _defaults(numbers,roi):
    large=sorted({v for v in numbers if v>=50},reverse=True)
    if len(large)>=2:
        a,b=large[:2]; portrait=roi is None or roi[3]>=roi[2]; w,h=((min(a,b),max(a,b)) if portrait else (max(a,b),min(a,b)))
    else: w,h=395.,830.
    return w,h,[v for v in numbers if 0<v<min(w,h)*.25]
def _hole_defaults(circles,roi,w,h,small):
    result=[]
    for circle in circles:
        if roi:
            x0,y0,rw,rh=roi; nx=max(0.,min(1.,(circle.x-x0)/max(rw,1))); ny=max(0.,min(1.,(y0+rh-circle.y)/max(rh,1))); hs="слева" if nx<.5 else "справа"; vs="снизу" if ny<.5 else "сверху"; dx=min(nx,1-nx)*w; dy=min(ny,1-ny)*h
        else: hs,dx,vs,dy="справа",20.,"снизу",20.
        if small: dx=small[0]; dy=small[1] if len(small)>1 else small[0]
        result.append((hs,max(0.,dx),vs,max(0.,dy)))
    return result
def _ask(w,h,defaults,dia):
    OUTPUT.mkdir(parents=True,exist_ok=True); token=f"{os.getpid()}_{time.time_ns()}"; request=OUTPUT/f".geometry_{token}_request.json"; response=OUTPUT/f".geometry_{token}_response.json"
    request.write_text(json.dumps({"width":w,"height":h,"defaults":defaults,"diameter":dia},ensure_ascii=False),encoding="utf-8")
    try:
        completed=subprocess.run([sys.executable,str(Path(__file__).with_name("geometry_dialog.py")),str(request),str(response)],check=False)
        if completed.returncode==2: return None
        if completed.returncode!=0 or not response.exists(): raise RuntimeError("Окно размеров завершилось с ошибкой")
        return json.loads(response.read_text(encoding="utf-8"))
    finally: request.unlink(missing_ok=True); response.unlink(missing_ok=True)
def _doc():
    import ezdxf
    doc=ezdxf.new("R12"); doc.header["$INSUNITS"]=4
    for name,color in (("CUT",7),("HOLES",1),("DIM",3),("TEXT",2)):
        if name not in doc.layers: doc.layers.add(name,color=color)
    return doc
def _geometry(model,w,h,specs,dia):
    model.add_polyline2d([(0,0),(w,0),(w,h),(0,h)],close=True,dxfattribs={"layer":"CUT"})
    for s in specs: model.add_circle((s["x"],s["y"]),dia/2,dxfattribs={"layer":"HOLES"})
def _line(m,a,b): m.add_line(a,b,dxfattribs={"layer":"DIM"})
def _text(m,t,p,height=5): m.add_text(t,dxfattribs={"layer":"TEXT","height":height,"insert":p})
def _dimensions(m,w,h,specs,dia):
    off=max(15.,min(w,h)*.05); _line(m,(0,-off),(w,-off)); _line(m,(0,0),(0,-off*1.25)); _line(m,(w,0),(w,-off*1.25)); _text(m,f"WIDTH {w:g} mm",(w*.35,-off*.85)); _line(m,(w+off,0),(w+off,h)); _line(m,(w,0),(w+off*1.25,0)); _line(m,(w,h),(w+off*1.25,h)); _text(m,f"HEIGHT {h:g} mm",(w+off*1.15,h*.45))
    for i,s in enumerate(specs,1):
        x,y=s["x"],s["y"]; _line(m,(0 if s["h_side"]=="слева" else w,y),(x,y)); _line(m,(x,0 if s["v_side"]=="снизу" else h),(x,y)); _text(m,f"H{i}: DIA {dia:g}; {s['h_distance']:g} FROM {s['h_side'].upper()}; {s['v_distance']:g} FROM {s['v_side'].upper()}",(x+dia,y+dia+i*2),max(3.,min(w,h)*.012))
def _validate(path,count,info):
    import ezdxf
    entities=list(ezdxf.readfile(path).modelspace()); cuts=[e for e in entities if e.dxftype()=="POLYLINE" and e.dxf.layer=="CUT"]; circles=[e for e in entities if e.dxftype()=="CIRCLE" and e.dxf.layer=="HOLES"]; dims=[e for e in entities if e.dxf.layer in {"DIM","TEXT"}]
    if len(cuts)!=1 or len(circles)!=count or (info and not dims) or (not info and dims): raise RuntimeError("Проверка DXF не пройдена")
def _write(stem,w,h,specs,dia):
    OUTPUT.mkdir(parents=True,exist_ok=True); clear=OUTPUT/f"{stem}_dxf_clear.dxf"; info=OUTPUT/f"{stem}_dxf_info.dxf"; ct=OUTPUT/f".{stem}_clear.tmp.dxf"; it=OUTPUT/f".{stem}_info.tmp.dxf"
    a=_doc(); _geometry(a.modelspace(),w,h,specs,dia); a.saveas(ct); b=_doc(); _geometry(b.modelspace(),w,h,specs,dia); _dimensions(b.modelspace(),w,h,specs,dia); b.saveas(it); _validate(ct,len(specs),False); _validate(it,len(specs),True); ct.replace(clear); it.replace(info)
def process(source):
    circles,image=holes.detect_holes(source)
    if image is None: raise RuntimeError("Не удалось открыть изображение")
    confirmed=holes.confirm_holes(image,circles,holes.read_diameter(source))
    if confirmed is None: raise holes.ClarificationRequired("Отверстия не подтверждены")
    selected=[circles[i] for i in confirmed["active"] if 0<=i<len(circles)]
    if confirmed["count"]!=len(selected): raise holes.ClarificationRequired("Количество отверстий не совпадает")
    roi=holes._automatic_figure_roi(image) or holes._manual_figure_roi(image); w,h,small=_defaults(_ocr(source),roi); geometry=_ask(w,h,_hole_defaults(selected,roi,w,h,small),confirmed["diameter"])
    if geometry is None: raise holes.ClarificationRequired("Размеры не подтверждены")
    _write(source.stem,geometry["width"],geometry["height"],geometry["holes"],confirmed["diameter"]); DONE.mkdir(parents=True,exist_ok=True); target=DONE/source.name
    if target.exists(): target=DONE/f"{source.stem}_{int(time.time())}{source.suffix}"
    shutil.move(str(source),str(target))
def _lock():
    import fcntl
    handle=(ROOT/".watcher.lock").open("w")
    try: fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError as error: raise RuntimeError("Обработчик уже запущен") from error
    handle.write(str(os.getpid())); handle.flush(); return handle
def main():
    lock=_lock(); INBOX.mkdir(parents=True,exist_ok=True); DONE.mkdir(parents=True,exist_ok=True); OUTPUT.mkdir(parents=True,exist_ok=True); signatures={}; paused=set(); print(f"Слушаю: {INBOX}")
    while True:
        for source in [p for p in INBOX.iterdir() if p.is_file() and p.suffix.lower() in EXTENSIONS]:
            stat=source.stat(); signature=(stat.st_size,stat.st_mtime_ns)
            if source in paused:
                if signatures.get(source)==signature: continue
                paused.remove(source)
            if signatures.get(source)!=signature: signatures[source]=signature; continue
            try: process(source); signatures.pop(source,None); print(f"Готово: {source.name}")
            except holes.ClarificationRequired as error: paused.add(source); print(f"Приостановлено: {error}")
            except Exception as error: paused.add(source); print(f"Ошибка: {source.name}: {error}")
        time.sleep(1)
if __name__=="__main__": main()
