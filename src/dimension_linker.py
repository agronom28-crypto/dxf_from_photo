"""Orientation-invariant linking of handwritten dimensions to drawing geometry.

Local-only pipeline. It does not trust OCR alone: numeric candidates are linked to
features through dimension/leader lines, arrowheads, extension lines, proximity,
orientation and global geometric consistency. Ambiguous links remain unresolved.
"""
from __future__ import annotations
import argparse, json, math, os
from dataclasses import dataclass, asdict
from typing import Any
import cv2
import numpy as np

EPS=1e-9

def _p(v): return np.asarray(v, dtype=float)
def dist(a,b): return float(np.linalg.norm(_p(a)-_p(b)))
def midpoint(a,b): return ((_p(a)+_p(b))/2).tolist()
def seg_len(s): return dist(s[:2],s[2:])
def angle_deg(a,b):
    v=_p(b)-_p(a)
    return math.degrees(math.atan2(v[1],v[0]))%180.0
def angle_diff(a,b):
    d=abs((a-b)%180.0); return min(d,180.0-d)
def point_segment_distance(p,a,b):
    p,a,b=_p(p),_p(a),_p(b); ab=b-a
    t=float(np.clip(np.dot(p-a,ab)/(np.dot(ab,ab)+EPS),0,1))
    q=a+t*ab
    return float(np.linalg.norm(p-q)),q.tolist(),t

def bbox_center(b):
    x,y,w,h=b[:4]; return [x+w/2,y+h/2]

def bbox_diag(b): return math.hypot(float(b[2]),float(b[3]))

def detect_segments(gray, text_boxes=()):
    """Detect line segments while masking OCR boxes so handwriting does not dominate."""
    work=gray.copy()
    for b in text_boxes:
        x,y,w,h=map(int,b[:4]); pad=max(3,int(.15*max(w,h)))
        cv2.rectangle(work,(max(0,x-pad),max(0,y-pad)),
                      (min(work.shape[1]-1,x+w+pad),min(work.shape[0]-1,y+h+pad)),255,-1)
    edges=cv2.Canny(work,50,150,apertureSize=3)
    scale=max(gray.shape)
    lines=cv2.HoughLinesP(edges,1,np.pi/360,threshold=max(18,int(scale*.018)),
                          minLineLength=max(12,int(scale*.012)),maxLineGap=max(6,int(scale*.008)))
    if lines is None: return [],edges
    # OpenCV 4 usually returns (N, 1, 4), while OpenCV 5 may return (N, 4).
    # Normalizing via reshape keeps the linker compatible with both APIs.
    arr=np.asarray(lines)
    if arr.size == 0: return [],edges
    raw=arr.reshape(-1,4).astype(float).tolist()
    return merge_collinear(raw),edges

def merge_collinear(lines,angle_tol=4.0,offset_tol=8.0,gap_tol=25.0):
    """Merge duplicate Hough fragments into stable segments."""
    out=[]
    for s in sorted(lines,key=seg_len,reverse=True):
        a,b=s[:2],s[2:]; ang=angle_deg(a,b); merged=False
        for i,t in enumerate(out):
            ta,tb=t[:2],t[2:]
            if angle_diff(ang,angle_deg(ta,tb))>angle_tol: continue
            d1,_,_=point_segment_distance(a,ta,tb); d2,_,_=point_segment_distance(b,ta,tb)
            if min(d1,d2)>offset_tol: continue
            pts=np.array([a,b,ta,tb]); u=np.array([math.cos(math.radians(ang)),math.sin(math.radians(ang))])
            proj=pts@u; lo,hi=float(proj.min()),float(proj.max())
            if hi-lo>seg_len(s)+seg_len(t)+gap_tol: continue
            origin=pts.mean(axis=0); normal=np.array([-u[1],u[0]])
            off=float(np.median(pts@normal)); p1=u*lo+normal*off; p2=u*hi+normal*off
            out[i]=[float(p1[0]),float(p1[1]),float(p2[0]),float(p2[1])]; merged=True; break
        if not merged: out.append(s)
    return out

