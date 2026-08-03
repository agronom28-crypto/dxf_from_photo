"""Verified photo-to-DXF watcher with edge-based hole dimensions."""
from __future__ import annotations

import json
import os
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


def _ocr_numbers(source):
    try:
        import cv2, pytesseract
        image = cv2.imread(str(source))
        if image is None: return []
        text = pytesseract.image_to_string(image, config="--psm 11", lang="rus+eng")
        return [float(value.replace(",", ".")) for value in NUMBER.findall(text)]
    except (ImportError, RuntimeError, ValueError):
        return []


def _dimension_defaults(numbers, roi):
    large = sorted({value for value in numbers if value >= 50}, reverse=True)
    if len(large) >= 2:
        first, second = large[:2]
        portrait = roi is None or roi[3] >= roi[2]
        width, height = ((min(first, second), max(first, second)) if portrait else (max(first, second), min(first, second)))
    else:
        width, height = 395.0, 830.0
    small = [value for value in numbers if 0 < value < min(width, height) * .25]
    return width, height, small


def _hole_distance_defaults(circles, roi, width, height, small):
    fallback = small[0] if small else 20.0
    result = []
    if roi is None:
        return [(fallback, fallback) for _ in circles]
    x0, y0, rw, rh = roi
    for circle in circles:
        nx = min(1.0, max(0.0, (circle.x - x0) / max(rw, 1)))
        ny = min(1.0, max(0.0, (y0 + rh - circle.y) / max(rh, 1)))
        dx = min(nx * width, (1 - nx) * width)
        dy = min(ny * height, (1 - ny) * height)
        if small: dx = small[0]
        if len(small) > 1: dy = small[1]
        elif small: dy = small[0]
        result.append((max(0.0, dx), max(0.0, dy)))
    return result


def _ask_geometry(width, height, distances, diameter):
    try:
        import tkinter as tk
        from tkinter import messagebox, ttk
        root = tk.Tk()
    except (ImportError, tk.TclError if "tk" in locals() else RuntimeError) as error:
        raise RuntimeError("Не удалось открыть окно подтверждения размеров") from error

    root.title("Размеры и привязка отверстий")
    root.attributes("-topmost", True)
    root.lift(); root.focus_force()
    answer = {}
    width_var = tk.StringVar(value=f"{width:g}")
    height_var = tk.StringVar(value=f"{height:g}")
    tk.Label(root, text="Проверьте размеры и расстояния от размерных линий", font=("Arial", 15, "bold")).grid(row=0, column=0, columnspan=6, padx=14, pady=10)
    tk.Label(root, text="Ширина, мм").grid(row=1, column=0, sticky="e"); tk.Entry(root, textvariable=width_var, width=12).grid(row=1, column=1)
    tk.Label(root, text="Высота, мм").grid(row=1, column=2, sticky="e"); tk.Entry(root, textvariable=height_var, width=12).grid(row=1, column=3)
    controls = []
    for index, (dx, dy) in enumerate(distances, 1):
        hside = tk.StringVar(value="справа"); vside = tk.StringVar(value="снизу")
        hdist = tk.StringVar(value=f"{dx:.1f}"); vdist = tk.StringVar(value=f"{dy:.1f}")
        controls.append((hside, hdist, vside, vdist)); row = index + 1
        tk.Label(root, text=f"Отверстие {index}: от").grid(row=row, column=0, sticky="e", pady=4)
        ttk.Combobox(root, textvariable=hside, values=("слева", "справа"), state="readonly", width=8).grid(row=row, column=1)
        tk.Entry(root, textvariable=hdist, width=9).grid(row=row, column=2); tk.Label(root, text="мм; от").grid(row=row, column=3)
        ttk.Combobox(root, textvariable=vside, values=("снизу", "сверху"), state="readonly", width=8).grid(row=row, column=4)
        tk.Entry(root, textvariable=vdist, width=9).grid(row=row, column=5)
    last = len(controls) + 2
    tk.Label(root, text=f"Диаметр: {diameter:g} мм").grid(row=last, column=0, columnspan=6, pady=5)

    def finish():
        try:
            w = float(width_var.get().replace(",", ".")); h = float(height_var.get().replace(",", "."))
            if w <= 0 or h <= 0: raise ValueError
            centers = []
            for hside, hdist, vside, vdist in controls:
                dx = float(hdist.get().replace(",", ".")); dy = float(vdist.get().replace(",", "."))
                x = dx if hside.get() == "слева" else w - dx
                y = dy if vside.get() == "снизу" else h - dy
                if dx < 0 or dy < 0 or not (0 <= x <= w and 0 <= y <= h): raise ValueError
                centers.append((x, y))
        except ValueError:
            messagebox.showerror("Ошибка", "Расстояния должны быть неотрицательными и не выходить за контур", parent=root); return
        answer.update(width=w, height=h, centers=centers); root.quit()

    def cancel(): root.quit()
    tk.Button(root, text="Создать чистый DXF", command=finish, bg="#2e7d32", fg="white", font=("Arial", 13)).grid(row=last+1, column=0, columnspan=3, padx=6, pady=12)
    tk.Button(root, text="Отмена", command=cancel, font=("Arial", 13)).grid(row=last+1, column=3, columnspan=3, padx=6, pady=12)
    root.protocol("WM_DELETE_WINDOW", cancel); root.grab_set()
    try: root.mainloop()
    finally:
        try: root.grab_release()
        except tk.TclError: pass
        root.destroy()
    return answer or None


