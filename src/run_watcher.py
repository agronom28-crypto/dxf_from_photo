from __future__ import annotations
import json,os,re,shutil,subprocess,sys,time
from pathlib import Path
from types import SimpleNamespace
import hole_diameter_clarification as holes
ROOT=Path(__file__).resolve().parent.parent;INBOX=ROOT/"новые фотографии";OUTPUT=ROOT/"DXF";DONE=INBOX/"_done"
EXTENSIONS={".png",".jpg",".jpeg",".tif",".tiff",".bmp",".heic"};NUMBER=re.compile(r"(?<!\d)(\d+(?:[.,]\d+)?)(?!\d)")
def _ocr(source,roi):
    try:
        import cv2,pytesseract
        image=cv2.imread(str(source))
        if image is None:return []
        x,y,w,h=map(int,roi);crop=image[y:y+h,x:x+w];values=[]
        rotations=(crop,cv2.rotate(crop,cv2.ROTATE_90_CLOCKWISE),cv2.rotate(crop,cv2.ROTATE_90_COUNTERCLOCKWISE))
        for rotated in rotations:
            gray=cv2.cvtColor(rotated,cv2.COLOR_BGR2GRAY);gray=cv2.resize(gray,None,fx=2.5,fy=2.5,interpolation=cv2.INTER_CUBIC);gray=cv2.threshold(gray,0,255,cv2.THRESH_BINARY+cv2.THRESH_OTSU)[1]
            for psm in (6,11,12):
                text=pytesseract.image_to_string(gray,config=f"--psm {psm} -c tessedit_char_whitelist=0123456789.,",lang="eng")
                values.extend(float(v.replace(",",".")) for v in NUMBER.findall(text))
        return values
    except (ImportError,RuntimeError,ValueError):return []
def _defaults(numbers,roi):
    large=sorted({v for v in numbers if 50<=v<=10000},reverse=True)
    if len(large)>=2:
        a,b=large[:2];portrait=roi[3]>=roi[2];w,h=((min(a,b),max(a,b)) if portrait else (max(a,b),min(a,b)))
    else:w,h=395.,830.
    return w,h
def _hole_defaults(circles,roi,w,h):
    x0,y0,rw,rh=roi;result=[]
    for circle in circles:
        nx=max(0.,min(1.,(circle.x-x0)/max(rw,1)));ny=max(0.,min(1.,(y0+rh-circle.y)/max(rh,1)));hs="слева" if nx<.5 else "справа";vs="снизу" if ny<.5 else "сверху";result.append((hs,min(nx,1-nx)*w,vs,min(ny,1-ny)*h))
    return result
def _run(script,args,response,message):
    done=subprocess.run([sys.executable,str(Path(__file__).with_name(script)),*map(str,args),str(response)],check=False)
    if done.returncode==2:return None
    if done.returncode!=0 or not response.exists():raise RuntimeError(message)
    return json.loads(response.read_text(encoding="utf-8"))
def _select_roi(source):
    OUTPUT.mkdir(parents=True,exist_ok=True);response=OUTPUT/f".roi_{os.getpid()}_{time.time_ns()}.json"
    try:return _run("roi_dialog.py",[source],response,"Выбор области завершился с ошибкой")
    finally:response.unlink(missing_ok=True)
def _confirm(source,roi):
    response=OUTPUT/f".holes_{os.getpid()}_{time.time_ns()}.json"
    try:return _run("hole_confirmation_dialog.py",[source,json.dumps(roi)],response,"Подтверждение отверстий завершилось с ошибкой")
    finally:response.unlink(missing_ok=True)
def _ask(w,h,defaults,dia):
    token=f"{os.getpid()}_{time.time_ns()}";request=OUTPUT/f".geometry_{token}_request.json";response=OUTPUT/f".geometry_{token}_response.json";request.write_text(json.dumps({"width":w,"height":h,"defaults":defaults,"diameter":dia},ensure_ascii=False),encoding="utf-8")
    try:return _run("geometry_dialog.py",[request],response,"Окно размеров завершилось с ошибкой")
    finally:request.unlink(missing_ok=True);response.unlink(missing_ok=True)
def _doc():
    import ezdxf
    doc=ezdxf.new("R12");doc.header["$INSUNITS"]=4
    for name,color in (("CUT",7),("HOLES",1),("DIM",3),("TEXT",2)):
        if name not in doc.layers:doc.layers.add(name,color=color)
    return doc
def _geometry(model,w,h,specs,dia):
    model.add_polyline2d([(0,0),(w,0),(w,h),(0,h)],close=True,dxfattribs={"layer":"CUT"})
    for spec in specs:model.add_circle((spec["x"],spec["y"]),dia/2,dxfattribs={"layer":"HOLES"})
