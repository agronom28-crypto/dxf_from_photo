#!/usr/bin/env python3
"""Фоновая папка: графический документ -> чистый и информационный DXF."""
from __future__ import annotations
import argparse,hashlib,json,os,shutil,signal,subprocess,sys,tempfile,time
from pathlib import Path
from hole_diameter_clarification import ClarificationRequired,add_to_info_dxf,resolve
INBOX_NAME="новые фотографии"; OUTPUT_NAME="DXF"
SUPPORTED={".jpg",".jpeg",".png",".bmp",".tif",".tiff",".webp",".pdf"}
DIMENSION_TYPES={"DIMENSION","TEXT","MTEXT","LEADER","MLEADER","TOLERANCE","ATTDEF","ATTRIB"}
DIMENSION_LAYER_WORDS=("dim","dimension","размер","text","текст","annotation","штамп")
def file_hash(path):
    value=hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda:stream.read(1024*1024),b""): value.update(block)
    return value.hexdigest()
def atomic_copy(source,target):
    target.parent.mkdir(parents=True,exist_ok=True); temporary=target.with_suffix(target.suffix+".tmp"); shutil.copy2(source,temporary); os.replace(temporary,target)
def load_state(path):
    try:return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError,json.JSONDecodeError):return {"version":1,"files":{}}
def save_state(path,state):
    temporary=path.with_suffix(".tmp"); temporary.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding="utf-8"); os.replace(temporary,path)
def stable(path,seen,seconds):
    stat=path.stat(); signature=(stat.st_size,stat.st_mtime_ns); key=str(path.resolve()); now=time.monotonic(); previous=seen.get(key)
    if not previous or previous[:2]!=signature:seen[key]=(signature[0],signature[1],now);return False
    return now-previous[2]>=seconds
def classify_outputs(files):
    files=list(files); information=next((x for x in files if any(word in x.stem.lower() for word in ("dimensioned","info","размер"))),None); clear=next((x for x in files if any(word in x.stem.lower() for word in ("cnc","clear","draft"))),None)
    if len(files)==1:information=files[0]
    elif files:information=information or files[-1];clear=clear or next((x for x in files if x!=information),None)
    return clear,information
def derive_clear(information_path,clear_path):
    try:import ezdxf
    except ImportError as error:raise RuntimeError("Для создания чистого DXF требуется ezdxf") from error
    document=ezdxf.readfile(information_path); model=document.modelspace()
    for entity in list(model):
        layer=str(entity.dxf.get("layer","0")).lower()
        if entity.dxftype() in DIMENSION_TYPES or any(word in layer for word in DIMENSION_LAYER_WORDS):model.delete_entity(entity)
    document.saveas(clear_path)
def default_processor(source,workdir):
    root=Path(__file__).resolve().parents[1]; scripts=[root/"src/auto_pipeline.py",root/"src/photo_to_draft_dxf.py"]; errors=[]
    for script in scripts:
        if not script.exists():continue
        commands=[[sys.executable,str(script),str(source),"--output-dir",str(workdir)],[sys.executable,str(script),str(source),"--output",str(workdir/source.stem)],[sys.executable,str(script),str(source),str(workdir/source.stem)]]
        for command in commands:
            before={item.resolve() for item in workdir.rglob("*.dxf")}; result=subprocess.run(command,cwd=root,text=True,capture_output=True,timeout=600); files=[item for item in workdir.rglob("*.dxf") if item.resolve() not in before]
            if result.returncode==0 and files:return files
            errors.append({"команда":command,"код":result.returncode,"ошибка":result.stderr[-2000:]})
    raise RuntimeError("Обработчик не создал DXF: "+json.dumps(errors,ensure_ascii=False))
class InboxWatcher:
    def __init__(self,root=".",interval=1.0,stable_seconds=2.0,processor=None):
        self.root=Path(root).resolve();self.inbox=self.root/INBOX_NAME;self.output=self.root/OUTPUT_NAME;self.state_path=self.output/".processing_state.json";self.interval=interval;self.stable_seconds=stable_seconds;self.processor=processor or default_processor;self.seen={};self.running=True;self.inbox.mkdir(parents=True,exist_ok=True);self.output.mkdir(parents=True,exist_ok=True);self.state=load_state(self.state_path)
    def candidates(self):return sorted(item for item in self.inbox.iterdir() if item.is_file() and item.suffix.lower() in SUPPORTED and not item.name.startswith("."))
    def process(self,source):
        digest=file_hash(source);key=str(source.relative_to(self.root));previous=self.state["files"].get(key,{})
        answer=self.output/f"{source.stem}_hole_diameter.json"
        if previous.get("sha256")==digest and previous.get("status")=="done":return False
        if previous.get("sha256")==digest and previous.get("status")=="awaiting_hole_diameter" and not answer.exists():return False
        self.state["files"][key]={"sha256":digest,"status":"processing","started_at":time.time()};save_state(self.state_path,self.state)
        try:
            hole_spec=resolve(source,self.output)
            with tempfile.TemporaryDirectory(prefix="dxf-job-") as directory:
                work=Path(directory);produced=self.processor(source,work);clear,information=classify_outputs(produced)
                if information is None:raise RuntimeError("Обработчик не создал информационный DXF")
                if clear is None:clear=work/(source.stem+"_derived_clear.dxf");derive_clear(information,clear)
                if hole_spec is not None:add_to_info_dxf(information,hole_spec)
                clear_target=self.output/f"{source.stem}_dxf_clear.dxf";info_target=self.output/f"{source.stem}_dxf_info.dxf";atomic_copy(clear,clear_target);atomic_copy(information,info_target)
            self.state["files"][key]={"sha256":digest,"status":"done","finished_at":time.time(),"clear":clear_target.name,"info":info_target.name};save_state(self.state_path,self.state);return True
        except ClarificationRequired as error:
            self.state["files"][key]={"source":str(source),"sha256":digest,"status":"awaiting_hole_diameter","message":str(error),"updated_at":time.time()};save_state(self.state_path,self.state);return False
        except Exception as error:
            report={"source":str(source),"sha256":digest,"status":"error","message":str(error),"failed_at":time.time()};(self.output/f"{source.stem}_error.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8");self.state["files"][key]=report;save_state(self.state_path,self.state);return False
    def scan(self,force_stable=False):
        total=0
        for source in self.candidates():
            if force_stable or stable(source,self.seen,self.stable_seconds):total+=int(self.process(source))
        return total
    def run(self):
        print(f"Слушаю: {self.inbox}\nРезультаты: {self.output}",flush=True)
        while self.running:self.scan();time.sleep(self.interval)
def main():
    parser=argparse.ArgumentParser(description="Фоновая обработка фотографий в DXF");parser.add_argument("--root",default=".");parser.add_argument("--interval",type=float,default=1.0);parser.add_argument("--stable-seconds",type=float,default=2.0);parser.add_argument("--once",action="store_true");arguments=parser.parse_args();watcher=InboxWatcher(arguments.root,arguments.interval,arguments.stable_seconds)
    if arguments.once:watcher.scan(force_stable=True);return
    def stop(*_):watcher.running=False
    signal.signal(signal.SIGINT,stop);signal.signal(signal.SIGTERM,stop);watcher.run()
if __name__=="__main__":main()
