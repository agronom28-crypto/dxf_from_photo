#!/usr/bin/env python3
"""Ask the operator only about unreadable handwritten dimensions."""
from __future__ import annotations
import argparse, html, json
from pathlib import Path
import cv2

DEFAULT_OCR_THRESHOLD=.88
DEFAULT_AMBIGUITY_MARGIN=.08

def needs_question(item,threshold=DEFAULT_OCR_THRESHOLD,margin=DEFAULT_AMBIGUITY_MARGIN):
    candidates=sorted(item.get("candidates",[]),key=lambda x:float(x.get("confidence",0)),reverse=True)
    if not candidates: return True,"no_reading"
    best=float(candidates[0].get("confidence",0))
    if best<threshold: return True,"low_ocr_confidence"
    if len(candidates)>1 and best-float(candidates[1].get("confidence",0))<margin and candidates[0].get("text")!=candidates[1].get("text"): return True,"ambiguous_handwriting"
    return False,None

def build_review(image_path,detections_path,output_dir,threshold=DEFAULT_OCR_THRESHOLD,margin=DEFAULT_AMBIGUITY_MARGIN):
    image=cv2.imread(str(image_path))
    if image is None: raise FileNotFoundError(image_path)
    data=json.loads(Path(detections_path).read_text(encoding="utf-8")); out=Path(output_dir); out.mkdir(parents=True,exist_ok=True); questions=[]
    for item in data.get("dimensions",[]):
        ask,reason=needs_question(item,threshold,margin); candidates=sorted(item.get("candidates",[]),key=lambda x:float(x.get("confidence",0)),reverse=True)
        if not ask:
            item["resolved_text"]=str(candidates[0]["text"]); item["resolved_value_mm"]=float(candidates[0].get("value_mm",candidates[0]["text"])); item["resolution"]="automatic"; continue
        x,y,w,h=map(int,item["bbox"]); x=max(0,x); y=max(0,y); w=max(1,w); h=max(1,h); pad=max(12,int(max(w,h)*.35)); x0=max(0,x-pad); y0=max(0,y-pad); x1=min(image.shape[1],x+w+pad); y1=min(image.shape[0],y+h+pad)
        crop=image[y0:y1,x0:x1].copy(); cv2.rectangle(crop,(x-x0,y-y0),(x+w-x0,y+h-y0),(0,0,255),3); qid=str(item.get("id",f"dimension_{len(questions)+1}")); crop_name=f"{qid}.png"; cv2.imwrite(str(out/crop_name),crop)
        questions.append({"id":qid,"reason":reason,"bbox":[x,y,w,h],"target":item.get("target"),"crop":crop_name,"candidates":[{"text":str(c.get("text","")),"value_mm":c.get("value_mm"),"confidence":float(c.get("confidence",0))} for c in candidates[:4]]})
    data["clarification_required"]=bool(questions); data["questions"]=questions; (out/"review.json").write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8"); (out/"review.html").write_text(render_html(questions),encoding="utf-8"); return data

def render_html(questions):
    cards=[]
    for q in questions:
        opts="".join(f'<label><input type="radio" name="{html.escape(q["id"])}" value="{html.escape(c["text"])}"> {html.escape(c["text"])} ({c["confidence"]:.0%})</label><br>' for c in q["candidates"])
        cards.append(f'<section><h2>{html.escape(q["id"])} — {html.escape(str(q.get("target") or "размер"))}</h2><img src="{html.escape(q["crop"])}"><p>Красной рамкой отмечена неразборчивая надпись.</p>{opts}<label>Другое значение, мм: <input name="{html.escape(q["id"])}_manual" inputmode="decimal"></label></section>')
    body="".join(cards) if cards else "<h2>Все размеры распознаны уверенно. Вопросов оператору нет.</h2>"
    return '<!doctype html><meta charset="utf-8"><title>Уточнение размеров</title><style>body{font:16px sans-serif;max-width:900px;margin:30px auto}section{border:1px solid #bbb;padding:18px;margin:18px 0;border-radius:10px}img{max-width:100%;border:1px solid #333}label{line-height:2}</style><h1>Уточнение рукописных размеров</h1>'+body

def apply_answers(review_path,answers_path,output_path):
    review=json.loads(Path(review_path).read_text(encoding="utf-8")); answers=json.loads(Path(answers_path).read_text(encoding="utf-8")); by_id={str(x.get("id")):x for x in review.get("dimensions",[])}
    for q in review.get("questions",[]):
        qid=q["id"]
        if qid not in answers: raise ValueError(f"missing operator answer: {qid}")
        value=float(answers[qid]); item=by_id[qid]; item["resolved_text"]=str(answers[qid]); item["resolved_value_mm"]=value; item["resolution"]="operator_clarification"
    unresolved=[x.get("id") for x in review.get("dimensions",[]) if x.get("resolved_value_mm") is None]
    if unresolved: raise ValueError(f"unresolved dimensions: {unresolved}")
    review["clarification_required"]=False; review["operator_answers_applied"]=True; Path(output_path).write_text(json.dumps(review,ensure_ascii=False,indent=2),encoding="utf-8"); return review

def main():
    ap=argparse.ArgumentParser(); sub=ap.add_subparsers(dest="cmd",required=True); b=sub.add_parser("build"); b.add_argument("image"); b.add_argument("detections"); b.add_argument("output_dir"); b.add_argument("--threshold",type=float,default=DEFAULT_OCR_THRESHOLD); a=sub.add_parser("apply"); a.add_argument("review"); a.add_argument("answers"); a.add_argument("output"); x=ap.parse_args(); result=build_review(x.image,x.detections,x.output_dir,x.threshold) if x.cmd=="build" else apply_answers(x.review,x.answers,x.output); print(json.dumps({"clarification_required":result["clarification_required"],"questions":len(result.get("questions",[]))},ensure_ascii=False))
if __name__=="__main__": main()
