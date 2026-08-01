import json,sys
from pathlib import Path
import cv2,numpy as np
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from auto_pipeline import run_pipeline

def test_end_to_end_no_text(tmp_path):
    img=np.full((500,800,3),255,np.uint8)
    cv2.rectangle(img,(100,120),(700,380),(0,0,0),5)
    cv2.circle(img,(250,250),25,(0,0,0),4)
    src=tmp_path/'part.png'; cv2.imwrite(str(src),img)
    result=run_pipeline(str(src),str(tmp_path/'out'),600,lang='eng')
    assert Path(result['outputs']['draft_dxf']).exists()
    assert Path(result['outputs']['dimensions_overlay_dxf']).exists()
    geo=json.loads(Path(result['outputs']['geometry_json']).read_text())
    assert len(geo['outer_contour'])>=4 and geo['coordinate_system']=='image_pixels'
    assert result['safe_for_cnc'] is False
