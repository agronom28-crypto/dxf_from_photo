import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'src'))
from constraint_solver import solve_constraints
G={'scale':{'px_to_mm':1.0,'origin_px':[0,500]},'holes':[]}
def dim(i,a,b,v,c=.8,status='resolved'):
 return {'id':i,'kind':'linear','value_mm':v,'endpoints':[a,b],'references':[{'feature_id':f'vertex:{a[0]}','feature_type':'vertex'},{'feature_id':f'vertex:{b[0]}','feature_type':'vertex'}],'confidence':c,'status':status}
def test_geometry_mismatch_rejected():
 r=solve_constraints({'dimensions':[dim('d1',[0,0],[100,0],400)]},G)
 assert r['dimensions'][0]['status']=='unresolved'
 assert r['constraint_solver']['issues'][0]['type']=='geometry_mismatch'
def test_chain_conflict_flags_weakest():
 ds=[dim('ab',[0,0],[100,0],100,.9),dim('bc',[100,0],[250,0],150,.85),dim('ac',[0,0],[250,0],300,.55)]
 r=solve_constraints({'dimensions':ds},G,geometry_tol=1.0)
 assert any(i['type']=='chain_conflict' for i in r['constraint_solver']['issues'])
 assert next(d for d in r['dimensions'] if d['id']=='ac')['status']=='review'
