#!/usr/bin/env python3
"""Fail-closed production validation for parametric models."""
from __future__ import annotations
from dataclasses import dataclass
from parametric_cad_kernel import distance, path_points
@dataclass
class Validation:
    errors:list[str]; warnings:list[str]
    @property
    def cnc_allowed(self): return not self.errors

def orient(a,b,c): return (b.x-a.x)*(c.y-a.y)-(b.y-a.y)*(c.x-a.x)
def intersects(a,b,c,d):
    return ((orient(a,b,c)>0)!=(orient(a,b,d)>0)) and ((orient(c,d,a)>0)!=(orient(c,d,b)>0))
def point_in_polygon(p,poly):
    inside=False
    for a,b in zip(poly,poly[1:]):
        if (a.y>p.y)!=(b.y>p.y) and p.x<(b.x-a.x)*(p.y-a.y)/(b.y-a.y)+a.x: inside=not inside
    return inside
def validate(model,min_feature_mm=.1):
    errors=[]; warnings=[]
    if not model.confirmed: errors.append("operator confirmation is missing")
    if not model.paths: errors.append("no closed cutting path")
    for pi,path in enumerate(model.paths):
        pts=path_points(path)
        if not pts or distance(pts[0],pts[-1])>1e-4: errors.append(f"path {pi} is open"); continue
        n=len(pts)-1
        for i in range(n):
            for j in range(i+2,n):
                if i==0 and j==n-1: continue
                if intersects(pts[i],pts[i+1],pts[j],pts[j+1]): errors.append(f"path {pi} self-intersects"); break
            if errors and errors[-1]==f"path {pi} self-intersects": break
    outer=next((path_points(x) for x in model.paths if x and x[0].layer=="CUT"),None)
    for c in model.circles:
        if c.radius<=0: errors.append(f"{c.feature_id}: radius must be positive")
        if outer and c.layer=="HOLES" and not point_in_polygon(c.center,outer): errors.append(f"{c.feature_id}: hole center outside outer contour")
    ids=[e.feature_id for p in model.paths for e in p]+[c.feature_id for c in model.circles]
    if len(ids)!=len(set(ids)): errors.append("duplicate feature ids")
    return Validation(sorted(set(errors)),sorted(set(warnings)))
