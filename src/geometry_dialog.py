import json
import os
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

request = Path(sys.argv[1])
response = Path(sys.argv[2])
data = json.loads(request.read_text(encoding="utf-8"))

root = tk.Tk()
root.title("Проверка геометрии детали")
root.attributes("-topmost", True)

width_var = tk.StringVar(value=f"{float(data.get('width', 0)):g}")
height_var = tk.StringVar(value=f"{float(data.get('height', 0)):g}")
diameter_var = tk.StringVar(value=f"{float(data.get('diameter', 0)):g}")
count_var = tk.StringVar(value=str(int(data.get("count", len(data.get("holes", []))))))
original = list(data.get("holes", []))
rows = []

header = ttk.Frame(root, padding=10)
header.pack(fill="x")
for column, (label, variable) in enumerate((("Ширина, мм", width_var), ("Высота, мм", height_var), ("Диаметр, мм", diameter_var), ("Отверстий", count_var))):
    ttk.Label(header, text=label).grid(row=0, column=column, padx=5, sticky="w")
    ttk.Entry(header, textvariable=variable, width=12).grid(row=1, column=column, padx=5)

body = ttk.Frame(root, padding=(10, 0, 10, 10))
body.pack(fill="both", expand=True)
canvas = tk.Canvas(body, width=560, height=360)
scrollbar = ttk.Scrollbar(body, orient="vertical", command=canvas.yview)
table = ttk.Frame(canvas)
table.bind("<Configure>", lambda event: canvas.configure(scrollregion=canvas.bbox("all")))
canvas.create_window((0, 0), window=table, anchor="nw")
canvas.configure(yscrollcommand=scrollbar.set)
canvas.pack(side="left", fill="both", expand=True)
scrollbar.pack(side="right", fill="y")


def number(value):
    return float(str(value).replace(",", "."))


def rebuild():
    try:
        count = max(0, int(count_var.get()))
        width = number(width_var.get())
        height = number(height_var.get())
    except ValueError:
        messagebox.showerror("Ошибка", "Проверьте ширину, высоту и количество отверстий")
        return
    saved = []
    for x_var, y_var in rows:
        try:
            saved.append({"x": number(x_var.get()), "y": number(y_var.get())})
        except ValueError:
            saved.append({})
    for widget in table.winfo_children():
        widget.destroy()
    rows.clear()
    ttk.Label(table, text="№", width=6).grid(row=0, column=0, padx=5, pady=4)
    ttk.Label(table, text="X, мм", width=18).grid(row=0, column=1, padx=5, pady=4)
    ttk.Label(table, text="Y, мм", width=18).grid(row=0, column=2, padx=5, pady=4)
    for index in range(count):
        source = saved[index] if index < len(saved) else original[index] if index < len(original) else {"x": width * (index + 1) / (count + 1), "y": height / 2}
        x_var = tk.StringVar(value=f"{float(source.get('x', width / 2)):g}")
        y_var = tk.StringVar(value=f"{float(source.get('y', height / 2)):g}")
        rows.append((x_var, y_var))
        ttk.Label(table, text=str(index + 1)).grid(row=index + 1, column=0, padx=5, pady=3)
        ttk.Entry(table, textvariable=x_var, width=18).grid(row=index + 1, column=1, padx=5, pady=3)
        ttk.Entry(table, textvariable=y_var, width=18).grid(row=index + 1, column=2, padx=5, pady=3)


def finish():
    try:
        width = number(width_var.get())
        height = number(height_var.get())
        diameter = number(diameter_var.get())
        count = int(count_var.get())
        if width <= 0 or height <= 0 or diameter <= 0 or count < 0:
            raise ValueError
        if len(rows) != count:
            rebuild()
            if len(rows) != count:
                return
        hole_values = [{"x": number(x.get()), "y": number(y.get())} for x, y in rows]
    except ValueError:
        messagebox.showerror("Ошибка", "Все размеры должны быть положительными числами")
        return
    payload = {"width": width, "height": height, "count": count, "diameter": diameter, "holes": hole_values}
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

buttons = ttk.Frame(root, padding=10)
buttons.pack(fill="x")
ttk.Button(buttons, text="Обновить количество", command=rebuild).pack(side="left")
tk.Button(buttons, text="Подтвердить", command=finish, bg="#2e7d32", fg="white", font=("Arial", 12, "bold")).pack(side="right", padx=5)
ttk.Button(buttons, text="Отмена", command=cancel).pack(side="right", padx=5)

rebuild()
root.protocol("WM_DELETE_WINDOW", cancel)
root.lift()
root.focus_force()
root.mainloop()
