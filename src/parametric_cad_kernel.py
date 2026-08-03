#!/usr/bin/env python3
"""Deterministic parametric CAD kernel for production DXF construction."""
from __future__ import annotations
import ast, math
from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class Point:
    x: float; y: float
@dataclass(frozen=True)
class Line:
    start: Point; end: Point; layer: str; feature_id: str
@dataclass(frozen=True)
class Arc:
    center: Point; radius: float; start_deg: float; end_deg: float; ccw: bool; layer: str; feature_id: str
    @property
    def start(self): return Point(self.center.x+self.radius*math.cos(math.radians(self.start_deg)),self.center.y+self.radius*math.sin(math.radians(self.start_deg)))
    @property
    def end(self): return Point(self.center.x+self.radius*math.cos(math.radians(self.end_deg)),self.center.y+self.radius*math.sin(math.radians(self.end_deg)))
@dataclass(frozen=True)
class Circle:
    center: Point; radius: float; layer: str; feature_id: str
@dataclass
class Model:
    part_id: str; parameters: dict[str,float]; paths: list[list[Any]]; circles: list[Circle]; used_parameters: set[str]; confirmed: bool

OPS={ast.Add:lambda a,b:a+b,ast.Sub:lambda a,b:a-b,ast.Mult:lambda a,b:a*b,ast.Div:lambda a,b:a/b,ast.USub:lambda a:-a,ast.UAdd:lambda a:a}
def evaluate(value,env,used):
    if isinstance(value,(int,float)): return float(value)
    if not isinstance(value,str): raise TypeError(f"expected number/expression, got {value!r}")
    node=ast.parse(value,mode="eval").body
    def walk(n):
        if isinstance(n,ast.Constant) and isinstance(n.value,(int,float)): return float(n.value)
        if isinstance(n,ast.Name):
            if n.id not in env: raise ValueError(f"unknown parameter: {n.id}")
            used.add(n.id); return float(env[n.id])
        if isinstance(n,ast.BinOp) and type(n.op) in OPS: return OPS[type(n.op)](walk(n.left),walk(n.right))
        if isinstance(n,ast.UnaryOp) and type(n.op) in OPS: return OPS[type(n.op)](walk(n.operand))
        raise ValueError(f"unsafe expression: {value}")
    result=walk(node)
    if not math.isfinite(result): raise ValueError(f"non-finite expression: {value}")
    return result
def point(value,env,used): return Point(evaluate(value[0],env,used),evaluate(value[1],env,used))
def compile_model(spec):
    env={k:float(v) for k,v in spec.get("parameters",{}).items()}; used=set(); paths=[]
    for path in spec.get("paths",[]):
        layer=path.get("layer","CUT"); current=point(path["start"],env,used); start=current; entities=[]
        for i,cmd in enumerate(path.get("segments",[])):
            fid=cmd.get("id",f"{path.get('id','path')}.{i+1}"); typ=cmd["type"]
            if typ=="line":
                end=point(cmd["to"],env,used); entities.append(Line(current,end,layer,fid)); current=end
            elif typ=="arc":
                center=point(cmd["center"],env,used); radius=evaluate(cmd["radius"],env,used); a0=evaluate(cmd["start_deg"],env,used); a1=evaluate(cmd["end_deg"],env,used); arc=Arc(center,radius,a0,a1,bool(cmd.get("ccw",True)),layer,fid)
                if distance(current,arc.start)>1e-5: raise ValueError(f"discontinuous arc {fid}: current point does not equal arc start")
                entities.append(arc); current=arc.end
            else: raise ValueError(f"unsupported segment type: {typ}")
        if distance(current,start)>1e-5: raise ValueError(f"open path: {path.get('id','path')}")
        paths.append(entities)
    circles=[]
    for i,c in enumerate(spec.get("circles",[])):
        radius=evaluate(c.get("radius",f"({c['diameter']})/2"),env,used); circles.append(Circle(point(c["center"],env,used),radius,c.get("layer","HOLES"),c.get("id",f"circle.{i+1}")))
    required=set(spec.get("required_parameters",env)); missing=required-env.keys(); unused=required-used
    if missing: raise ValueError(f"missing parameters: {sorted(missing)}")
    if unused: raise ValueError(f"unconsumed required parameters: {sorted(unused)}")
    return Model(str(spec.get("part_id","part")),env,paths,circles,used,bool(spec.get("operator_confirmed",False)))
def distance(a,b): return math.hypot(a.x-b.x,a.y-b.y)
def arc_points(a,tolerance=.05):
    span=(a.end_deg-a.start_deg)%360 if a.ccw else -((a.start_deg-a.end_deg)%360); steps=max(2,int(abs(math.radians(span))*max(a.radius,1)/max(tolerance,1e-4))+1)
    return [Point(a.center.x+a.radius*math.cos(math.radians(a.start_deg+span*i/steps)),a.center.y+a.radius*math.sin(math.radians(a.start_deg+span*i/steps))) for i in range(steps+1)]
def path_points(path,tolerance=.05):
    out=[]
    for entity in path:
        pts=[entity.start,entity.end] if isinstance(entity,Line) else arc_points(entity,tolerance)
        out.extend(pts if not out else pts[1:])
    return out
