import json
import os
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

request, response = map(Path, sys.argv[1:3])
data = json.loads(request.read_text(encoding="utf-8"))
root = tk.Tk()
root.title("Размеры и привязка отверстий")
root.attributes("-topmost", True)
width = tk.StringVar(value=f"{float(data.get('width', 0)):g}")
height = tk.StringVar(value=f"{float(data.get('height', 0)):g}")
diameter = tk.StringVar(value=f"{float(data.get('diameter', 10) or 10):g}")
mode_values = ("Без открытых вырезов", "С открытыми вырезами")
mode = tk.StringVar(value=data.get("cutout_mode", mode_values[0]))
if mode.get() not in mode_values:
    mode.set(mode_values[0])
controls = []

def number(value):
    return float(str(value).replace(",", "."))

def edge_values(item, w, h):
    x, y = float(item.get("x", w / 2)), float(item.get("y", h / 2))
    hs = item.get("h_side") or ("слева" if x <= w / 2 else "справа")
    vs = item.get("v_side") or ("снизу" if y <= h / 2 else "сверху")
    dx = float(item.get("h_distance", x if hs == "слева" else w - x))
    dy = float(item.get("v_distance", y if vs == "снизу" else h - y))
    return hs, dx, vs, dy

head = ttk.Frame(root, padding=12)
head.pack(fill="x")
for col, (title, variable) in enumerate((("Ширина, мм", width), ("Высота, мм", height), ("Диаметр, мм", diameter))):
    ttk.Label(head, text=title).grid(row=0, column=col, padx=5, sticky="w")
    ttk.Entry(head, textvariable=variable, width=13).grid(row=1, column=col, padx=5)
ttk.Label(head, text="Тип контура").grid(row=0, column=3, padx=5, sticky="w")
ttk.Combobox(head, textvariable=mode, values=mode_values, state="readonly", width=24).grid(row=1, column=3, padx=5)

body = ttk.Frame(root, padding=12)
body.pack(fill="both", expand=True)
for col, title in enumerate(("№", "По горизонтали от", "Расстояние, мм", "По вертикали от", "Расстояние, мм")):
    ttk.Label(body, text=title).grid(row=0, column=col, padx=5, pady=4)
w0, h0 = number(width.get()), number(height.get())
for index, item in enumerate(data.get("holes", []), 1):
    hs0, dx0, vs0, dy0 = edge_values(item, w0, h0)
    hs, dx, vs, dy = tk.StringVar(value=hs0), tk.StringVar(value=f"{dx0:g}"), tk.StringVar(value=vs0), tk.StringVar(value=f"{dy0:g}")
    controls.append((hs, dx, vs, dy))
    ttk.Label(body, text=str(index)).grid(row=index, column=0, padx=5, pady=3)
    ttk.Combobox(body, textvariable=hs, values=("слева", "справа"), state="readonly", width=12).grid(row=index, column=1, padx=5)
    ttk.Entry(body, textvariable=dx, width=15).grid(row=index, column=2, padx=5)
    ttk.Combobox(body, textvariable=vs, values=("снизу", "сверху"), state="readonly", width=12).grid(row=index, column=3, padx=5)
    ttk.Entry(body, textvariable=dy, width=15).grid(row=index, column=4, padx=5)

def close(code):
    root.withdraw(); root.update_idletasks(); root.after(20, lambda: os._exit(code))

def finish():
    try:
        w, h, dia = number(width.get()), number(height.get()), number(diameter.get())
        if w <= 0 or h <= 0 or dia <= 0:
            raise ValueError
        result = []
        for hs, dx_text, vs, dy_text in controls:
            dx, dy = number(dx_text.get()), number(dy_text.get())
            x = dx if hs.get() == "слева" else w - dx
            y = dy if vs.get() == "снизу" else h - dy
            if dx < 0 or dy < 0 or not (0 <= x <= w and 0 <= y <= h):
                raise ValueError
            result.append({"x": x, "y": y, "h_side": hs.get(), "h_distance": dx, "v_side": vs.get(), "v_distance": dy})
    except ValueError:
        messagebox.showerror("Ошибка", "Проверьте размеры и расстояния отверстий от краёв", parent=root)
        return
    payload = dict(data)
    payload.update({"width": w, "height": h, "diameter": dia, "count": len(result), "holes": result, "cutout_mode": mode.get()})
    temporary = response.with_suffix(response.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(response)
    close(0)

def action(parent, text, command):
    label = tk.Label(parent, text=text, bg="#176b3a", fg="#ffffff", activebackground="#0f4d29", activeforeground="#ffffff", font=("Arial", 13, "bold"), padx=20, pady=9, relief="raised", bd=2, cursor="hand2")
    label.bind("<Button-1>", lambda event: command())
    return label

buttons = ttk.Frame(root, padding=12)
buttons.pack(fill="x")
ttk.Button(buttons, text="Отмена", command=lambda: close(2)).pack(side="right", padx=6)
action(buttons, "Продолжить", finish).pack(side="right", padx=6)
root.protocol("WM_DELETE_WINDOW", lambda: close(2))
root.lift(); root.focus_force(); root.mainloop()
