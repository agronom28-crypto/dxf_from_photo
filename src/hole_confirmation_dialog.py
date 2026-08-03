import json
import os
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

import cv2
import numpy as np
from PIL import Image, ImageTk

import hole_diameter_clarification as holes

source = Path(sys.argv[1])
x0, y0, width, height = map(int, json.loads(sys.argv[2]))
response = Path(sys.argv[3])
image = cv2.imread(str(source))
if image is None:
    raise SystemExit(3)
crop = image[y0:y0 + height, x0:x0 + width]
if crop.size == 0:
    raise SystemExit(4)

gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
gray = cv2.createCLAHE(2.0, (8, 8)).apply(gray)
blur = cv2.GaussianBlur(gray, (5, 5), 1.2)
side = min(width, height)
minimum = max(2, int(side * 0.004))
maximum = max(minimum + 2, int(side * 0.035))
raw = []
for threshold in (24, 20, 17):
    found = cv2.HoughCircles(
        blur, cv2.HOUGH_GRADIENT, 1.2, max(12, int(side * 0.04)),
        param1=100, param2=threshold, minRadius=minimum, maxRadius=maximum,
    )
    if found is not None:
        for cx, cy, radius in found[0]:
            raw.append((float(cx), float(cy), float(radius), threshold))

candidates = []
for cx, cy, radius, score in sorted(raw, key=lambda item: -item[3]):
    if cx - radius < 3 or cy - radius < 3 or cx + radius > width - 3 or cy + radius > height - 3:
        continue
    yy, xx = np.ogrid[:height, :width]
    ring = np.abs(np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2) - radius) <= max(1.5, radius * 0.18)
    contrast = float(np.std(gray[ring])) if np.any(ring) else 0
    if contrast < 12:
        continue
    if any((px - cx) ** 2 + (py - cy) ** 2 < max(pr, radius, 8) ** 2 for px, py, pr, manual in candidates):
        continue
    candidates.append([cx, cy, radius, False])
    if len(candidates) >= 40:
        break

active = set(range(len(candidates)))
root = tk.Tk()
root.title("Подтверждение и добавление отверстий")
root.attributes("-topmost", True)
scale = min(1100 / width, 680 / height, 1.0)
shown = cv2.resize(crop, (int(width * scale), int(height * scale)), interpolation=cv2.INTER_AREA)
photo = ImageTk.PhotoImage(Image.fromarray(cv2.cvtColor(shown, cv2.COLOR_BGR2RGB)))
canvas = tk.Canvas(root, width=shown.shape[1], height=shown.shape[0], highlightthickness=0)
canvas.pack(padx=8, pady=8)
canvas.create_image(0, 0, image=photo, anchor="nw")
count_var = tk.StringVar()
automatic = holes.read_diameter(source)
diameter_var = tk.StringVar(value=f"{automatic:g}" if automatic else "10")


def visual_radius():
    detected = [item[2] for item in candidates if not item[3]]
    return float(np.median(detected)) if detected else max(5.0, side * 0.012)


def redraw():
    canvas.delete("mark")
    for index, (cx, cy, radius, manual) in enumerate(candidates):
        selected = index in active
        color = "#d00000" if selected else "#777777"
        dash = (5, 3) if manual else None
        canvas.create_oval(
            (cx - radius) * scale, (cy - radius) * scale,
            (cx + radius) * scale, (cy + radius) * scale,
            outline=color, width=3, dash=dash, tags="mark",
        )
        canvas.create_text(cx * scale, cy * scale, text=str(index + 1), fill=color, font=("Arial", 10, "bold"), tags="mark")
    count_var.set(str(len(active)))


def nearest(px, py):
    if not candidates:
        return None, float("inf")
    index = min(range(len(candidates)), key=lambda i: (candidates[i][0] - px) ** 2 + (candidates[i][1] - py) ** 2)
    cx, cy, radius, manual = candidates[index]
    return index, ((cx - px) ** 2 + (cy - py) ** 2) ** 0.5


def left_click(event):
    px, py = event.x / scale, event.y / scale
    index, distance = nearest(px, py)
    if index is not None and distance <= max(12, candidates[index][2] * 1.8):
        if index in active:
            active.remove(index)
        else:
            active.add(index)
    else:
        candidates.append([px, py, visual_radius(), True])
        active.add(len(candidates) - 1)
    redraw()


def right_click(event):
    px, py = event.x / scale, event.y / scale
    index, distance = nearest(px, py)
    if index is None or distance > max(14, candidates[index][2] * 2):
        return
    candidates.pop(index)
    shifted = set()
    for value in active:
        if value < index:
            shifted.add(value)
        elif value > index:
            shifted.add(value - 1)
    active.clear()
    active.update(shifted)
    redraw()


def clear_all():
    active.clear()
    redraw()


def select_all():
    active.update(range(len(candidates)))
    redraw()


def finish():
    try:
        diameter = float(diameter_var.get().replace(",", "."))
        if diameter <= 0:
            raise ValueError
    except ValueError:
        messagebox.showerror("Ошибка", "Введите положительный диаметр отверстий")
        return
    selected = [{"x": x0 + candidates[i][0], "y": y0 + candidates[i][1]} for i in sorted(active)]
    payload = {"count": len(selected), "diameter": diameter, "circles": selected}
    temporary = response.with_suffix(response.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(response)
    root.withdraw()
    root.update_idletasks()
    root.after(20, lambda: os._exit(0))


def cancel():
    root.withdraw()
    root.update_idletasks()
    root.after(20, lambda: os._exit(2))

canvas.bind("<Button-1>", left_click)
canvas.bind("<Button-2>", right_click)
canvas.bind("<Button-3>", right_click)

hint = ttk.Label(root, text="Левый щелчок: выбрать или добавить отверстие. Правый щелчок: удалить отметку.")
hint.pack(pady=(0, 6))
panel = ttk.Frame(root, padding=(8, 4, 8, 10))
panel.pack(fill="x")
ttk.Label(panel, text="Выбрано:").pack(side="left")
ttk.Entry(panel, textvariable=count_var, width=5, state="readonly").pack(side="left", padx=4)
ttk.Button(panel, text="Снять все", command=clear_all).pack(side="left", padx=5)
ttk.Button(panel, text="Выбрать все", command=select_all).pack(side="left", padx=5)
ttk.Label(panel, text="Диаметр, мм:").pack(side="left", padx=(15, 4))
ttk.Entry(panel, textvariable=diameter_var, width=8).pack(side="left")
ttk.Button(panel, text="Отмена", command=cancel).pack(side="right", padx=5)
ttk.Button(panel, text="Продолжить", command=finish).pack(side="right", padx=5)

redraw()
root.protocol("WM_DELETE_WINDOW", cancel)
root.lift()
root.focus_force()
root.mainloop()