def _line(model,a,b):model.add_line(a,b,dxfattribs={"layer":"DIM"})
def _text(model,text,point,height):model.add_text(text,dxfattribs={"layer":"TEXT","height":height,"insert":point})
def _dimensions(model,w,h,specs,dia):
    off=max(25.,min(w,h)*.08);gap=max(8.,off*.3);size=max(3.,min(w,h)*.012);bottom=-off;right=w+off
    _line(model,(0,bottom),(w,bottom));_line(model,(0,bottom-gap),(0,bottom+gap));_line(model,(w,bottom-gap),(w,bottom+gap));_text(model,f"WIDTH {w:g} mm",(w*.35,bottom-gap-size),size)
    _line(model,(right,0),(right,h));_line(model,(right-gap,0),(right+gap,0));_line(model,(right-gap,h),(right+gap,h));_text(model,f"HEIGHT {h:g} mm",(right+gap,h*.45),size)
    px=w+off*2.2;py=h;_text(model,f"PART {w:g} x {h:g} mm",(px,py),size);_text(model,f"HOLES {len(specs)}; DIA {dia:g} mm",(px,py-size*1.8),size)
    for i,spec in enumerate(specs,1):_text(model,f"H{i}: {spec['h_distance']:g} FROM {spec['h_side'].upper()}; {spec['v_distance']:g} FROM {spec['v_side'].upper()}",(px,py-size*(3.6+i*1.8)),size)
def _validate(path,count,info,w,h):
    import ezdxf
    entities=list(ezdxf.readfile(path).modelspace());cuts=[e for e in entities if e.dxftype()=="POLYLINE" and e.dxf.layer=="CUT"];circles=[e for e in entities if e.dxftype()=="CIRCLE" and e.dxf.layer=="HOLES"];service=[e for e in entities if e.dxf.layer in {"DIM","TEXT"}]
    if len(cuts)!=1 or len(circles)!=count or (info and not service) or (not info and service):raise RuntimeError("Проверка DXF не пройдена")
    if info:
        for entity in service:
            points=(entity.dxf.start,entity.dxf.end) if entity.dxftype()=="LINE" else ((entity.dxf.insert,) if entity.dxftype()=="TEXT" else ())
            if any(0<=float(p.x)<=w and 0<=float(p.y)<=h for p in points):raise RuntimeError("Служебная информация касается контура")
def _write(stem,w,h,specs,dia):
    OUTPUT.mkdir(parents=True,exist_ok=True);clear=OUTPUT/f"{stem}_dxf_clear.dxf";info=OUTPUT/f"{stem}_dxf_info.dxf";ct=OUTPUT/f".{stem}_clear.tmp.dxf";it=OUTPUT/f".{stem}_info.tmp.dxf"
    a=_doc();_geometry(a.modelspace(),w,h,specs,dia);a.saveas(ct);b=_doc();_geometry(b.modelspace(),w,h,specs,dia);_dimensions(b.modelspace(),w,h,specs,dia);b.saveas(it);_validate(ct,len(specs),False,w,h);_validate(it,len(specs),True,w,h);ct.replace(clear);it.replace(info)
def process(source):
    selection=_select_roi(source)
    if selection is None:raise holes.ClarificationRequired("Область детали не подтверждена")
    roi=selection["roi"];confirmed=_confirm(source,roi)
    if confirmed is None:raise holes.ClarificationRequired("Отверстия не подтверждены")
    circles=[SimpleNamespace(x=item["x"],y=item["y"]) for item in confirmed["circles"]];numbers=_ocr(source,roi);print(f"OCR {source.name}: {numbers}");w,h=_defaults(numbers,roi);geometry=_ask(w,h,_hole_defaults(circles,roi,w,h),confirmed["diameter"])
    if geometry is None:raise holes.ClarificationRequired("Размеры не подтверждены")
    _write(source.stem,geometry["width"],geometry["height"],geometry["holes"],confirmed["diameter"]);DONE.mkdir(parents=True,exist_ok=True);target=DONE/source.name
    if target.exists():target=DONE/f"{source.stem}_{int(time.time())}{source.suffix}"
    shutil.move(str(source),str(target))
def _lock():
    import fcntl
    handle=(ROOT/".watcher.lock").open("w")
    try:fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError as error:raise RuntimeError("Обработчик уже запущен") from error
    handle.write(str(os.getpid()));handle.flush();return handle
def main():
    lock=_lock();INBOX.mkdir(parents=True,exist_ok=True);DONE.mkdir(parents=True,exist_ok=True);OUTPUT.mkdir(parents=True,exist_ok=True);signatures={};paused=set();print(f"Слушаю: {INBOX}")
    while True:
        for source in [p for p in INBOX.iterdir() if p.is_file() and p.suffix.lower() in EXTENSIONS]:
            stat=source.stat();signature=(stat.st_size,stat.st_mtime_ns)
            if source in paused:
                if signatures.get(source)==signature:continue
                paused.remove(source)
            if signatures.get(source)!=signature:signatures[source]=signature;continue
            try:process(source);signatures.pop(source,None);print(f"Готово: {source.name}")
            except holes.ClarificationRequired as error:paused.add(source);print(f"Приостановлено: {error}")
            except Exception as error:paused.add(source);print(f"Ошибка: {source.name}: {error}")
        time.sleep(1)
if __name__=="__main__":main()
