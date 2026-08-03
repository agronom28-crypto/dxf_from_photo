"""Photo-to-DXF watcher: verified geometry, clean and dimensioned outputs."""
from __future__ import annotations

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
        return ((min(first, second), max(first, second)) if portrait else (max(first, second), min(first, second))), [value for value in numbers if 0 < value < min(first, second) * .25]
    return (395.0, 830.0), [value for value in numbers if 0 < value < 100]


def _distance_defaults(circles, roi, width, height, small):
    result = []
    for circle in circles:
        if roi is None:
            h_side, v_side, dx, dy = "справа", "снизу", 20.0, 20.0
        else:
            x0, y0, rw, rh = roi
            nx = min(1.0, max(0.0, (circle.x - x0) / max(rw, 1)))
            ny = min(1.0, max(0.0, (y0 + rh - circle.y) / max(rh, 1)))
            h_side = "слева" if nx < .5 else "справа"
            v_side = "снизу" if ny < .5 else "сверху"
            dx = min(nx, 1 - nx) * width
            dy = min(ny, 1 - ny) * height
        if small:
            dx = small[0]
            dy = small[1] if len(small) > 1 else small[0]
        result.append((h_side, max(0, dx), v_side, max(0, dy)))
    return result


def _ask_geometry(width, height, defaults, diameter):
    try:
        import tkinter as tk
        from tkinter import messagebox, ttk
    except ImportError as error:
        raise RuntimeError("Для подтверждения размеров требуется tkinter") from error
    try:
        root = tk.Tk()
    except tk.TclError as error:
        raise RuntimeError("Не удалось открыть окно подтверждения размеров") from error

    root.title("Размеры и привязка отверстий")
    root.attributes("-topmost", True)
    result = {}
    width_var = tk.StringVar(value=f"{width:g}")
    height_var = tk.StringVar(value=f"{height:g}")
    tk.Label(root, text="Размеры и расстояния от размерных линий", font=("Arial", 15, "bold")).grid(row=0, column=0, columnspan=6, padx=14, pady=10)
    tk.Label(root, text="Ширина, мм").grid(row=1, column=0, sticky="e")
    tk.Entry(root, textvariable=width_var, width=12).grid(row=1, column=1)
    tk.Label(root, text="Высота, мм").grid(row=1, column=2, sticky="e")
    tk.Entry(root, textvariable=height_var, width=12).grid(row=1, column=3)
    controls = []
    for index, (hs, dx, vs, dy) in enumerate(defaults, 1):
        h_side = tk.StringVar(value=hs)
        h_distance = tk.StringVar(value=f"{dx:.1f}")
        v_side = tk.StringVar(value=vs)
        v_distance = tk.StringVar(value=f"{dy:.1f}")
        controls.append((h_side, h_distance, v_side, v_distance))
        row = index + 1
        tk.Label(root, text=f"Отверстие {index}: от").grid(row=row, column=0, sticky="e", pady=4)
        ttk.Combobox(root, textvariable=h_side, values=("слева", "справа"), state="readonly", width=8).grid(row=row, column=1)
        tk.Entry(root, textvariable=h_distance, width=9).grid(row=row, column=2)
        tk.Label(root, text="мм; от").grid(row=row, column=3)
        ttk.Combobox(root, textvariable=v_side, values=("снизу", "сверху"), state="readonly", width=8).grid(row=row, column=4)
        tk.Entry(root, textvariable=v_distance, width=9).grid(row=row, column=5)
    last = len(controls) + 2
    tk.Label(root, text=f"Диаметр отверстий: {diameter:g} мм").grid(row=last, column=0, columnspan=6, pady=6)

    def close_window():
        try:
            root.grab_release()
        except tk.TclError:
            pass
        root.destroy()

    def accept():
        try:
            confirmed_width = float(width_var.get().replace(",", "."))
            confirmed_height = float(height_var.get().replace(",", "."))
            if confirmed_width <= 0 or confirmed_height <= 0:
                raise ValueError
            confirmed_holes = []
            for h_side, h_distance, v_side, v_distance in controls:
                dx = float(h_distance.get().replace(",", "."))
                dy = float(v_distance.get().replace(",", "."))
                x = dx if h_side.get() == "слева" else confirmed_width - dx
                y = dy if v_side.get() == "снизу" else confirmed_height - dy
                if dx < 0 or dy < 0 or not (0 <= x <= confirmed_width and 0 <= y <= confirmed_height):
                    raise ValueError
                confirmed_holes.append({"x": x, "y": y, "h_side": h_side.get(), "h_distance": dx, "v_side": v_side.get(), "v_distance": dy})
        except ValueError:
            messagebox.showerror("Ошибка", "Проверьте размеры: отверстия должны находиться внутри контура", parent=root)
            return
        result.update(width=confirmed_width, height=confirmed_height, holes=confirmed_holes)
        close_window()

    tk.Button(root, text="Создать DXF", command=accept, bg="#2e7d32", fg="white", font=("Arial", 13)).grid(row=last + 1, column=0, columnspan=3, padx=6, pady=12)
    tk.Button(root, text="Отмена", command=close_window, font=("Arial", 13)).grid(row=last + 1, column=3, columnspan=3, padx=6, pady=12)
    root.protocol("WM_DELETE_WINDOW", close_window)
    root.update_idletasks()
    root.lift()
    root.focus_force()
    root.grab_set()
    root.wait_window()
    return result or None


