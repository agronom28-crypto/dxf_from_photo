#!/usr/bin/env python3
"""Convert arbitrary factory DXF geometry into clean CNC and dimensioned DXF files."""
from __future__ import annotations
import argparse, json, math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
try:
    import ezdxf
    from ezdxf import path as ezpath
except ImportError as exc:
    raise SystemExit("Install: pip install -r requirements-reference.txt") from exc
Point=tuple[float,float]
SUPPORTED={"LINE","ARC","CIRCLE","LWPOLYLINE","POLYLINE","SPLINE","ELLIPSE"}
EXCLUDED_LAYER_WORDS=("dim","размер","text","текст","annotation","штамп","axis","center")
@dataclass
class Loop:
    points:list[Point]; source_types:set[str]; area:float=0.0; layer:str="CUT"
    def __post_init__(self):
        if self.points and self.points[0]!=self.points[-1]: self.points.append(self.points[0])
        self.area=abs(signed_area(self.points))
def signed_area(p): return sum(x1*y2-x2*y1 for (x1,y1),(x2,y2) in zip(p,p[1:]))/2
def dist(a,b): return math.hypot(a[0]-b[0],a[1]-b[1])
def clean_points(points,tol):
    out=[]
    for p in points:
        p=(float(p[0]),float(p[1]))
        if not out or dist(out[-1],p)>tol: out.append(p)
    return out
def entity_points(e,flatten):
    if e.dxftype()=="LINE": return [(e.dxf.start.x,e.dxf.start.y),(e.dxf.end.x,e.dxf.end.y)],False
    p=ezpath.make_path(e); pts=[(v.x,v.y) for v in p.flattening(max(flatten,1e-4))]
    return pts,e.dxftype()=="CIRCLE" or bool(getattr(e,"closed",False)) or bool(getattr(p,"is_closed",False))
def join_open_chains(chains,tol):
    result=[]
    while chains:
        pts,types=chains.pop(); changed=True
        while changed:
            changed=False
            for i,(other,otypes) in enumerate(chains):
                if dist(pts[-1],other[0])<=tol: pts+=other[1:]
                elif dist(pts[-1],other[-1])<=tol: pts+=list(reversed(other[:-1]))
                elif dist(pts[0],other[-1])<=tol: pts=other[:-1]+pts
                elif dist(pts[0],other[0])<=tol: pts=list(reversed(other[1:]))+pts
                else: continue
                types|=otypes; chains.pop(i); changed=True; break
        result.append((pts,types))
    return result
def point_in_polygon(p,poly):
    x,y=p; inside=False
    for (x1,y1),(x2,y2) in zip(poly,poly[1:]):
        if (y1>y)!=(y2>y) and x<(x2-x1)*(y-y1)/(y2-y1)+x1: inside=not inside
    return inside
def centroid(poly):
    q=poly[:-1] if poly and poly[0]==poly[-1] else poly
    return sum(x for x,_ in q)/len(q),sum(y for _,y in q)/len(q)
def extract_loops(doc,flatten=.05,join_tol=.1,min_area=1.0,layers=None):
    closed=[]; opens=[]
    for e in doc.modelspace():
        typ=e.dxftype(); layer=str(e.dxf.get("layer","0"))
        if typ not in SUPPORTED or (layers and layer not in layers) or (not layers and any(w in layer.lower() for w in EXCLUDED_LAYER_WORDS)): continue
        try: pts,is_closed=entity_points(e,flatten)
        except Exception: continue
        pts=clean_points(pts,join_tol/10)
        if len(pts)<2: continue
        if is_closed:
            if dist(pts[0],pts[-1])>join_tol: pts.append(pts[0])
            closed.append((pts,{typ}))
        else: opens.append((pts,{typ}))
    for pts,types in join_open_chains(opens,join_tol):
        if len(pts)>=3 and dist(pts[0],pts[-1])<=join_tol: pts[-1]=pts[0]; closed.append((pts,types))
    loops=[Loop(p,t) for p,t in closed]; loops=[l for l in loops if l.area>=min_area]; loops.sort(key=lambda l:l.area,reverse=True)
    for i,l in enumerate(loops): l.layer="HOLES" if sum(point_in_polygon(centroid(l.points),b.points) for b in loops[:i])%2 else "CUT"
    return loops