def _write_dxf(path, width, height, centers, diameter):
    import ezdxf
    document = ezdxf.new("R12"); document.header["$INSUNITS"] = 4
    for name, color in (("CUT", 7), ("HOLES", 1), ("HOLE_INFO", 3)):
        if name not in document.layers: document.layers.add(name, color=color)
    model = document.modelspace()
    model.add_polyline2d([(0, 0), (width, 0), (width, height), (0, height)], close=True, dxfattribs={"layer": "CUT"})
    for center in centers: model.add_circle(center, diameter / 2, dxfattribs={"layer": "HOLES"})
    model.add_text(f"{len(centers)} HOLE DIA {diameter:g} mm", dxfattribs={"layer": "HOLE_INFO", "height": 5, "insert": (0, height + 10)})
    temporary = path.with_suffix(".tmp.dxf"); document.saveas(temporary)
    entities = list(ezdxf.readfile(temporary).modelspace())
    cuts = [e for e in entities if e.dxftype() == "POLYLINE" and e.dxf.layer == "CUT"]
    found = [e for e in entities if e.dxftype() == "CIRCLE" and e.dxf.layer == "HOLES"]
    if len(cuts) != 1 or len(found) != len(centers):
        temporary.unlink(missing_ok=True); raise RuntimeError("Проверка DXF не пройдена")
    temporary.replace(path)


def _archive(source):
    DONE.mkdir(parents=True, exist_ok=True); target = DONE / source.name
    if target.exists(): target = DONE / f"{source.stem}_{int(time.time())}{source.suffix}"
    shutil.move(str(source), str(target)); return target


def process(source):
    OUTPUT.mkdir(parents=True, exist_ok=True)
    circles, image = holes.detect_holes(source)
    if image is None: raise RuntimeError("Не удалось открыть изображение")
    confirmed = holes.confirm_holes(image, circles, holes.read_diameter(source))
    if confirmed is None: raise holes.ClarificationRequired("Отверстия не подтверждены")
    selected = [circles[i] for i in confirmed["active"] if 0 <= i < len(circles)]
    if confirmed["count"] != len(selected): raise holes.ClarificationRequired("Количество не совпадает с выбранными отметками")
    roi = holes._automatic_figure_roi(image)
    if roi is None: roi = holes._manual_figure_roi(image)
    width, height, small = _dimension_defaults(_ocr_numbers(source), roi)
    distances = _hole_distance_defaults(selected, roi, width, height, small)
    geometry = _ask_geometry(width, height, distances, confirmed["diameter"])
    if geometry is None: raise holes.ClarificationRequired("Размеры не подтверждены")
    final = OUTPUT / f"{source.stem}_FINAL.dxf"
    _write_dxf(final, geometry["width"], geometry["height"], geometry["centers"], confirmed["diameter"])
    archived = _archive(source)
    record = {"status": "done", "source": str(source), "archived_to": str(archived), "dxf": final.name, "width": geometry["width"], "height": geometry["height"], "diameter": confirmed["diameter"], "holes": [{"x": x, "y": y} for x, y in geometry["centers"]]}
    (OUTPUT / f"{source.stem}_result.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")


def _single_instance():
    import fcntl
    handle = (ROOT / ".watcher.lock").open("w")
    try: fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as error: raise RuntimeError("Обработчик уже запущен. Завершите прежний процесс Python.") from error
    handle.write(str(os.getpid())); handle.flush(); return handle


def main():
    lock = _single_instance()
    INBOX.mkdir(parents=True, exist_ok=True); DONE.mkdir(parents=True, exist_ok=True); OUTPUT.mkdir(parents=True, exist_ok=True)
    signatures, paused = {}, set(); print(f"Слушаю: {INBOX}")
    while True:
        current = [p for p in INBOX.iterdir() if p.is_file() and p.suffix.lower() in EXTENSIONS]
        for source in current:
            stat = source.stat(); signature = (stat.st_size, stat.st_mtime_ns)
            if source in paused:
                if signatures.get(source) == signature: continue
                paused.remove(source)
            if signatures.get(source) != signature: signatures[source] = signature; continue
            try: process(source); signatures.pop(source, None); print(f"Готово: {source.name}")
            except holes.ClarificationRequired as error: paused.add(source); print(f"Приостановлено: {error}")
            except Exception as error:
                paused.add(source); (OUTPUT / f"{source.stem}_error.json").write_text(json.dumps({"status": "error", "message": str(error)}, ensure_ascii=False, indent=2), encoding="utf-8"); print(f"Ошибка: {source.name}: {error}")
        time.sleep(1)


if __name__ == "__main__": main()