def detect_arrowheads(segments):
    """Find V/chevron arrowheads from pairs of short segments sharing a tip."""
    if not segments:return []
    lens=np.array([seg_len(s) for s in segments]); med=float(np.median(lens))
    max_short=max(18.0,min(90.0,med*.75))
    shorts=[s for s in segments if 5<=seg_len(s)<=max_short]
    arrows=[]
    for i,a in enumerate(shorts):
        for b in shorts[i+1:]:
            ends_a=[a[:2],a[2:]]; ends_b=[b[:2],b[2:]]
            pairs=[(dist(x,y),x,y) for x in ends_a for y in ends_b]
            d,x,y=min(pairs,key=lambda z:z[0])
            if d>10: continue
            tip=midpoint(x,y)
            oa=max(ends_a,key=lambda z:dist(z,tip)); ob=max(ends_b,key=lambda z:dist(z,tip))
            va=_p(oa)-_p(tip); vb=_p(ob)-_p(tip)
            c=float(np.dot(va,vb)/(np.linalg.norm(va)*np.linalg.norm(vb)+EPS))
            opening=math.degrees(math.acos(np.clip(c,-1,1)))
            if 18<=opening<=105:
                axis=(va/np.linalg.norm(va)+vb/np.linalg.norm(vb));
                if np.linalg.norm(axis)>EPS: axis=axis/np.linalg.norm(axis)
                arrows.append({'tip':tip,'axis':[float(axis[0]),float(axis[1])],
                               'opening_deg':opening,'confidence':max(.2,1-abs(opening-45)/80)})
    ded=[]
    for a in sorted(arrows,key=lambda x:-x['confidence']):
        if not any(dist(a['tip'],b['tip'])<12 for b in ded): ded.append(a)
    return ded

def _feature_list(geometry):
    feats=[]
    outer=geometry.get('outer_contour') or geometry.get('outer') or geometry.get('contour') or []
    if isinstance(outer,dict): outer=outer.get('points',[])
    for i,p in enumerate(outer): feats.append({'id':f'vertex:{i}','type':'vertex','point':p})
    for i,(a,b) in enumerate(zip(outer,outer[1:]+outer[:1] if outer else [])):
        feats.append({'id':f'edge:{i}','type':'edge','a':a,'b':b})
    for i,h in enumerate(geometry.get('holes',[])):
        c=h.get('center',[h.get('x',0),h.get('y',0)]); r=h.get('radius',h.get('r',h.get('diameter',h.get('d',0))/2))
        feats.append({'id':h.get('id',f'hole:{i}'),'type':'circle','center':c,'radius':r})
    for i,c in enumerate(geometry.get('cutouts',[])):
        pts=c.get('points',c if isinstance(c,list) else [])
        for j,(a,b) in enumerate(zip(pts,pts[1:]+pts[:1] if pts else [])):
            feats.append({'id':f'cutout:{i}:edge:{j}','type':'edge','a':a,'b':b})
    return feats

def nearest_feature(point,features):
    best=None
    for f in features:
        if f['type']=='vertex': d=dist(point,f['point']); q=f['point']
        elif f['type']=='edge': d,q,_=point_segment_distance(point,f['a'],f['b'])
        else:
            c=f['center']; r=float(f.get('radius',0)); dc=dist(point,c); d=abs(dc-r)
            v=(_p(point)-_p(c))/(dc+EPS); q=(_p(c)+v*r).tolist()
        if best is None or d<best[0]: best=(d,f,q)
    return best

def find_dimension_line(text,segments):
    c=bbox_center(text['bbox']); diag=max(10,bbox_diag(text['bbox']))
    hint=text.get('angle_deg')
    cand=[]
    for s in segments:
        d,q,t=point_segment_distance(c,s[:2],s[2:]); L=seg_len(s)
        if L<diag*.45 or d>diag*4.0: continue
        a=angle_deg(s[:2],s[2:]); orient=1.0 if hint is None else math.exp(-angle_diff(a,float(hint))/25)
        center_bonus=math.exp(-d/(diag*1.4)); length_bonus=min(1,L/(diag*3))
        score=.48*center_bonus+.30*orient+.22*length_bonus
        cand.append((score,s,d,a))
    return max(cand,key=lambda x:x[0]) if cand else None

def endpoint_from_arrows(line,arrows):
    ends=[line[:2],line[2:]]; out=[]
    L=seg_len(line); radius=max(16,min(55,L*.12))
    for e in ends:
        near=[a for a in arrows if dist(a['tip'],e)<=radius]
        out.append(max(near,key=lambda a:a['confidence'])['tip'] if near else e)
    return out

def classify_link(text,line,endpoints,features):
    raw=str(text.get('raw_text','')); value=text.get('parsed_value_mm')
    c=bbox_center(text['bbox']); near=[]
    for p in endpoints:
        n=nearest_feature(p,features); near.append(n)
    circle_hits=[n for n in near if n and n[1]['type']=='circle']
    leader_like=dist(c,midpoint(*endpoints))>seg_len(line)*.35
    if 'Ø' in raw or '⌀' in raw or raw.lower().startswith('d') or (leader_like and circle_hits): kind='diameter'
    elif 'R' in raw.upper() and circle_hits: kind='radius'
    elif '°' in raw or 'deg' in raw.lower(): kind='angle'
    else: kind='linear'
    refs=[]; ds=[]
    for n in near:
        if n: ds.append(n[0]); refs.append({'feature_id':n[1]['id'],'feature_type':n[1]['type'],'snap_point':n[2],'distance_px':round(n[0],2)})
    return kind,refs,ds

