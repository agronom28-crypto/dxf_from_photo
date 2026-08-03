from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import ezdxf

import hole_diameter_clarification as holes
from contour_geometry import build_contour_from_measurements, extract_outline

ROOT = Path(__file__).resolve().parent.parent
INBOX = ROOT / "новые фотографии"
DONE = INBOX / "_done"
OUTBOX = ROOT / "DXF"
STATE_FILE = OUTBOX / ".processing_state.json"
TMP = OUTBOX / ".tmp"
SUPPORTED = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}
POLL = 1.0


def _atomic_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _state():
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8")) if STATE_FILE.exists() else {}
    except Exception:
        return {}


def _stable(path):
    try:
        first = path.stat()
        time.sleep(0.35)
        second = path.stat()
        return (first.st_size, first.st_mtime_ns) == (second.st_size, second.st_mtime_ns)
    except FileNotFoundError:
        return False


def _invoke_helper(name, args, response):
    response.unlink(missing_ok=True)
    command = [sys.executable, str(Path(__file__).with_name(name)), *map(str, args), str(response)]
    environment = dict(os.environ)
    environment["PYTHONPATH"] = str(Path(__file__).parent) + os.pathsep + environment.get("PYTHONPATH", "")
    result = subprocess.run(command, env=environment)
    if result.returncode != 0 or not response.exists():
        raise RuntimeError(f"Диалог {name} отменён или завершился с ошибкой")
    return json.loads(response.read_text(encoding="utf-8"))


def _select_roi(source):
    return _invoke_helper("roi_dialog.py", [source], TMP / "roi_response.json")


def _confirm_holes(source, roi):
    return _invoke_helper("hole_confirmation_dialog.py", [source, json.dumps(list(roi))], TMP / "hole_response.json")


def _manual(defaults):
    request = TMP / "geometry_request.json"
    response = TMP / "geometry_response.json"
    _atomic_json(request, defaults)
    return _invoke_helper("geometry_dialog.py", [request], response)


def _parse_dims(source):
    candidates = []
    for path in (source.with_name(source.stem + "_ocr_dimensions.json"), source.with_suffix(".json")):
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                candidates.extend(float(value) for value in data.get("dimensions", []) if float(value) > 0)
            except Exception:
                pass
    try:
        text = holes._ocr_text(source)
        candidates.extend(float(value.replace(",", ".")) for value in re.findall(r"(?<![A-Za-z])\d+(?:[.,]\d+)?", text))
    except Exception:
        pass
    values = sorted({value for value in candidates if 10 <= value <= 100000}, reverse=True)
    return (values[0], values[1]) if len(values) >= 2 else (None, None)


def _hole_defaults(circles, bbox, width, height):
    bx, by, bw, bh = map(float, bbox)
    result = []
    for circle in circles:
        nx = (float(circle["x"]) - bx) / max(1.0, bw)
        ny = 1.0 - (float(circle["y"]) - by) / max(1.0, bh)
        if -0.03 <= nx <= 1.03 and -0.03 <= ny <= 1.03:
            result.append({"x": round(min(1, max(0, nx)) * width, 3), "y": round(min(1, max(0, ny)) * height, 3)})
    return result


def _defaults(source, confirmed, outline):
    width, height = _parse_dims(source)
    width, height = width or 1040.0, height or 710.0
    diameter = float(confirmed.get("diameter") or holes.read_diameter(source) or 10.0)
    specs = _hole_defaults(confirmed.get("circles", []), outline["bbox"], width, height)
    count = int(confirmed.get("count", len(specs)))
    specs = specs[:count]
    while len(specs) < count:
        index = len(specs)
        specs.append({"x": round(width * (index + 1) / (count + 1), 3), "y": round(height / 2, 3)})
    return {"width": width, "height": height, "count": count, "diameter": diameter, "holes": specs, "cutout_mode": "Без открытых вырезов"}


def _resolved_outline(answer, detected):
    width, height = float(answer["width"]), float(answer["height"])
    measurements = dict(answer)
    measurements["contour_points"] = detected.get("points", [])
    absolute = build_contour_from_measurements(measurements)
    normalized = [[float(x) / width, float(y) / height] for x, y in absolute]
    result = dict(detected)
    result["points"] = normalized
    result["mode"] = answer.get("cutout_mode", "Без открытых вырезов")
    result["rectified"] = result["mode"] == "Без открытых вырезов" and len(normalized) == 4
    return result


def _geometry(model, width, height, specs, diameter, outline):
    points = [(float(x) * width, float(y) * height) for x, y in outline.get("points", [])]
    if len(points) < 4:
        points = [(0, 0), (width, 0), (width, height), (0, height)]
    model.add_lwpolyline(points, close=True, dxfattribs={"layer": "CUT"})
    for point in specs:
        model.add_circle((point["x"], point["y"]), diameter / 2, dxfattribs={"layer": "HOLES"})


def _dim_horizontal(model, p1, p2, base, text, style):
    x1, y1 = p1
    x2, y2 = p2
    model.add_line((x1, y1), (x1, base), dxfattribs={"layer": "DIM"})
    model.add_line((x2, y2), (x2, base), dxfattribs={"layer": "DIM"})
    model.add_linear_dim(base=(0, base - y1), p1=p1, p2=p2, angle=0, text=text, dimstyle=style, dxfattribs={"layer": "DIM"}).render()


def _dim_vertical(model, p1, p2, base, text, style):
    x1, y1 = p1
    x2, y2 = p2
    model.add_line((x1, y1), (base, y1), dxfattribs={"layer": "DIM"})
    model.add_line((x2, y2), (base, y2), dxfattribs={"layer": "DIM"})
    model.add_linear_dim(base=(base - x1, 0), p1=p1, p2=p2, angle=90, text=text, dimstyle=style, dxfattribs={"layer": "DIM"}).render()


