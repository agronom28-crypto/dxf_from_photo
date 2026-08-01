"""One-command local pipeline: photo -> geometry -> OCR -> dimension links -> annotated DXF/report."""
from __future__ import annotations
import argparse, json, os, shutil
from pathlib import Path
from photo_to_draft_dxf import build_draft_dxf
from ocr_dimensions import recognize_dimensions
from dimension_linker import link_dimensions
from geometry import DxfBuilder


def _save_json(path,data):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    with open(path,'w',encoding='utf-8') as f: json.dump(data,f,ensure_ascii=False,indent=2)

def _px_to_mm(p,geom):
    scale=geom['scale']['px_to_mm']; ox,oy=geom['scale']['origin_px']
    return [(float(p[0])-ox)*scale,(oy-float(p[1]))*scale]

def add_verified_dimensions(base_dxf,output_dxf,links,geom):
    """Append resolved dimensions on a separate layer; never modifies CUT geometry."""
    # Rebuild overlay as a standalone DXF to avoid corrupting an existing R12 file.
    b=DxfBuilder()
    for r in links['dimensions']:
        if r.get('status')!='resolved' or r.get('value_mm') is None: continue
        kind=r.get('kind','linear'); value=float(r['value_mm']); ends=r.get('endpoints',[])
        if kind=='linear' and len(ends)==2:
            a,c=map(_px_to_mm,ends,[geom,geom]) if False else (_px_to_mm(ends[0],geom),_px_to_mm(ends[1],geom))
            dx,dy=c[0]-a[0],c[1]-a[1]; ang=__import__('math').atan2(dy,dx)
            b.line(a[0],a[1],c[0],c[1],'DIM_AUTO'); b._arrow(a[0],a[1],ang,'DIM_AUTO'); b._arrow(c[0],c[1],ang+__import__('math').pi,'DIM_AUTO')
            m=[(a[0]+c[0])/2,(a[1]+c[1])/2]; b.text(m[0],m[1]+8,f'{value:g}',12,__import__('math').degrees(ang),'TEXT_AUTO')
        elif kind in ('diameter','radius') and r.get('references'):
            q=_px_to_mm(r['references'][0]['snap_point'],geom)
            prefix='DIA ' if kind=='diameter' else 'R '
            b.text(q[0]+10,q[1]+10,prefix+f'{value:g}',12,0,'TEXT_AUTO')
    b.text(0,-25,'AUTO DIMENSION OVERLAY - VERIFY BEFORE CNC',12,0,'TEXT_AUTO')
    b.save(output_dxf)
    return output_dxf

def run_pipeline(image,out_dir,scale_mm=1000.0,lang='rus+eng',strict=True):
    out=Path(out_dir); out.mkdir(parents=True,exist_ok=True)
    draft=out/'draft.dxf'; geo_dir=out/'geometry'; ocr_dir=out/'ocr'; link_dir=out/'links'
    build_draft_dxf(image,str(draft),scale_mm,debug_dir=str(geo_dir),strict=strict)
    ocr=recognize_dimensions(image,debug_dir=str(ocr_dir),lang=lang)
    geo=json.loads((geo_dir/'recognition_report.json').read_text(encoding='utf-8'))
    links=link_dimensions(image,ocr,geo,debug_dir=str(link_dir))
    _save_json(out/'ocr_candidates.json',ocr); _save_json(out/'dimension_links.json',links)
    add_verified_dimensions(str(draft),str(out/'dimensions_overlay.dxf'),links,geo)
    counts={s:sum(1 for x in links['dimensions'] if x['status']==s) for s in ('resolved','review','unresolved')}
    manifest={'input':str(image),'outputs':{'draft_dxf':str(draft),'dimensions_overlay_dxf':str(out/'dimensions_overlay.dxf'),
        'geometry_json':str(geo_dir/'recognition_report.json'),'ocr_json':str(out/'ocr_candidates.json'),
        'links_json':str(out/'dimension_links.json'),'links_preview':str(link_dir/'dimension_links.png')},
        'counts':counts,'safe_for_cnc':False,'warning':'Automatic OCR/dimension links must be verified before CNC.'}
    _save_json(out/'pipeline_manifest.json',manifest); return manifest

def main():
    ap=argparse.ArgumentParser(description=__doc__); ap.add_argument('image'); ap.add_argument('output_dir')
    ap.add_argument('--scale-mm',type=float,default=1000.0); ap.add_argument('--lang',default='rus+eng'); ap.add_argument('--no-strict',action='store_true')
    a=ap.parse_args(); print(json.dumps(run_pipeline(a.image,a.output_dir,a.scale_mm,a.lang,not a.no_strict),ensure_ascii=False,indent=2))
if __name__=='__main__': main()
