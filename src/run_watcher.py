"""Fail-safe launcher producing one compatible DXF with confirmed holes."""
from __future__ import annotations

import json
import os
import runpy
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import sitecustomize  # noqa: F401,E402
import hole_diameter_clarification as hole_info  # noqa: E402

_original_resolve = hole_info.resolve
_last_holes = {"circles": [], "roi": None}


def _capture_resolve(source, output):
    spec = _original_resolve(source, output)
    _last_holes.update(circles=[], roi=None)
    if spec is None:
        return None
    source = Path(source)
    saved = Path(output) / f"{source.stem}_hole_diameter.json"
    try:
        data = json.loads(saved.read_text(encoding="utf-8"))
        selected = [int(number) - 1 for number in data.get("selected_marks", [])]
        circles, image = hole_info.detect_holes(source)
        roi = hole_info._automatic_figure_roi(image) if image is not None else None
        _last_holes["circles"] = [circles[index] for index in selected if 0 <= index < len(circles)]
        _last_holes["roi"] = roi
    except (OSError, ValueError, KeyError, IndexError):
        pass
    return spec


def _cut_bounds(model):
    points = []
    for entity in model:
        if entity.dxf.layer != "CUT":
            continue
        kind = entity.dxftype()
        if kind == "POLYLINE":
            points.extend((point.x, point.y) for point in entity.points())
        elif kind == "LWPOLYLINE":
            points.extend((point[0], point[1]) for point in entity.get_points("xy"))
        elif kind == "LINE":
            points.extend(((entity.dxf.start.x, entity.dxf.start.y), (entity.dxf.end.x, entity.dxf.end.y)))
    if not points:
        return None
    xs, ys = zip(*points)
    return min(xs), min(ys), max(xs), max(ys)


def _source_dxf(path):
    path = Path(path)
    clear = path.with_name(path.name.replace("_dxf_info.dxf", "_dxf_clear.dxf"))
    return clear if clear.exists() else path


def _write_final_dxf(path, spec) -> None:
    try:
        import ezdxf
    except ImportError as error:
        raise RuntimeError("Для записи диаметра требуется ezdxf") from error

    path = Path(path)
    document = ezdxf.readfile(_source_dxf(path))
    model = document.modelspace()
    if "HOLES" not in document.layers:
        document.layers.add("HOLES", color=1)
    if "HOLE_INFO" not in document.layers:
        document.layers.add("HOLE_INFO", color=3)

    bounds = _cut_bounds(model)
    roi = _last_holes.get("roi")
    circles = _last_holes.get("circles", [])
    if bounds and roi and circles:
        x0, y0, width, height = roi
        min_x, min_y, max_x, max_y = bounds
        for circle in circles:
            x = min_x + (circle.x - x0) / max(width, 1) * (max_x - min_x)
            y = max_y - (circle.y - y0) / max(height, 1) * (max_y - min_y)
            model.add_circle((x, y), spec.diameter / 2.0, dxfattribs={"layer": "HOLES"})

    model.add_text(
        f"{spec.count} HOLE DIA {spec.diameter:g} mm",
        dxfattribs={"layer": "HOLE_INFO", "height": 5, "insert": (0, 10)},
    )
    document.saveas(path)


hole_info.resolve = _capture_resolve
hole_info.add_to_info_dxf = _write_final_dxf

if os.environ.get("DXF_PHOTO_COMPAT_ACTIVE") != "1":
    raise RuntimeError("Слой совместимости DXF не загрузился")

runpy.run_path(str(SRC / "inbox_watcher.py"), run_name="__main__")