def _new_document():
    import ezdxf
    document = ezdxf.new("R12")
    document.header["$INSUNITS"] = 4
    for name, color in (("CUT", 7), ("HOLES", 1), ("DIM", 3), ("TEXT", 2)):
        if name not in document.layers:
            document.layers.add(name, color=color)
    return document


def _add_geometry(model, width, height, hole_specs, diameter):
    model.add_polyline2d([(0, 0), (width, 0), (width, height), (0, height)], close=True, dxfattribs={"layer": "CUT"})
    for hole in hole_specs:
        model.add_circle((hole["x"], hole["y"]), diameter / 2, dxfattribs={"layer": "HOLES"})


def _line(model, start, end):
    model.add_line(start, end, dxfattribs={"layer": "DIM"})


def _text(model, value, point, height=5):
    model.add_text(value, dxfattribs={"layer": "TEXT", "height": height, "insert": point})


def _add_dimensions(model, width, height, hole_specs, diameter):
    offset = max(15.0, min(width, height) * .05)
    _line(model, (0, -offset), (width, -offset))
    _line(model, (0, 0), (0, -offset * 1.25))
    _line(model, (width, 0), (width, -offset * 1.25))
    _text(model, f"WIDTH {width:g} mm", (width * .35, -offset * .85))
    _line(model, (width + offset, 0), (width + offset, height))
    _line(model, (width, 0), (width + offset * 1.25, 0))
    _line(model, (width, height), (width + offset * 1.25, height))
    _text(model, f"HEIGHT {height:g} mm", (width + offset * 1.15, height * .45))
    for index, hole in enumerate(hole_specs, 1):
        x, y = hole["x"], hole["y"]
        h_edge = 0 if hole["h_side"] == "слева" else width
        v_edge = 0 if hole["v_side"] == "снизу" else height
        _line(model, (h_edge, y), (x, y))
        _line(model, (x, v_edge), (x, y))
        label = f"H{index}: DIA {diameter:g}; {hole['h_distance']:g} FROM {hole['h_side'].upper()}; {hole['v_distance']:g} FROM {hole['v_side'].upper()}"
        _text(model, label, (x + diameter, y + diameter + index * 2), max(3.0, min(width, height) * .012))


def _validate(path, expected_holes, allow_dimensions):
    import ezdxf
    entities = list(ezdxf.readfile(path).modelspace())
    cuts = [entity for entity in entities if entity.dxftype() == "POLYLINE" and entity.dxf.layer == "CUT"]
    circles = [entity for entity in entities if entity.dxftype() == "CIRCLE" and entity.dxf.layer == "HOLES"]
    dimensions = [entity for entity in entities if entity.dxf.layer in {"DIM", "TEXT"}]
    if len(cuts) != 1 or len(circles) != expected_holes:
        raise RuntimeError("Проверка DXF не пройдена: неверный контур или отверстия")
    if not allow_dimensions and dimensions:
        raise RuntimeError("В чистом DXF обнаружены размерные элементы")
    if allow_dimensions and not dimensions:
        raise RuntimeError("В информационном DXF отсутствуют размеры")


