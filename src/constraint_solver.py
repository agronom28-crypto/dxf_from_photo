"""Global consistency checks for linked drawing dimensions.

The solver does not invent geometry. It validates OCR/link candidates against measured
endpoint distances, duplicate dimensions, diameter/radius geometry and linear chains.
Conflicting dimensions are downgraded instead of silently applied.
"""
from __future__ import annotations
import argparse, copy, json, math
from collections import defaultdict
import numpy as np

def dist(a,b): return math.hypot(float(a[0])-float(b[0]),float(a[1])-float(b[1]))
def px_to_mm(p,geometry):
    s=float(geometry['scale']['px_to_mm']); ox,oy=geometry['scale']['origin_px']
    return [(float(p[0])-ox)*s,(oy-float(p[1]))*s]
def rel_error(a,b): return abs(a-b)/max(abs(a),abs(b),1e-9)
def _ref_pair(d):
    ids=sorted(r['feature_id'] for r in d.get('references',[]))
    return tuple(ids[:2]) if ids else ()
def _axis(d):
    a=float(d.get('line_angle_deg',0)); return 'x' if min(abs(a),abs(a-180))<=45 else 'y'
def _measured(d,g):
    if d.get('kind')=='linear' and len(d.get('endpoints',[]))==2:
        a,b=[px_to_mm(p,g) for p in d['endpoints']]; return dist(a,b)
    if d.get('kind') in ('diameter','radius'):
        ids={r['feature_id'] for r in d.get('references',[])}
        for h in g.get('holes',[]):
            # linker default ids are hole:<index>
            idx=g.get('holes',[]).index(h)
            if f'hole:{idx}' in ids:
                radius=float(h.get('radius',0))*float(g['scale']['px_to_mm'])
                return radius*2 if d['kind']=='diameter' else radius
    return None

def _endpoint_key(p,tol=18): return (round(float(p[0])/tol),round(float(p[1])/tol))
def solve_constraints(links,geometry,geometry_tol=.18,duplicate_tol=.04,chain_tol=.08):
    out=copy.deepcopy(links); dims=out.get('dimensions',[]); issues=[]
    # Individual geometric residuals.
    for d in dims:
        val=d.get('value_mm'); measured=_measured(d,geometry)
        d.setdefault('global_checks',{})['measured_geometry_mm']=None if measured is None else round(measured,3)
        if val is None or measured is None or float(val)<=0: continue
        err=rel_error(float(val),measured); d['global_checks']['geometry_relative_error']=round(err,4)
        if err>geometry_tol:
            issues.append({'type':'geometry_mismatch','dimension_id':d['id'],'ocr_value_mm':val,'geometry_mm':round(measured,3),'relative_error':round(err,4)})
            d['confidence']=round(min(float(d.get('confidence',0)),.34),3); d['status']='unresolved'
        elif err<geometry_tol*.35:
            d['confidence']=round(min(1,float(d.get('confidence',0))+.08),3)
    # Duplicate dimensions on same feature pair must agree.
    groups=defaultdict(list)
    for d in dims:
        key=(d.get('kind'),_ref_pair(d))
        if key[1] and d.get('value_mm') is not None: groups[key].append(d)
    for key,group in groups.items():
        if len(group)<2: continue
        vals=np.array([float(d['value_mm']) for d in group]); med=float(np.median(vals))
        for d in group:
            err=rel_error(float(d['value_mm']),med)
            d['global_checks']['duplicate_median_mm']=round(med,3)
            if err>duplicate_tol:
                issues.append({'type':'duplicate_conflict','dimension_id':d['id'],'median_mm':round(med,3),'relative_error':round(err,4)})
                d['status']='review'; d['confidence']=round(min(float(d.get('confidence',0)),.61),3)
    # Detect A-B + B-C = A-C chains for dimensions sharing approximately equal direction.
    linear=[d for d in dims if d.get('kind')=='linear' and len(d.get('endpoints',[]))==2 and d.get('value_mm')]
    nodes={}
    edges=[]
    for d in linear:
        ka,kb=[_endpoint_key(p) for p in d['endpoints']]; nodes.setdefault(ka,d['endpoints'][0]); nodes.setdefault(kb,d['endpoints'][1])
        edges.append((ka,kb,float(d['value_mm']),d))
    direct={(min(a,b),max(a,b)):(v,d) for a,b,v,d in edges}
    checked=set()
    for a,b,v1,d1 in edges:
        for c,d,v2,d2 in edges:
            if b!=c or a==d: continue
            key=(min(a,d),max(a,d))
            if key not in direct: continue
            v3,d3=direct[key]; sig=tuple(sorted([d1['id'],d2['id'],d3['id']]))
            if sig in checked: continue
            checked.add(sig); err=rel_error(v1+v2,v3)
            for x in (d1,d2,d3): x['global_checks']['chain_relative_error']=round(err,4)
            if err>chain_tol:
                worst=min((d1,d2,d3),key=lambda x:float(x.get('confidence',0)))
                worst['status']='review'; worst['confidence']=round(min(float(worst.get('confidence',0)),.61),3)
                issues.append({'type':'chain_conflict','dimension_ids':list(sig),'sum_mm':round(v1+v2,3),'overall_mm':round(v3,3),'relative_error':round(err,4)})
    # Promote only after all checks; never promote unresolved OCR.
    for d in dims:
        if d.get('status')=='review' and float(d.get('confidence',0))>=.70 and not any(i.get('dimension_id')==d['id'] or d['id'] in i.get('dimension_ids',[]) for i in issues): d['status']='resolved'
    out['constraint_solver']={'issues':issues,'issue_count':len(issues),'geometry_tolerance':geometry_tol,'duplicate_tolerance':duplicate_tol,'chain_tolerance':chain_tol,
        'resolved':sum(d.get('status')=='resolved' for d in dims),'review':sum(d.get('status')=='review' for d in dims),'unresolved':sum(d.get('status')=='unresolved' for d in dims)}
    return out

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('links_json'); ap.add_argument('geometry_json'); ap.add_argument('output_json'); a=ap.parse_args()
    with open(a.links_json,encoding='utf-8') as f: links=json.load(f)
    with open(a.geometry_json,encoding='utf-8') as f: geo=json.load(f)
    result=solve_constraints(links,geo)
    with open(a.output_json,'w',encoding='utf-8') as f: json.dump(result,f,ensure_ascii=False,indent=2)
    print(json.dumps(result['constraint_solver'],ensure_ascii=False,indent=2))
if __name__=='__main__': main()
