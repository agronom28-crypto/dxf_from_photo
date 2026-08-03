"""Production watcher: clean parametric contour, confirmed holes, and _done archive."""
from __future__ import annotations

import json
import re
import shutil
import time
from pathlib import Path

import hole_diameter_clarification as holes

ROOT = Path(__file__).resolve().parent.parent
INBOX = ROOT / "новые фотографии"
OUTPUT = ROOT / "DXF"
DONE = INBOX / "_done"
EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".heic"}
NUMBER = re.compile(r"(?<!\d)(\d+(?:[.,]\d+)?)(?!\d)")


def _ocr_numbers(source: Path) -> list[float]:
    try:
        import cv2
        import pytesseract
        image = cv2.imread(str(source))
        if image is None:
            return []
        text = pytesseract.image_to_string(image, config="--psm 11", lang="rus+eng")
        return [float(value.replace(",", ".")) for value in NUMBER.findall(text)]
    except (ImportError, RuntimeError, ValueError):
        return []


def _dimension_defaults(numbers, roi):
    large = sorted({value for value in numbers if value >= 50}, reverse=True)
    if len(large) >= 2:
        first, second = large[:2]
        portrait = roi is None or roi[3] >= roi[2]
        width, height = (min(first, second), max(first, second)) if portrait else (max(first, second), min(first, second))
    else:
        width, height = 395.0, 830.0
    small = [value for value in numbers if 0 < value < min(width, height) * 0.25]
    return width, height, small


def _hole_defaults(circles, roi, width, height, small):
    result = []
    if roi is None:
        return [(width / 2, height / 2) for _ in circles]
    x0, y0, rw, rh = roi
    for circle in circles:
        nx = min(1.0, max(0.0, (circle.x - x0) / max(rw, 1)))
        ny = min(1.0, max(0.0, (y0 + rh - circle.y) / max(rh, 1)))
        x, y = nx * width, ny * height
        if small and nx > 0.6:
            x = width - small[0]
        if small and ny < 0.4:
            y = small[1] if len(small) > 1 else small[0]
        result.append((x, y))
    return result


def _ask_geometry(width, height, centers, diameter):
    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk(); root.title("Размеры чистого контура")
        tk.Label(root, text="Проверьте размеры детали и координаты отверстий", font=("Arial", 15, "bold")).grid(row=0, column=0, columnspan=4, padx=12, pady=10)
        width_var = tk.StringVar(value=f"{width:g}"); height_var = tk.StringVar(value=f"{height:g}")
        tk.Label(root, text="Ширина детали, мм:").grid(row=1, column=0, sticky="e"); tk.Entry(root, textvariable=width_var).grid(row=1, column=1)
        tk.Label(root, text="Высота детали, мм:").grid(row=1, column=2, sticky="e"); tk.Entry(root, textvariable=height_var).grid(row=1, column=3)
        vars_xy = []
        for index, (x, y) in enumerate(centers, 1):
            xv = tk.StringVar(value=f"{x:.1f}"); yv = tk.StringVar(value=f"{y:.1f}"); vars_xy.append((xv, yv))
            tk.Label(root, text=f"Отверстие {index}: X от левого края, мм").grid(row=index+1, column=0, sticky="e", pady=3); tk.Entry(root, textvariable=xv).grid(row=index+1, column=1)
            tk.Label(root, text="Y от нижнего края, мм").grid(row=index+1, column=2, sticky="e"); tk.Entry(root, textvariable=yv).grid(row=index+1, column=3)
        tk.Label(root, text=f"Диаметр отверстий: {diameter:g} мм").grid(row=len(centers)+2, column=0, columnspan=4, pady=6)
        answer = {}
        def accept():
            try:
                w = float(width_var.get().replace(",", ".")); h = float(height_var.get().replace(",", ".")); points = [(float(x.get().replace(",", ".")), float(y.get().replace(",", "."))) for x, y in vars_xy]
                assert w > 0 and h > 0 and all(0 <= x <= w and 0 <= y <= h for x, y in points)
            except (ValueError, AssertionError):
                messagebox.showerror("Ошибка", "Размеры должны быть положительными, а отверстия — внутри детали"); return
            answer.update(width=w, height=h, centers=points); root.destroy()
        tk.Button(root, text="Создать чистый DXF", command=accept, bg="#2e7d32", fg="white", font=("Arial", 13)).grid(row=len(centers)+3, column=0, columnspan=4, pady=12)
        root.protocol("WM_DELETE_WINDOW", root.destroy); root.mainloop(); return answer or None
    except (ImportError, tk.TclError):
        return {"width": width, "height": height, "centers": centers}


