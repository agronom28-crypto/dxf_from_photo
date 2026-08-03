import json, os, sys, tkinter as tk
from pathlib import Path
import cv2
from PIL import Image, ImageTk
import hole_diameter_clarification as holes
source=Path(sys.argv[1]); response=Path(sys.argv[2]); image=cv2.imread(str(source))
if image is None:os._exit(3)
height,width=image.shape[:2];auto=holes._automatic_figure_roi(image) or (0,0,width,height)
root=tk.Tk();root.title("Укажите область детали");root.attributes("-topmost",True)
scale=min(1100/width,720/height,1.0);shown=cv2.resize(image,(int(width*scale),int(height*scale)),interpolation=cv2.INTER_AREA);photo=ImageTk.PhotoImage(Image.fromarray(cv2.cvtColor(shown,cv2.COLOR_BGR2RGB)))
canvas=tk.Canvas(root,width=shown.shape[1],height=shown.shape[0]);canvas.pack(padx=8,pady=8);canvas.create_image(0,0,image=photo,anchor="nw")
selection=list(map(float,auto));start=[None]
def redraw():
 canvas.delete("selection");x,y,w,h=selection;canvas.create_rectangle(x*scale,y*scale,(x+w)*scale,(y+h)*scale,outline="red",width=3,tags="selection")
def press(event):start[0]=(event.x/scale,event.y/scale)
def release(event):
 if start[0] is None:return
 x1,y1=start[0];x2,y2=event.x/scale,event.y/scale;x=max(0,min(x1,x2));y=max(0,min(y1,y2));w=min(width,max(x1,x2))-x;h=min(height,max(y1,y2))-y
 if w>10 and h>10:selection[:]=[x,y,w,h];redraw()
 start[0]=None
def finish(code):
 if code==0:
  x,y,w,h=map(lambda v:int(round(v)),selection);temp=response.with_suffix(".tmp");temp.write_text(json.dumps({"roi":[x,y,w,h]}),encoding="utf-8");temp.replace(response)
 root.withdraw();root.update_idletasks();root.after(20,lambda:os._exit(code))
canvas.bind("<ButtonPress-1>",press);canvas.bind("<ButtonRelease-1>",release);redraw();tk.Label(root,text="Красная рамка — найденная деталь. Корректируйте только при необходимости.",font=("Arial",13,"bold")).pack(pady=4)
tk.Button(root,text="Использовать область",command=lambda:finish(0),bg="#2e7d32",fg="white",font=("Arial",13)).pack(side="left",padx=20,pady=10);tk.Button(root,text="Отмена",command=lambda:finish(2),font=("Arial",13)).pack(side="right",padx=20,pady=10)
root.protocol("WM_DELETE_WINDOW",lambda:finish(2));root.lift();root.focus_force();root.mainloop()
