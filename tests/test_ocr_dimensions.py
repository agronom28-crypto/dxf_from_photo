import sys
from pathlib import Path
import cv2,numpy as np
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from ocr_dimensions import estimate_box_angle,parse_number_candidate

def test_rotated_text_angle_estimation():
 img=np.full((160,220),255,np.uint8); cv2.putText(img,'150',(45,90),cv2.FONT_HERSHEY_SIMPLEX,1.5,0,3)
 M=cv2.getRotationMatrix2D((110,80),30,1); rot=cv2.warpAffine(img,M,(220,160),borderValue=255)
 a=estimate_box_angle(rot,(20,20,180,120)); assert abs(a)>10

def test_dimension_prefix_parsing():
 assert parse_number_candidate('D10')==10
 assert parse_number_candidate('R7.5')==7.5
