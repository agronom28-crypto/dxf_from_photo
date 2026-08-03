#!/usr/bin/env python3
"""Background inbox: graphic document -> clear and information DXF files."""
from __future__ import annotations
import argparse, hashlib, json, os, shutil, signal, subprocess, sys, tempfile, time
from pathlib import Path

INBOX_NAME="новые фотографии"
OUTPUT_NAME="DXF"
SUPPORTED={".jpg",".jpeg",".png",".bmp",".tif",".tiff",".webp",".pdf"}
DIMENSION_TYPES={"DIMENSION","TEXT","MTEXT","LEADER","MLEADER","TOLERANCE","ATTDEF","ATTRIB"}
DIMENSION_LAYER_WORDS=("dim","dimension","размер","text","текст","annotation","штамп")

def file_hash(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda:f.read(1024*1024),b""): h.update(block)
    return h.hexdigest()
def atomic_copy(src,dst):
    dst.parent.mkdir(parents=True,exist_ok=True); tmp=dst.with_suffix(dst.suffix+".tmp"); shutil.copy2(src,tmp); os.replace(tmp,dst)
def load_state(path):
    try: return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError,json.JSONDecodeError): return {"version":1,"files":{}}
def save_state(path,state):
    tmp=path.with_suffix(".tmp"); tmp.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding="utf-8"); os.replace(tmp,path)
def stable(path,seen,seconds):
    key=str(path.resolve()); stat=path.stat(); signature=(stat.st_size,stat.st_mtime_ns); now=time.monotonic(); old=seen.get(key)
    if not old or old[:2]!=signature: seen[key]=(signature[0],signature[1],now); return False
    return now-old[2]>=seconds

def classify_outputs(files):
    files=list(files); info=next((x for x in files if any(w in x.stem.lower() for w in ("dimensioned","info","размер"))),None); clear=next((x for x in files if any(w in x.stem.lower() for w in ("cnc","clear","draft"))),None)
    if len(files)==1: info=files[0]
    elif files:
        info=info or files[-1]; clear=clear or next((x for x in files if x!=info),None)
    return clear,info

def derive_clear(info_path,clear_path):
    try: import ezdxf
    except ImportError as exc: raise RuntimeError("ezdxf is required to derive clear DXF") from exc
    doc=ezdxf.readfile(info_path); msp=doc.modelspace()
    for entity in list(msp):
        layer=str(entity.dxf.get("layer","0")).lower()
        if entity.dxftype() in DIMENSION_TYPES or any(word in layer for word in DIMENSION_LAYER_WORDS): msp.delete_entity(entity)
    doc.saveas(clear_path)

def default_processor(source,workdir):
    root=Path(__file__).resolve().parents[1]; scripts=[root/"src/auto_pipeline.py",root/"src/photo_to_draft_dxf.py"]
    variants=lambda script:[[sys.executable,str(script),str(source),"--output-dir",str(workdir)],[sys.executable,str(script),str(source),"--output",str(workdir/source.stem)],[sys.executable,str(script),str(source),str(workdir/source.stem)]]
    errors=[]
    for script in scripts:
        if not script.exists(): continue
        for command in variants(script):
            before={x.resolve() for x in workdir.rglob("*.dxf")}; run=subprocess.run(command,cwd=root,text=True,capture_output=True,timeout=600); files=[x for x in workdir.rglob("*.dxf") if x.resolve() not in before]
            if run.returncode==0 and files: return files
            errors.append({"command":command,"returncode":run.returncode,"stderr":run.stderr[-2000:]})
    raise RuntimeError("No existing processor produced DXF: "+json.dumps(errors,ensure_ascii=False))

class InboxWatcher:
    def __init__(self,root=".",interval=1.0,stable_seconds=2.0,processor=None):
        self.root=Path(root).resolve(); self.inbox=self.root/INBOX_NAME; self.output=self.root/OUTPUT_NAME; self.state_path=self.output/".processing_state.json"; self.interval=interval; self.stable_seconds=stable_seconds; self.processor=processor or default_processor; self.seen={}; self.running=True; self.inbox.mkdir(parents=True,exist_ok=True); self.output.mkdir(parents=True,exist_ok=True); self.state=load_state(self.state_path)
    def candidates(self): return sorted(x for x in self.inbox.iterdir() if x.is_file() and x.suffix.lower() in SUPPORTED and not x.name.startswith("."))
    def process(self,source):
        digest=file_hash(source); key=str(source.relative_to(self.root)); previous=self.state["files"].get(key,{})
        if previous.get("sha256")==digest and previous.get("status")=="done": return False
        self.state["files"][key]={"sha256":digest,"status":"processing","started_at":time.time()}; save_state(self.state_path,self.state)
        try:
            with tempfile.TemporaryDirectory(prefix="dxf-job-") as td:
                work=Path(td); produced=self.processor(source,work); clear,info=classify_outputs(produced)
                if info is None: raise RuntimeError("processor did not create an information DXF")
                if clear is None: clear=work/(source.stem+"_derived_clear.dxf"); derive_clear(info,clear)
                clear_dst=self.output/f"{source.stem}_dxf_clear.dxf"; info_dst=self.output/f"{source.stem}_dxf_info.dxf"; atomic_copy(clear,clear_dst); atomic_copy(info,info_dst)
            self.state["files"][key]={"sha256":digest,"status":"done","finished_at":time.time(),"clear":clear_dst.name,"info":info_dst.name}; save_state(self.state_path,self.state); return True
        except Exception as exc:
            error={"source":str(source),"sha256":digest,"status":"error","message":str(exc),"failed_at":time.time()}; (self.output/f"{source.stem}_error.json").write_text(json.dumps(error,ensure_ascii=False,indent=2),encoding="utf-8"); self.state["files"][key]=error; save_state(self.state_path,self.state); return False
    def scan(self,force_stable=False):
        count=0
        for source in self.candidates():
            if force_stable or stable(source,self.seen,self.stable_seconds): count+=int(self.process(source))
        return count
    def run(self):
        print(f"Слушаю: {self.inbox}\nРезультаты: {self.output}",flush=True)
        while self.running: self.scan(); time.sleep(self.interval)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--root",default="."); ap.add_argument("--interval",type=float,default=1.0); ap.add_argument("--stable-seconds",type=float,default=2.0); ap.add_argument("--once",action="store_true"); a=ap.parse_args(); watcher=InboxWatcher(a.root,a.interval,a.stable_seconds)
    if a.once: watcher.scan(force_stable=True); return
    def stop(*_): watcher.running=False
    signal.signal(signal.SIGINT,stop); signal.signal(signal.SIGTERM,stop); watcher.run()
if __name__=="__main__": main()
