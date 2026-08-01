import json,sys
from pathlib import Path
import cv2, numpy as np
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from dimension_linker import link_dimensions, angle_diff, point_segment_distance, detect_segments

def test_geometry_helpers():
    assert angle_diff(179,1)==2
    d,q,t=point_segment_distance((5,3),(0,0),(10,0)); assert abs(d-3)<1e-6 and abs(q[0]-5)<1e-6 and abs(q[1])<1e-6

def test_arbitrary_angle_link(tmp_path):
    img=np.full((500,700,3),255,np.uint8)
    p1=np.array([180,360]); p2=np.array([520,140]); v=p2-p1; u=v/np.linalg.norm(v); n=np.array([-u[1],u[0]])
    cv2.line(img,tuple(p1),tuple(p2),(0,0,0),2)
    for p,sgn in [(p1,1),(p2,-1)]:
        back=sgn*u*22
        for side in (-1,1): cv2.line(img,tuple(p),tuple((p+back+side*n*9).astype(int)),(0,0,0),3)
    path=str(tmp_path/'angled.png'); cv2.imwrite(path,img)
    c=((p1+p2)/2).astype(int)
    ocr=[{'bbox':[int(c[0]-30),int(c[1]-18),60,36],'raw_text':'405','parsed_value_mm':405.0,'ocr_confidence':.94,'angle_deg':float(np.degrees(np.arctan2(v[1],v[0]))%180)}]
    geom={'outer_contour':[[180,360],[520,140],[560,200],[220,420]]}
    report=link_dimensions(path,ocr,geom,str(tmp_path/'debug'))
    assert report['dimensions'][0]['status'] in ('resolved','review')
    assert angle_diff(report['dimensions'][0]['line_angle_deg'],ocr[0]['angle_deg'])<8
    assert (tmp_path/'debug'/'dimension_links.json').exists()


def test_hough_shape_opencv5(monkeypatch):
    gray=np.full((100,100),255,np.uint8)
    monkeypatch.setattr(cv2,'HoughLinesP',lambda *a,**k: np.array([[5,10,80,10],[5,20,80,20]],dtype=np.int32))
    segments,_=detect_segments(gray,[])
    assert len(segments)==2
    assert all(len(s)==4 for s in segments)

def test_hough_shape_opencv4(monkeypatch):
    gray=np.full((100,100),255,np.uint8)
    monkeypatch.setattr(cv2,'HoughLinesP',lambda *a,**k: np.array([[[5,10,80,10]],[[5,20,80,20]]],dtype=np.int32))
    segments,_=detect_segments(gray,[])
    assert len(segments)==2
