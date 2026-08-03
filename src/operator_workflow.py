#!/usr/bin/env python3
"""Safe operator workflow: photo -> candidates -> confirmed job -> two DXFs."""
from __future__ import annotations
import argparse, json
from pathlib import Path
from sketch_shape_matcher import match
from reference_dxf_pipeline import write_outputs
REQUIRED=("selected_reference","overall_width_mm","overall_height_mm","dimensions_confirmed","geometry_confirmed")
def create_job(image,index,output):
    result=match(image,index,top=5); job={**result,"selected_reference":None,"overall_width_mm":None,"overall_height_mm":None,"dimensions":[],"dimensions_confirmed":False,"geometry_confirmed":False,"cnc_export_allowed":False,"notes":["Select one reference topology","Confirm every handwritten dimension","Unresolved dimensions block CNC export"]}; Path(output).write_text(json.dumps(job,ensure_ascii=False,indent=2),encoding="utf-8"); return job
def validate_job(job):
    missing=[k for k in REQUIRED if job.get(k) in (None,False,"")]; unresolved=[d for d in job.get("dimensions",[]) if not d.get("confirmed") or d.get("value_mm") is None or not d.get("target")]
    if missing or unresolved: raise ValueError(f"CNC blocked: missing={missing}; unresolved_dimensions={len(unresolved)}")
    return True
def export_job(job_path,dataset_dir,output_base):
    job=json.loads(Path(job_path).read_text()); validate_job(job); src=Path(dataset_dir)/job["selected_reference"]; manifest=write_outputs(src,Path(output_base)); manifest["job"]=str(job_path); manifest["operator_dimensions"]=job["dimensions"]; manifest["safe_for_cnc"]=True; Path(str(output_base)+"_manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8"); return manifest
def main():
    ap=argparse.ArgumentParser(); sub=ap.add_subparsers(dest="cmd",required=True); c=sub.add_parser("create"); c.add_argument("image"); c.add_argument("index"); c.add_argument("job"); e=sub.add_parser("export"); e.add_argument("job"); e.add_argument("dataset"); e.add_argument("output_base"); a=ap.parse_args(); result=create_job(a.image,a.index,a.job) if a.cmd=="create" else export_job(a.job,a.dataset,a.output_base); print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=="__main__": main()
