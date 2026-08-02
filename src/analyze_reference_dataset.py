#!/usr/bin/env python3
"""Audit every reference DXF and build a machine-readable coverage report."""
import argparse, collections, json
from pathlib import Path
import ezdxf
from reference_dxf_pipeline import extract_loops, bounds

def analyze(folder:Path,flatten=.05,join_tol=.1):
    files=[]; totals=collections.Counter()
    for p in sorted(folder.glob("*.dxf")):
        row={"file":p.name}
        try:
            doc=ezdxf.readfile(p); entities=collections.Counter(e.dxftype() for e in doc.modelspace()); totals.update(entities)
            loops=extract_loops(doc,flatten,join_tol)
            row.update(status="ok",entities=dict(entities),closed_contours=len(loops),outer=sum(x.layer=="CUT" for x in loops),inner=sum(x.layer=="HOLES" for x in loops),bounds=bounds(loops) if loops else None,convertible=bool(loops))
        except Exception as e: row.update(status="error",error=str(e),convertible=False)
        files.append(row)
    return {"dataset":str(folder),"files":len(files),"readable":sum(x["status"]=="ok" for x in files),"convertible":sum(x["convertible"] for x in files),"entity_totals":dict(totals),"items":files}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("folder"); ap.add_argument("--output",default="dataset/reference_shapes_report.json"); a=ap.parse_args()
    report=analyze(Path(a.folder)); Path(a.output).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8"); print(json.dumps({k:report[k] for k in ("files","readable","convertible")},indent=2))
if __name__=="__main__": main()
