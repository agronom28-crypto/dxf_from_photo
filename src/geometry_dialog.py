import json
import os
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

request, response = map(Path, sys.argv[1:3])
data = json.loads(request.read_text(encoding="utf-8"))
root = tk.Tk()
root.title("Визуальная разметка детали и отверстий")
root.geometry("1280x760")
root.minsize(1050, 650)
root.attributes("-topmost", True)

width = tk.StringVar(value=f"{float(data.get('width', 0)):g}")
height = tk.StringVar(value=f"{float(data.get('height', 0)):g}")
diameter = tk.StringVar(value=f"{float(data.get('diameter', 10) or 10):g}")
mode_values = ("Без открытых вырезов", "С открытыми вырезами")
mode = tk.StringVar(value=data.get("cutout_mode", mode_values[0]))
if mode.get() not in mode_values:
    mode.set(mode_values[0])
selected = tk.IntVar(value=0)
controls = []
row_frames = []
hole_screen = []
redraw_job = None


def number(value):
    return float(str(value).replace(",", "."))


def safe_number(variable, fallback=0.0):
    try:
        return number(variable.get())
    except (TypeError, ValueError):
        return fallback


def edge_values(item, w, h):
    x, y = float(item.get("x", w / 2)), float(item.get("y", h / 2))
    hs = item.get("h_side") or ("слева" if x <= w / 2 else "справа")
    vs = item.get("v_side") or ("снизу" if y <= h / 2 else "сверху")
    dx = float(item.get("h_distance", x if hs == "слева" else w - x))
    dy = float(item.get("v_distance", y if vs == "снизу" else h - y))
    return hs, dx, vs, dy


def current_xy(index, w, h):
    hs, dx_var, vs, dy_var = controls[index]
    dx, dy = safe_number(dx_var), safe_number(dy_var)
    x = dx if hs.get() == "слева" else w - dx
    y = dy if vs.get() == "снизу" else h - dy
    return x, y, dx, dy


def schedule_draw(*_):
    global redraw_job
    if redraw_job is not None:
        root.after_cancel(redraw_job)
    redraw_job = root.after(40, draw)


def select_hole(index):
    if controls:
        selected.set(max(0, min(index, len(controls) - 1)))
    draw()


def draw_dimension(x1, y1, x2, y2, text, color):
    canvas.create_line(x1, y1, x2, y2, fill=color, width=2, arrow=tk.BOTH)
    mx, my = (x1 + x2) / 2, (y1 + y2) / 2
    canvas.create_rectangle(mx - 30, my - 11, mx + 30, my + 11, fill="#ffffff", outline="")
    canvas.create_text(mx, my, text=text, fill=color, font=("Arial", 10, "bold"))


