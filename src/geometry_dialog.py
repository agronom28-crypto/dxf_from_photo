import json, os, sys, tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
request, response = map(Path, sys.argv[1:3])
data = json.loads(request.read_text(encoding="utf-8"))
root = tk.Tk(); root.title("Размеры и привязка отверстий"); root.attributes("-topmost", True)
wv=tk.StringVar(value=str(data["width"])); hv=tk.StringVar(value=str(data["height"])); controls=[]
tk.Label(root,text="Размеры и расстояния от размерных линий",font=("Arial",15,"bold")).grid(row=0,column=0,columnspan=6,padx=14,pady=10)
tk.Label(root,text="Ширина, мм").grid(row=1,column=0); tk.Entry(root,textvariable=wv,width=12).grid(row=1,column=1)
tk.Label(root,text="Высота, мм").grid(row=1,column=2); tk.Entry(root,textvariable=hv,width=12).grid(row=1,column=3)
for i,(hs,dx,vs,dy) in enumerate(data["defaults"],1):
    a=tk.StringVar(value=hs); b=tk.StringVar(value=f"{dx:.1f}"); c=tk.StringVar(value=vs); d=tk.StringVar(value=f"{dy:.1f}"); controls.append((a,b,c,d)); r=i+1
    tk.Label(root,text=f"Отверстие {i}: от").grid(row=r,column=0); ttk.Combobox(root,textvariable=a,values=("слева","справа"),state="readonly",width=8).grid(row=r,column=1)
    tk.Entry(root,textvariable=b,width=9).grid(row=r,column=2); tk.Label(root,text="мм; от").grid(row=r,column=3); ttk.Combobox(root,textvariable=c,values=("снизу","сверху"),state="readonly",width=8).grid(row=r,column=4); tk.Entry(root,textvariable=d,width=9).grid(row=r,column=5)
last=len(controls)+2; tk.Label(root,text=f"Диаметр: {data['diameter']:g} мм").grid(row=last,column=0,columnspan=6,pady=6)
def quit_now(code):
    root.withdraw(); root.update_idletasks(); root.after(20, lambda: os._exit(code))
def accept():
    try:
        w=float(wv.get().replace(",",".")); h=float(hv.get().replace(",",".")); specs=[]
        if w<=0 or h<=0: raise ValueError
        for hs,ds,vs,dv in controls:
            dx=float(ds.get().replace(",",".")); dy=float(dv.get().replace(",",".")); x=dx if hs.get()=="слева" else w-dx; y=dy if vs.get()=="снизу" else h-dy
            if dx<0 or dy<0 or not (0<=x<=w and 0<=y<=h): raise ValueError
            specs.append({"x":x,"y":y,"h_side":hs.get(),"h_distance":dx,"v_side":vs.get(),"v_distance":dy})
    except ValueError:
        messagebox.showerror("Ошибка","Проверьте размеры и привязки",parent=root); return
    temp=response.with_suffix(".tmp"); temp.write_text(json.dumps({"width":w,"height":h,"holes":specs},ensure_ascii=False),encoding="utf-8"); temp.replace(response); quit_now(0)
tk.Button(root,text="Создать DXF",command=accept,bg="#2e7d32",fg="white",font=("Arial",13)).grid(row=last+1,column=0,columnspan=3,pady=12)
tk.Button(root,text="Отмена",command=lambda:quit_now(2),font=("Arial",13)).grid(row=last+1,column=3,columnspan=3,pady=12)
root.protocol("WM_DELETE_WINDOW",lambda:quit_now(2)); root.lift(); root.focus_force(); root.mainloop()
