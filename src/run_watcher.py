from __future__ import annotations
import json, os, re, subprocess, sys, time
from pathlib import Path
import ezdxf
import hole_diameter_clarification as holes
from contour_geometry import extract_outline
from production_validator import ProductionValidator
INBOX=Path.home()/"Desktop"/"DXF_Inbox"; OUTBOX=Path.home()/"Desktop"/"DXF_Outbox"; SUPPORTED={".jpg",".jpeg",".png",".tif",".tiff",".bmp",".webp"}; POLL=1.0

def _atomic_json(path,payload):
 tmp=path.with_suffix(path.suffix+".tmp");tmp.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8");tmp.replace(path)
def _state():
 path=OUTBOX/".processed_state.json"
 try:return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
 except Exception:return {}
def _stable(path):
 try:a=path.stat();time.sleep(.35);b=path.stat();return (a.st_size,a.st_mtime_ns)==(b.st_size,b.st_mtime_ns)
 except FileNotFoundError:return False
def _invoke_helper(name,args,response):
 response.unlink(missing_ok=True);cmd=[sys.executable,str(Path(__file__).with_name(name)),*map(str,args),str(response)];env=dict(os.environ);env["PYTHONPATH"]=str(Path(__file__).parent)+os.pathsep+env.get("PYTHONPATH","");result=subprocess.run(cmd,env=env)
 if result.returncode!=0 or not response.exists():raise RuntimeError(f"Диалог {name} отменён или завершился с ошибкой")
 return json.loads(response.read_text(encoding="utf-8"))
def _select_roi(source):return _invoke_helper("roi_dialog.py",[source],OUTBOX/".roi_response.json")
def _confirm_holes(source,roi):return _invoke_helper("hole_confirmation_dialog.py",[source,json.dumps(list(roi))],OUTBOX/".hole_response.json")
def _manual(source,defaults):return _invoke_helper("geometry_dialog.py",[source,json.dumps(defaults,ensure_ascii=False)],OUTBOX/".geometry_response.json")
def _parse_dims(source):
 candidates=[]
 for path in (source.with_name(source.stem+"_ocr_dimensions.json"),source.with_suffix(".json")):
  if path.exists():
   try:
    data=json.loads(path.read_text(encoding="utf-8"));candidates.extend(float(x) for x in data.get("dimensions",[]) if float(x)>0)
   except Exception:pass
 try:
  text=holes._ocr_text(source);candidates.extend(float(x.replace(",",".")) for x in re.findall(r"(?<![A-Za-z])\d+(?:[.,]\d+)?",text))
 except Exception:pass
 vals=sorted({x for x in candidates if 10<=x<=100000},reverse=True);return (vals[0],vals[1]) if len(vals)>=2 else (None,None)
def _hole_defaults(circles,bbox,w,h):
 bx,by,bw,bh=map(float,bbox);out=[]
 for circle in circles:
  nx=(float(circle["x"])-bx)/max(1.0,bw);ny=1.0-(float(circle["y"])-by)/max(1.0,bh)
  if -.03<=nx<=1.03 and -.03<=ny<=1.03:out.append({"x":round(min(1,max(0,nx))*w,3),"y":round(min(1,max(0,ny))*h,3)})
 return out
def _defaults(source,confirmed,outline):
 width,height=_parse_dims(source);width=width or 1040.0;height=height or 710.0;diameter=float(confirmed.get("diameter") or holes.read_diameter(source) or 10.0);specs=_hole_defaults(confirmed.get("circles",[]),outline["bbox"],width,height);count=int(confirmed.get("count",len(specs)));specs=specs[:count]
 while len(specs)<count:
  i=len(specs);specs.append({"x":round(width*(i+1)/(count+1),3),"y":round(height/2,3)})
 return {"width":width,"height":height,"count":count,"diameter":diameter,"holes":specs}
def _geometry(model,width,height,specs,diameter,outline):
 points=[(float(x)*width,float(y)*height) for x,y in outline.get("points",[])];points=points if len(points)>=4 else [(0,0),(width,0),(width,height),(0,height)];model.add_lwpolyline(points,close=True,dxfattribs={"layer":"CUT"})
 for p in specs:model.add_circle((p["x"],p["y"]),diameter/2,dxfattribs={"layer":"HOLES"})