def draw():
    global redraw_job, hole_screen
    redraw_job = None
    canvas.delete("all")
    hole_screen = []
    cw, ch = max(canvas.winfo_width(), 500), max(canvas.winfo_height(), 400)
    w, h = safe_number(width), safe_number(height)
    if w <= 0 or h <= 0:
        canvas.create_text(cw / 2, ch / 2, text="Введите положительные ширину и высоту", fill="#b42318", font=("Arial", 16, "bold"))
        return
    margin_left, margin_right, margin_top, margin_bottom = 125, 125, 85, 105
    scale = min((cw - margin_left - margin_right) / w, (ch - margin_top - margin_bottom) / h)
    scale = max(scale, 0.01)
    ox = (cw - w * scale) / 2
    oy = (ch - h * scale) / 2
    x0, y0, x1, y1 = ox, oy, ox + w * scale, oy + h * scale
    canvas.create_rectangle(x0, y0, x1, y1, fill="#f8fbff", outline="#153e75", width=3)
    canvas.create_text((x0 + x1) / 2, y0 - 52, text=f"Ширина {w:g} мм", fill="#153e75", font=("Arial", 12, "bold"))
    canvas.create_line(x0, y0 - 30, x1, y0 - 30, fill="#153e75", arrow=tk.BOTH, width=2)
    canvas.create_text(x0 - 72, (y0 + y1) / 2, text=f"Высота\n{h:g} мм", fill="#153e75", font=("Arial", 12, "bold"), justify="center")
    canvas.create_line(x0 - 30, y0, x0 - 30, y1, fill="#153e75", arrow=tk.BOTH, width=2)
    dia = max(0.0, safe_number(diameter, 10.0))
    active = selected.get() if controls else -1
    for index in range(len(controls)):
        x, y, dx, dy = current_xy(index, w, h)
        sx, sy = ox + x * scale, oy + (h - y) * scale
        hole_screen.append((sx, sy))
        radius = max(6, min(18, dia * scale / 2))
        valid = 0 <= x <= w and 0 <= y <= h
        color = "#d92d20" if index == active else ("#1570ef" if valid else "#f79009")
        canvas.create_oval(sx - radius, sy - radius, sx + radius, sy + radius, fill="#ffffff", outline=color, width=4 if index == active else 2, tags=(f"hole{index}", "hole"))
        canvas.create_line(sx - radius - 4, sy, sx + radius + 4, sy, fill=color)
        canvas.create_line(sx, sy - radius - 4, sx, sy + radius + 4, fill=color)
        canvas.create_text(sx, sy - radius - 14, text=f"H{index + 1}", fill=color, font=("Arial", 11, "bold"))
    if 0 <= active < len(controls):
        hs, _, vs, _ = controls[active]
        x, y, dx, dy = current_xy(active, w, h)
        sx, sy = ox + x * scale, oy + (h - y) * scale
        edge_x = x0 if hs.get() == "слева" else x1
        edge_y = y1 if vs.get() == "снизу" else y0
        horizontal_y = min(y1 + 42, ch - 42)
        vertical_x = min(x1 + 55, cw - 55)
        canvas.create_line(sx, sy, sx, horizontal_y, fill="#7f1d1d", dash=(4, 3))
        canvas.create_line(edge_x, y1, edge_x, horizontal_y, fill="#7f1d1d", dash=(4, 3))
        draw_dimension(edge_x, horizontal_y, sx, horizontal_y, f"{dx:g} мм", "#b42318")
        canvas.create_line(sx, sy, vertical_x, sy, fill="#7f1d1d", dash=(4, 3))
        canvas.create_line(x1, edge_y, vertical_x, edge_y, fill="#7f1d1d", dash=(4, 3))
        draw_dimension(vertical_x, sy, vertical_x, edge_y, f"{dy:g} мм", "#b42318")
        canvas.create_text((edge_x + sx) / 2, horizontal_y + 24, text=f"от {hs.get()} края", fill="#7f1d1d", font=("Arial", 10))
        canvas.create_text(vertical_x + 48, (sy + edge_y) / 2, text=f"от {vs.get()} края", fill="#7f1d1d", font=("Arial", 10), width=90)
    canvas.create_text(cw / 2, ch - 18, text="Нажмите на отверстие, чтобы увидеть и изменить его привязки", fill="#475467", font=("Arial", 10))
    for index, frame in enumerate(row_frames):
        frame.configure(style="Selected.TFrame" if index == active else "TFrame")


def canvas_click(event):
    if not hole_screen:
        return
    distances = [((event.x - x) ** 2 + (event.y - y) ** 2, index) for index, (x, y) in enumerate(hole_screen)]
    distance, index = min(distances)
    if distance <= 35 ** 2:
        select_hole(index)


style = ttk.Style(root)
style.configure("Selected.TFrame", background="#dbeafe")
style.configure("Title.TLabel", font=("Arial", 12, "bold"))
style.configure("Hint.TLabel", foreground="#475467")

header = ttk.Frame(root, padding=(12, 10))
header.pack(fill="x")
for col, (title, variable) in enumerate((("Ширина детали, мм", width), ("Высота детали, мм", height), ("Диаметр отверстий, мм", diameter))):
    ttk.Label(header, text=title).grid(row=0, column=col, padx=5, sticky="w")
    entry = ttk.Entry(header, textvariable=variable, width=18)
    entry.grid(row=1, column=col, padx=5, sticky="ew")
    entry.bind("<KeyRelease>", schedule_draw)
ttk.Label(header, text="Тип контура").grid(row=0, column=3, padx=5, sticky="w")
ttk.Combobox(header, textvariable=mode, values=mode_values, state="readonly", width=25).grid(row=1, column=3, padx=5, sticky="ew")
for col in range(4):
    header.columnconfigure(col, weight=1)

workspace = ttk.Panedwindow(root, orient="horizontal")
workspace.pack(fill="both", expand=True, padx=12, pady=(0, 8))
visual = ttk.Frame(workspace, padding=6)
panel = ttk.Frame(workspace, padding=8)
workspace.add(visual, weight=3)
workspace.add(panel, weight=2)

ttk.Label(visual, text="Эскиз привязок", style="Title.TLabel").pack(anchor="w", pady=(0, 4))
canvas = tk.Canvas(visual, bg="#ffffff", highlightthickness=1, highlightbackground="#98a2b3")
canvas.pack(fill="both", expand=True)
canvas.bind("<Button-1>", canvas_click)
canvas.bind("<Configure>", schedule_draw)

ttk.Label(panel, text="Точные размеры отверстий", style="Title.TLabel").pack(anchor="w")
ttk.Label(panel, text="Выберите отверстие на эскизе или в списке. Укажите, от какого края задан каждый размер.", style="Hint.TLabel", wraplength=430).pack(anchor="w", pady=(2, 8))