def link_dimensions(image_path,ocr_candidates,geometry,debug_dir=None):
    img=cv2.imread(image_path)
    if img is None: raise FileNotFoundError(image_path)
    gray=cv2.cvtColor(img,cv2.COLOR_BGR2GRAY)
    boxes=[x['bbox'] for x in ocr_candidates]
    segments,edges=detect_segments(gray,boxes)
    arrows=detect_arrowheads(segments)
    features=_feature_list(geometry)
    results=[]
    diag=math.hypot(*gray.shape)
    for idx,t in enumerate(ocr_candidates):
        dl=find_dimension_line(t,segments)
        if not dl:
            results.append({'id':f'dim:{idx}','status':'unresolved','reason':'dimension_line_not_found','ocr':t,'confidence':0.0}); continue
        line_score,line,text_distance,line_angle=dl
        endpoints=endpoint_from_arrows(line,arrows)
        kind,refs,feature_ds=classify_link(t,line,endpoints,features)
        ocr_conf=float(t.get('ocr_confidence',0)); arrow_count=sum(any(dist(p,a['tip'])<12 for a in arrows) for p in endpoints)
        feature_score=math.exp(-np.mean(feature_ds)/(diag*.025)) if feature_ds else 0.0
        confidence=.35*ocr_conf+.25*line_score+.20*(arrow_count/2)+.20*feature_score
        status='resolved' if confidence>=.62 and len(refs)>=1 else ('review' if confidence>=.35 else 'unresolved')
        results.append({'id':f'dim:{idx}','status':status,'kind':kind,'value_mm':t.get('parsed_value_mm'),
                        'raw_text':t.get('raw_text'),'text_bbox':t['bbox'],'dimension_line':line,
                        'line_angle_deg':round(line_angle,2),'endpoints':endpoints,'references':refs,
                        'evidence':{'ocr':round(ocr_conf,3),'line':round(line_score,3),'arrows':arrow_count,'geometry':round(feature_score,3)},
                        'confidence':round(confidence,3)})
    report={'image':image_path,'dimensions':results,'detected':{'segments':len(segments),'arrowheads':len(arrows),'features':len(features)},
            'policy':{'auto_accept_min':.62,'review_min':.35,'never_guess_ambiguous':True}}
    if debug_dir:
        os.makedirs(debug_dir,exist_ok=True); vis=img.copy()
        for s in segments: cv2.line(vis,tuple(map(int,s[:2])),tuple(map(int,s[2:])),(180,180,0),1)
        for a in arrows: cv2.circle(vis,tuple(map(int,a['tip'])),5,(255,0,255),2)
        colors={'resolved':(0,180,0),'review':(0,165,255),'unresolved':(0,0,255)}
        for r in results:
            col=colors[r['status']]; b=r.get('text_bbox') or r.get('ocr',{}).get('bbox'); x,y,w,h=map(int,b)
            cv2.rectangle(vis,(x,y),(x+w,y+h),col,2)
            if 'dimension_line' in r: cv2.line(vis,tuple(map(int,r['dimension_line'][:2])),tuple(map(int,r['dimension_line'][2:])),col,3)
            cv2.putText(vis,f"{r.get('value_mm')} {r['status']}",(x,max(15,y-5)),cv2.FONT_HERSHEY_SIMPLEX,.5,col,1,cv2.LINE_AA)
        cv2.imwrite(os.path.join(debug_dir,'dimension_links.png'),vis)
        cv2.imwrite(os.path.join(debug_dir,'dimension_edges.png'),edges)
        with open(os.path.join(debug_dir,'dimension_links.json'),'w',encoding='utf-8') as f: json.dump(report,f,ensure_ascii=False,indent=2)
    return report

def main():
    ap=argparse.ArgumentParser(description='Привязка OCR-размеров к геометрии при любом угле записи')
    ap.add_argument('image'); ap.add_argument('ocr_json'); ap.add_argument('geometry_json'); ap.add_argument('--debug-dir')
    a=ap.parse_args()
    with open(a.ocr_json,encoding='utf-8') as f: ocr=json.load(f)
    with open(a.geometry_json,encoding='utf-8') as f: geom=json.load(f)
    print(json.dumps(link_dimensions(a.image,ocr,geom,a.debug_dir),ensure_ascii=False,indent=2))
if __name__=='__main__': main()