def _dim_horizontal(msp,p1,p2,base,text,style):
 x1,y1=p1;x2,y2=p2;off=base-y1;msp.add_line((x1,y1),(x1,base),dxfattribs={"layer":"DIM"});msp.add_line((x2,y2),(x2,base),dxfattribs={"layer":"DIM"});msp.add_linear_dim(base=(0,off),p1=p1,p2=p2,angle=0,text=text,dimstyle=style,dxfattribs={"layer":"DIM"}).render()
def _dim_vertical(msp,p1,p2,base,text,style):
 x1,y1=p1;x2,y2=p2;off=base-x1;msp.add_line((x1,y1),(base,y1),dxfattribs={"layer":"DIM"});msp.add_line((x2,y2),(base,y2),dxfattribs={"layer":"DIM"});msp.add_linear_dim(base=(off,0),p1=p1,p2=p2,angle=90,text=text,dimstyle=style,dxfattribs={"layer":"DIM"}).render()
def _write(path,width,height,specs,diameter,outline,info):
 doc=ezdxf.new("R2010");doc.header["$INSUNITS"]=4;doc.layers.new("CUT",dxfattribs={"color":7});doc.layers.new("HOLES",dxfattribs={"color":1});doc.layers.new("DIM",dxfattribs={"color":3});doc.layers.new("TEXT",dxfattribs={"color":2});msp=doc.modelspace();_geometry(msp,width,height,specs,diameter,outline)
 if info:
  style="DXF_INFO";doc.dimstyles.new(style,dxfattribs={"dimtxt":max(3,min(width,height)*.025),"dimasz":max(2,min(width,height)*.015),"dimexe":1.5,"dimexo":1.0,"dimgap":1.0});off=max(25,min(width,height)*.12);_dim_horizontal(msp,(0,0),(width,0),-off,f"{width:g}",style);_dim_vertical(msp,(0,0),(0,height),-off,f"{height:g}",style)
  for i,p in enumerate(specs,1):msp.add_text(f"H{i}: X={p['x']:g} Y={p['y']:g} DIA{diameter:g}",dxfattribs={"layer":"TEXT","height":max(3,min(width,height)*.018),"insert":(p["x"]+diameter,p["y"]+diameter)})
 tmp=path.with_suffix(".tmp.dxf");doc.saveas(tmp);tmp.replace(path)
def _validate(path,count):
 result=ProductionValidator().validate_dxf(path,expected_counts={"CUT":1,"HOLES":count},require_mm_units=True);return {"valid":result.valid,"summary":result.summary,"errors":result.errors,"warnings":result.warnings,"metrics":result.metrics}
def process(source):
 roi_payload=_select_roi(source);roi=tuple(map(int,roi_payload["roi"]));outline=extract_outline(source,roi);confirmed=_confirm_holes(source,roi);defaults=_defaults(source,confirmed,outline);answer=_manual(source,defaults);width=float(answer["width"]);height=float(answer["height"]);count=int(answer["count"]);diameter=float(answer["diameter"]);specs=list(answer["holes"]);base=OUTBOX/source.stem;clear=base.with_name(base.name+"_dxf_clear.dxf");info=base.with_name(base.name+"_dxf_info.dxf");_write(clear,width,height,specs,diameter,outline,False);_write(info,width,height,specs,diameter,outline,True);report={"source":str(source),"roi":roi,"outline_confidence":outline["confidence"],"outline_vertices":len(outline["points"]),"width":width,"height":height,"count":count,"diameter":diameter,"clear":_validate(clear,count),"info":_validate(info,count)};_atomic_json(base.with_name(base.name+"_report.json"),report);print(f"Готово: {clear.name}, {info.name}",flush=True)
def main():
 INBOX.mkdir(parents=True,exist_ok=True);OUTBOX.mkdir(parents=True,exist_ok=True);state=_state();print(f"Наблюдение: {INBOX}",flush=True)
 while True:
  for source in sorted(INBOX.iterdir()):
   if not source.is_file() or source.suffix.lower() not in SUPPORTED:continue
   try:stamp=f"{source.stat().st_mtime_ns}:{source.stat().st_size}"
   except FileNotFoundError:continue
   key=str(source.resolve())
   if state.get(key)==stamp or not _stable(source):continue
   try:process(source);state[key]=stamp;_atomic_json(OUTBOX/".processed_state.json",state)
   except Exception as exc:print(f"Ошибка {source.name}: {exc}",file=sys.stderr,flush=True)
  time.sleep(POLL)
if __name__=="__main__":main()