def _write_dxf(path, width, height, centers, diameter):
    import ezdxf
    document = ezdxf.new("R12"); document.header["$INSUNITS"] = 4
    for name, color in (("CUT", 7), ("HOLES", 1), ("HOLE_INFO", 3)):
        if name not in document.layers: document.layers.add(name, color=color)
    model = document.modelspace()
    model.add_polyline2d([(0, 0), (width, 0), (width, height), (0, height)], close=True, dxfattribs={"layer": "CUT"})
    for center in centers: model.add_circle(center, diameter / 2.0, dxfattribs={"layer": "HOLES"})
    model.add_text(f"{len(centers)} HOLE DIA {diameter:g} mm", dxfattribs={"layer": "HOLE_INFO", "height": 5, "insert": (0, height + 10)})
    temporary = path.with_suffix(".tmp.dxf"); document.saveas(temporary)
    check = ezdxf.readfile(temporary); entities = list(check.modelspace()); cuts = [e for e in entities if e.dxftype() == "POLYLINE" and e.dxf.layer == "CUT"]; found = [e for e in entities if e.dxftype() == "CIRCLE" and e.dxf.layer == "HOLES"]
    if len(cuts) != 1 or len(found) != len(centers): temporary.unlink(missing_ok=True); raise RuntimeError("Проверка DXF не пройдена: неверный контур или количество отверстий")
    temporary.replace(path)


def _archive(source):
    DONE.mkdir(parents=True, exist_ok=True); target = DONE / source.name
    if target.exists(): target = DONE / f"{source.stem}_{int(time.time())}{source.suffix}"
    shutil.move(str(source), str(target)); return target


def process(source: Path):
    import cv2
    OUTPUT.mkdir(parents=True, exist_ok=True)
    circles, image = holes.detect_holes(source)
    if image is None: raise RuntimeError("Не удалось открыть изображение")
    answer = holes.confirm_holes(image, circles, holes.read_diameter(source))
    if answer is None: raise holes.ClarificationRequired("Не подтверждены отверстия и диаметр")
    selected = [circles[index] for index in answer["active"] if 0 <= index < len(circles)]
    if answer["count"] != len(selected): raise holes.ClarificationRequired("Количество должно совпадать с числом красных отметок")
    roi = holes._automatic_figure_roi(image) or holes._manual_figure_roi(image)
    numbers = _ocr_numbers(source); width, height, small = _dimension_defaults(numbers, roi); defaults = _hole_defaults(selected, roi, width, height, small)
    geometry = _ask_geometry(width, height, defaults, answer["diameter"])
    if geometry is None: raise holes.ClarificationRequired("Не подтверждены размеры детали")
    final = OUTPUT / f"{source.stem}_FINAL.dxf"; _write_dxf(final, geometry["width"], geometry["height"], geometry["centers"], answer["diameter"])
    record = {"source": str(source), "status": "done", "width": geometry["width"], "height": geometry["height"], "diameter": answer["diameter"], "holes": [{"x": x, "y": y} for x, y in geometry["centers"]], "dxf": final.name}
    archived = _archive(source); record["archived_to"] = str(archived); (OUTPUT / f"{source.stem}_result.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    INBOX.mkdir(parents=True, exist_ok=True); DONE.mkdir(parents=True, exist_ok=True); OUTPUT.mkdir(parents=True, exist_ok=True); observed = {}
    print(f"Слушаю: {INBOX}")
    while True:
        for source in [p for p in INBOX.iterdir() if p.is_file() and p.suffix.lower() in EXTENSIONS]:
            size = source.stat().st_size
            if observed.get(source) != size: observed[source] = size; continue
            try: process(source); observed.pop(source, None); print(f"Готово: {source.name}")
            except holes.ClarificationRequired as error: print(f"Ожидание уточнения: {error}")
            except Exception as error:
                (OUTPUT / f"{source.stem}_error.json").write_text(json.dumps({"source": str(source), "status": "error", "message": str(error), "failed_at": time.time()}, ensure_ascii=False, indent=2), encoding="utf-8"); print(f"Ошибка: {source.name}: {error}")
        time.sleep(1)


if __name__ == "__main__":
    main()