def _write_outputs(stem, width, height, hole_specs, diameter):
    OUTPUT.mkdir(parents=True, exist_ok=True)
    clear_path = OUTPUT / f"{stem}_dxf_clear.dxf"
    info_path = OUTPUT / f"{stem}_dxf_info.dxf"
    clear_tmp = OUTPUT / f".{stem}_clear.tmp.dxf"
    info_tmp = OUTPUT / f".{stem}_info.tmp.dxf"
    clear_document = _new_document()
    _add_geometry(clear_document.modelspace(), width, height, hole_specs, diameter)
    clear_document.saveas(clear_tmp)
    info_document = _new_document()
    _add_geometry(info_document.modelspace(), width, height, hole_specs, diameter)
    _add_dimensions(info_document.modelspace(), width, height, hole_specs, diameter)
    info_document.saveas(info_tmp)
    _validate(clear_tmp, len(hole_specs), False)
    _validate(info_tmp, len(hole_specs), True)
    clear_tmp.replace(clear_path)
    info_tmp.replace(info_path)
    return clear_path, info_path


def _archive(source):
    DONE.mkdir(parents=True, exist_ok=True)
    target = DONE / source.name
    if target.exists():
        target = DONE / f"{source.stem}_{int(time.time())}{source.suffix}"
    shutil.move(str(source), str(target))


def process(source):
    circles, image = holes.detect_holes(source)
    if image is None:
        raise RuntimeError("Не удалось открыть изображение")
    confirmed = holes.confirm_holes(image, circles, holes.read_diameter(source))
    if confirmed is None:
        raise holes.ClarificationRequired("Отверстия не подтверждены")
    selected = [circles[index] for index in confirmed["active"] if 0 <= index < len(circles)]
    if confirmed["count"] != len(selected):
        raise holes.ClarificationRequired("Количество отверстий не совпадает с выбранными отметками")
    roi = holes._automatic_figure_roi(image)
    if roi is None:
        roi = holes._manual_figure_roi(image)
    (width, height), small = _dimension_defaults(_ocr_numbers(source), roi)
    defaults = _distance_defaults(selected, roi, width, height, small)
    geometry = _ask_geometry(width, height, defaults, confirmed["diameter"])
    if geometry is None:
        raise holes.ClarificationRequired("Размеры не подтверждены")
    _write_outputs(source.stem, geometry["width"], geometry["height"], geometry["holes"], confirmed["diameter"])
    _archive(source)


def _single_instance():
    import fcntl
    handle = (ROOT / ".watcher.lock").open("w")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as error:
        raise RuntimeError("Обработчик уже запущен") from error
    handle.write(str(os.getpid()))
    handle.flush()
    return handle


def main():
    lock = _single_instance()
    INBOX.mkdir(parents=True, exist_ok=True)
    DONE.mkdir(parents=True, exist_ok=True)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    signatures, paused = {}, set()
    print(f"Слушаю: {INBOX}")
    while True:
        for source in [path for path in INBOX.iterdir() if path.is_file() and path.suffix.lower() in EXTENSIONS]:
            stat = source.stat()
            signature = (stat.st_size, stat.st_mtime_ns)
            if source in paused:
                if signatures.get(source) == signature:
                    continue
                paused.remove(source)
            if signatures.get(source) != signature:
                signatures[source] = signature
                continue
            try:
                process(source)
                signatures.pop(source, None)
                print(f"Готово: {source.name}")
            except holes.ClarificationRequired as error:
                paused.add(source)
                print(f"Приостановлено: {error}")
            except Exception as error:
                paused.add(source)
                print(f"Ошибка: {source.name}: {error}")
        time.sleep(1)


if __name__ == "__main__":
    main()