def _add_info_labels(model, width, height, specs, diameter, offset):
    text_height = max(3, min(width, height) * 0.018)
    row_spacing = text_height * 1.8
    edge_gap = max(offset, text_height * 3)
    column_width = max(width * 0.28, text_height * 24)
    rows = max(1, int(max(height, row_spacing) // row_spacing))
    ordered = sorted(enumerate(specs, 1), key=lambda item: item[1]["y"], reverse=True)
    for position, (index, point) in enumerate(ordered):
        column, row = divmod(position, rows)
        label_x = width + edge_gap + column * column_width
        label_y = height - text_height - row * row_spacing
        elbow_x = width + edge_gap * 0.45
        model.add_lwpolyline(
            [
                (point["x"] + diameter / 2, point["y"]),
                (elbow_x, label_y),
                (label_x - text_height, label_y),
            ],
            dxfattribs={"layer": "TEXT"},
        )
        model.add_text(
            f"H{index}: X={point['x']:g} Y={point['y']:g} DIA{diameter:g}",
            dxfattribs={"layer": "TEXT", "height": text_height, "insert": (label_x, label_y)},
        )


def _write(path, width, height, specs, diameter, outline, info):
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 4
    for name, color in (("CUT", 7), ("HOLES", 1), ("DIM", 3), ("TEXT", 2)):
        doc.layers.new(name, dxfattribs={"color": color})
    model = doc.modelspace()
    _geometry(model, width, height, specs, diameter, outline)
    if info:
        style = "DXF_INFO"
        doc.dimstyles.new(style, dxfattribs={"dimtxt": max(3, min(width, height) * 0.025), "dimasz": max(2, min(width, height) * 0.015), "dimexe": 1.5, "dimexo": 1.0, "dimgap": 1.0})
        offset = max(25, min(width, height) * 0.12)
        _dim_horizontal(model, (0, 0), (width, 0), -offset, f"{width:g}", style)
        _dim_vertical(model, (0, 0), (0, height), -offset, f"{height:g}", style)
        _add_info_labels(model, width, height, specs, diameter, offset)
    temporary = path.with_suffix(".tmp.dxf")
    doc.saveas(temporary)
    temporary.replace(path)


def _validate(path, count):
    try:
        doc = ezdxf.readfile(path)
        model = doc.modelspace()
        cut = sum(1 for entity in model if entity.dxf.layer == "CUT")
        found = sum(1 for entity in model if entity.dxf.layer == "HOLES" and entity.dxftype() == "CIRCLE")
        errors = [str(error) for error in doc.audit().errors]
        units_mm = int(doc.header.get("$INSUNITS", 0)) == 4
        return {"valid": cut == 1 and found == count and units_mm and not errors, "summary": f"CUT={cut}, HOLES={found}/{count}, mm={units_mm}", "errors": errors, "warnings": [], "metrics": {"cut_entities": cut, "hole_entities": found}}
    except Exception as error:
        return {"valid": False, "summary": "DXF validation failed", "errors": [str(error)], "warnings": [], "metrics": {}}


def _done_target(source):
    target = DONE / source.name
    return target if not target.exists() else DONE / f"{source.stem}_{int(time.time())}{source.suffix}"


def process(source):
    roi = tuple(map(int, _select_roi(source)["roi"]))
    detected = extract_outline(source, roi)
    confirmed = _confirm_holes(source, roi)
    answer = _manual(_defaults(source, confirmed, detected))
    width, height = float(answer["width"]), float(answer["height"])
    count, diameter, specs = int(answer["count"]), float(answer["diameter"]), list(answer["holes"])
    outline = _resolved_outline(answer, detected)
    base = OUTBOX / source.stem
    clear = base.with_name(base.name + "_dxf_clear.dxf")
    info = base.with_name(base.name + "_dxf_info.dxf")
    _write(clear, width, height, specs, diameter, outline, False)
    _write(info, width, height, specs, diameter, outline, True)
    report = {"source": str(source), "roi": roi, "cutout_mode": outline["mode"], "rectified": outline["rectified"], "outline_confidence": detected["confidence"], "detected_outline_vertices": len(detected["points"]), "output_outline_vertices": len(outline["points"]), "width": width, "height": height, "count": count, "diameter": diameter, "clear": _validate(clear, count), "info": _validate(info, count)}
    _atomic_json(base.with_name(base.name + "_report.json"), report)
    DONE.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(_done_target(source)))
    print(f"Готово: {clear.name}, {info.name}", flush=True)


def main():
    for folder in (INBOX, DONE, OUTBOX, TMP):
        folder.mkdir(parents=True, exist_ok=True)
    state = _state()
    print(f"Вход: {INBOX}", flush=True)
    print(f"Выход: {OUTBOX}", flush=True)
    while True:
        for source in sorted(INBOX.iterdir()):
            if not source.is_file() or source.suffix.lower() not in SUPPORTED:
                continue
            try:
                stamp = f"{source.stat().st_mtime_ns}:{source.stat().st_size}"
            except FileNotFoundError:
                continue
            key = str(source.resolve())
            if state.get(key) == stamp or not _stable(source):
                continue
            try:
                process(source)
                state.pop(key, None)
            except Exception as error:
                print(f"Ошибка {source.name}: {error}", file=sys.stderr, flush=True)
                state[key] = stamp
            _atomic_json(STATE_FILE, state)
        time.sleep(POLL)


if __name__ == "__main__":
    main()
