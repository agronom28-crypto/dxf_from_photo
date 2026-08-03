#!/usr/bin/env python3
"""Index factory DXF topologies and match a photographed operator sketch."""
from __future__ import annotations
import argparse, json, math
from pathlib import Path
import cv2, ezdxf, numpy as np
from reference_dxf_pipeline import extract_loops

def resample(points,n=256):
    p=np.asarray(points[:-1] if points[0]==points[-1] else points,dtype=np.float64)
    p=np.vstack([p,p[0]]); seg=np.linalg.norm(np.diff(p,axis=0),axis=1); total=seg.sum()
    if total<=0: raise ValueError("degenerate contour")
    t=np.concatenate([[0],np.cumsum(seg)]); targets=np.linspace(0,total,n,endpoint=False); out=[]
    for q in targets:
        i=min(np.searchsorted(t,q,side="right")-1,len(seg)-1); a=(q-t[i])/max(seg[i],1e-12); out.append(p[i]*(1-a)+p[i+1]*a)
    return np.asarray(out,np.float32)
def normalize(p):
    q=p-p.mean(axis=0); scale=np.sqrt((q*q).sum(axis=1).mean()); return q/max(scale,1e-12)
def descriptor(points):
    p=normalize(resample(points)); hu=cv2.HuMoments(cv2.moments(p.reshape((-1,1,2)))).flatten(); hu=-np.sign(hu)*np.log10(np.abs(hu)+1e-30)
    z=p[:,0]+1j*p[:,1]; fft=np.abs(np.fft.fft(z))[1:33]; fft=fft/max(fft[0],1e-12)
    return {"hu":hu.tolist(),"fourier":fft.tolist(),"aspect":float(np.ptp(p[:,0])/max(np.ptp(p[:,1]),1e-12)),"points":p.tolist()}
def build_index(folder,out):
    items=[]
    for f in sorted(Path(folder).glob("*.dxf")):
        try:
            outer=[x for x in extract_loops(ezdxf.readfile(f)) if x.layer=="CUT"]
            for i,l in enumerate(outer): items.append({"file":f.name,"contour":i,"descriptor":descriptor(l.points),"area":l.area})
        except Exception as e: items.append({"file":f.name,"error":str(e)})
    data={"version":1,"items":items,"usable":sum("descriptor" in x for x in items)}; Path(out).write_text(json.dumps(data,ensure_ascii=False),encoding="utf-8"); return data
def sketch_contour(image_path):
    img=cv2.imread(str(image_path))
    if img is None: raise FileNotFoundError(image_path)
    gray=cv2.cvtColor(img,cv2.COLOR_BGR2GRAY); gray=cv2.GaussianBlur(gray,(5,5),0); bw=cv2.adaptiveThreshold(gray,255,cv2.ADAPTIVE_THRESH_GAUSSIAN_C,cv2.THRESH_BINARY_INV,51,11); bw=cv2.morphologyEx(bw,cv2.MORPH_CLOSE,np.ones((5,5),np.uint8),iterations=2)
    cnts,_=cv2.findContours(bw,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_NONE)
    if not cnts: raise ValueError("no contour found")
    h,w=gray.shape; valid=[c for c in cnts if .01*w*h<cv2.contourArea(c)<.95*w*h]; c=max(valid or cnts,key=cv2.contourArea); c=cv2.approxPolyDP(c,.002*cv2.arcLength(c,True),True); pts=[(float(x),float(y)) for [[x,y]] in c]; pts.append(pts[0]); return pts
def score(a,b):
    ah=np.asarray(a["hu"]); bh=np.asarray(b["hu"]); af=np.asarray(a["fourier"]); bf=np.asarray(b["fourier"])
    return float(np.mean(np.abs(ah-bh))+.75*np.mean(np.abs(af-bf))+.2*abs(math.log(max(a["aspect"],1e-9)/max(b["aspect"],1e-9))))
def match(image,index_path,top=5):
    d=descriptor(sketch_contour(image)); idx=json.loads(Path(index_path).read_text()); rows=[]
    for x in idx["items"]:
        if "descriptor" in x: rows.append({"file":x["file"],"contour":x["contour"],"score":score(d,x["descriptor"])})
    rows.sort(key=lambda x:x["score"]); return {"image":str(image),"status":"operator_review_required","candidates":rows[:top]}
def main():
    ap=argparse.ArgumentParser(); sub=ap.add_subparsers(dest="cmd",required=True); a=sub.add_parser("index"); a.add_argument("folder"); a.add_argument("output"); m=sub.add_parser("match"); m.add_argument("image"); m.add_argument("index"); m.add_argument("--output",default="shape_candidates.json"); m.add_argument("--top",type=int,default=5); x=ap.parse_args()
    if x.cmd=="index": print(json.dumps({k:v for k,v in build_index(x.folder,x.output).items() if k!="items"},indent=2))
    else:
        result=match(x.image,x.index,x.top); Path(x.output).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8"); print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=="__main__": main()