def bounds(loops):
    pts=[p for l in loops for p in l.points]; return min(x for x,_ in pts),min(y for _,y in pts),max(x for x,_ in pts),max(y for _,y in pts)
def normalized(loops):
    x0,y0,_,_=bounds(loops); return [Loop([(x-x0,y-y0) for x,y in l.points],set(l.source_types),layer=l.layer) for l in loops]
def add_layers(doc):
    for name,color in (("CUT",7),("HOLES",1),("DIM",3),("CENTER",4),("TEXT",2)):
        if name not in doc.layers: doc.layers.add(name,color=color)
def circle_fit(points,tol_ratio=.015):
    q=points[:-1]; cx=sum(x for x,_ in q)/len(q); cy=sum(y for _,y in q)/len(q); rr=[dist((x,y),(cx,cy)) for x,y in q]; r=sum(rr)/len(rr)
    return (cx,cy,r) if r and (max(rr)-min(rr))/r<=tol_ratio else None
def add_dimensions(doc,msp,loops):
    x0,y0,x1,y1=bounds(loops); w=x1-x0; h=y1-y0; gap=max(w,h)*.08+10
    d=msp.add_linear_dim(base=(x0,y0-gap),p1=(x0,y0),p2=(x1,y0),angle=0,dxfattribs={"layer":"DIM"}); d.render()
    d=msp.add_linear_dim(base=(x1+gap,y0),p1=(x1,y0),p2=(x1,y1),angle=90,dxfattribs={"layer":"DIM"}); d.render()
    msp.add_text(f"OVERALL {w:.2f} x {h:.2f} mm",height=max(min(w,h)*.025,3),dxfattribs={"layer":"TEXT"}).set_placement((x0,y1+gap))
    for l in loops:
        fit=circle_fit(l.points)
        if fit and l.layer=="HOLES":
            cx,cy,r=fit; msp.add_line((cx-r,cy),(cx+r,cy),dxfattribs={"layer":"CENTER"}); msp.add_line((cx,cy-r),(cx,cy+r),dxfattribs={"layer":"CENTER"}); msp.add_text(f"DIA {2*r:.2f}",height=max(r*.35,2.5),dxfattribs={"layer":"TEXT"}).set_placement((cx+r*1.2,cy+r*1.2))
def write_outputs(source,output_base,flatten=.05,join_tol=.1,min_area=1.0,layers=None):
    loops=extract_loops(ezdxf.readfile(source),flatten,join_tol,min_area,layers)
    if not loops: raise ValueError("No closed manufacturing contours found; specify --layers or adjust tolerances")
    loops=normalized(loops)
    for suffix,dimensioned in (("_CNC.dxf",False),("_DIMENSIONED.dxf",True)):
        doc=ezdxf.new("R2010",setup=True); doc.units=4; add_layers(doc); msp=doc.modelspace()
        for l in loops: msp.add_lwpolyline(l.points[:-1],close=True,dxfattribs={"layer":l.layer})
        if dimensioned: add_dimensions(doc,msp,loops)
        doc.saveas(str(output_base)+suffix)
    manifest={"source":str(source),"contours":len(loops),"outer":sum(l.layer=="CUT" for l in loops),"inner":sum(l.layer=="HOLES" for l in loops),"bounds":bounds(loops),"flatten_tolerance_mm":flatten,"safe_for_cnc":False,"operator_confirmation_required":True}
    Path(str(output_base)+"_manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8"); return manifest
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("source"); ap.add_argument("output_base"); ap.add_argument("--flatten",type=float,default=.05); ap.add_argument("--join-tol",type=float,default=.1); ap.add_argument("--min-area",type=float,default=1.0); ap.add_argument("--layers")
    a=ap.parse_args(); layers=set(a.layers.split(",")) if a.layers else None; print(json.dumps(write_outputs(Path(a.source),Path(a.output_base),a.flatten,a.join_tol,a.min_area,layers),ensure_ascii=False,indent=2))
if __name__=="__main__": main()