list_canvas = tk.Canvas(panel, highlightthickness=0, width=440)
scrollbar = ttk.Scrollbar(panel, orient="vertical", command=list_canvas.yview)
rows_holder = ttk.Frame(list_canvas)
rows_holder.bind("<Configure>", lambda event: list_canvas.configure(scrollregion=list_canvas.bbox("all")))
list_canvas.create_window((0, 0), window=rows_holder, anchor="nw")
list_canvas.configure(yscrollcommand=scrollbar.set)
list_canvas.pack(side="left", fill="both", expand=True)
scrollbar.pack(side="right", fill="y")

w0, h0 = safe_number(width), safe_number(height)
for index, item in enumerate(data.get("holes", [])):
    hs0, dx0, vs0, dy0 = edge_values(item, w0, h0)
    hs = tk.StringVar(value=hs0)
    dx = tk.StringVar(value=f"{dx0:g}")
    vs = tk.StringVar(value=vs0)
    dy = tk.StringVar(value=f"{dy0:g}")
    controls.append((hs, dx, vs, dy))
    frame = ttk.Frame(rows_holder, padding=7)
    frame.grid(row=index, column=0, sticky="ew", pady=3)
    row_frames.append(frame)
    ttk.Radiobutton(frame, text=f"H{index + 1}", variable=selected, value=index, command=draw).grid(row=0, column=0, rowspan=2, padx=(0, 8))
    ttk.Label(frame, text="Горизонтально от").grid(row=0, column=1, sticky="w")
    ttk.Combobox(frame, textvariable=hs, values=("слева", "справа"), state="readonly", width=9).grid(row=1, column=1, padx=(0, 5))
    horizontal = ttk.Entry(frame, textvariable=dx, width=10)
    horizontal.grid(row=1, column=2, padx=(0, 10))
    ttk.Label(frame, text="Вертикально от").grid(row=0, column=3, sticky="w")
    ttk.Combobox(frame, textvariable=vs, values=("снизу", "сверху"), state="readonly", width=9).grid(row=1, column=3, padx=(0, 5))
    vertical = ttk.Entry(frame, textvariable=dy, width=10)
    vertical.grid(row=1, column=4)
    for variable in (hs, dx, vs, dy):
        variable.trace_add("write", schedule_draw)
    for widget in (frame, horizontal, vertical):
        widget.bind("<Button-1>", lambda event, i=index: select_hole(i), add="+")
rows_holder.columnconfigure(0, weight=1)


def close(code):
    root.withdraw()
    root.update_idletasks()
    root.after(20, lambda: os._exit(code))


def finish():
    try:
        w, h, dia = number(width.get()), number(height.get()), number(diameter.get())
        if w <= 0 or h <= 0 or dia <= 0:
            raise ValueError
        result = []
        for index, (hs, dx_text, vs, dy_text) in enumerate(controls, 1):
            dx, dy = number(dx_text.get()), number(dy_text.get())
            x = dx if hs.get() == "слева" else w - dx
            y = dy if vs.get() == "снизу" else h - dy
            radius = dia / 2
            if dx < 0 or dy < 0 or not (radius <= x <= w - radius and radius <= y <= h - radius):
                raise ValueError(f"H{index}")
            result.append({"x": x, "y": y, "h_side": hs.get(), "h_distance": dx, "v_side": vs.get(), "v_distance": dy})
    except ValueError as error:
        suffix = f" ({error})" if str(error) else ""
        messagebox.showerror("Ошибка размеров", "Проверьте размеры и привязки: отверстие целиком должно находиться внутри детали" + suffix, parent=root)
        return
    payload = dict(data)
    payload.update({"width": w, "height": h, "diameter": dia, "count": len(result), "holes": result, "cutout_mode": mode.get()})
    temporary = response.with_suffix(response.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(response)
    close(0)


buttons = ttk.Frame(root, padding=(12, 4, 12, 12))
buttons.pack(fill="x")
ttk.Label(buttons, text="Синий — корректно, красный — выбранное, оранжевый — вне детали", style="Hint.TLabel").pack(side="left")
ttk.Button(buttons, text="Отмена", command=lambda: close(2)).pack(side="right", padx=6)
tk.Button(buttons, text="Продолжить и создать DXF", command=finish, bg="#176b3a", fg="#ffffff", activebackground="#0f4d29", activeforeground="#ffffff", font=("Arial", 12, "bold"), padx=18, pady=7, cursor="hand2").pack(side="right", padx=6)

root.protocol("WM_DELETE_WINDOW", lambda: close(2))
root.after(120, draw)
root.lift()
root.focus_force()
root.mainloop()
