#!/usr/bin/env python3
"""Compile a confirmed construction spec and export CNC and dimensioned DXF."""
from __future__ import annotations
import argparse, json
from pathlib import Path
import ezdxf
from parametric_cad_kernel import Arc, Line, compile_model, path_points
from production_validator import validate

def layers(doc):
    for name,color in (("CUT",7),("HOLES",1),("DIM",3),("TEXT",2)):
        if name not in doc.layers: doc.layers.add(name,color=color)
def add_geometry(msp,model):
    for path in model.paths:
        for e in path:
            if isinstance(e,Line): msp.add_line((e.start.x,e.start.y),(e.end.x,e.end.y),dxfattribs={"layer":e.layer})
            elif isinstance(e,Arc):
                start,end=(e.start_deg,e.end_deg) if e.ccw else (e.end_deg,e.start_deg); msp.add_arc((e.center.x,e.center.y),e.radius,start,end,dxfattribs={"layer":e.layer})
    for c in model.circles: msp.add_circle((c.center.x,c.center.y),c.radius,dxfattribs={"layer":c.layer})
def bounds(model):
    pts=[q for p in model.paths for q in path_points(p)]; return min(q.x for q in pts),min(q.y for q in pts),max(q.x for q in pts),max(q.y for q in pts)
def export(spec_path,output_base):
    spec=json.loads(Path(spec_path).read_text(encoding="utf-8")); model=compile_model(spec); check=validate(model)
    if not check.cnc_allowed: raise ValueError("CNC export blocked: "+"; ".join(check.errors))
    x0,y0,x1,y1=bounds(model)
    for suffix,dimensioned in (("_CNC.dxf",False),("_DIMENSIONED.dxf",True)):
        doc=ezdxf.new("R2010",setup=True); doc.units=4; layers(doc); msp=doc.modelspace(); add_geometry(msp,model)
        if dimensioned:
            gap=max(x1-x0,y1-y0)*.08+10; d=msp.add_linear_dim(base=(x0,y0-gap),p1=(x0,y0),p2=(x1,y0),angle=0,dxfattribs={"layer":"DIM"}); d.render(); d=msp.add_linear_dim(base=(x1+gap,y0),p1=(x1,y0),p2=(x1,y1),angle=90,dxfattribs={"layer":"DIM"}); d.render()
            for c in model.circles: msp.add_text(f"DIA {2*c.radius:.2f}",height=3,dxfattribs={"layer":"TEXT"}).set_placement((c.center.x+c.radius,c.center.y+c.radius))
        doc.saveas(str(output_base)+suffix)
    manifest={"part_id":model.part_id,"parameters":model.parameters,"features":sum(len(x) for x in model.paths)+len(model.circles),"validation":{"errors":check.errors,"warnings":check.warnings},"cnc_allowed":True,"operator_confirmed":True}; Path(str(output_base)+"_manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8"); return manifest
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("spec"); ap.add_argument("output_base"); a=ap.parse_args(); print(json.dumps(export(a.spec,a.output_base),ensure_ascii=False,indent=2))
if __name__=="__main__": main()
