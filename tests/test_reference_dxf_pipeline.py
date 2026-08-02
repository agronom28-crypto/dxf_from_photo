import ezdxf
from reference_dxf_pipeline import extract_loops, write_outputs

def test_line_arc_reference_becomes_closed_contour(tmp_path):
    doc=ezdxf.new("R2010"); m=doc.modelspace()
    m.add_line((0,0),(90,0)); m.add_arc((90,10),10,270,0); m.add_line((100,10),(100,40)); m.add_arc((90,40),10,0,90); m.add_line((90,50),(0,50)); m.add_line((0,50),(0,0))
    src=tmp_path/"source.dxf"; doc.saveas(src)
    loops=extract_loops(ezdxf.readfile(src),flatten=.02,join_tol=.05)
    assert len(loops)==1 and loops[0].layer=="CUT"
    manifest=write_outputs(src,tmp_path/"part",flatten=.02,join_tol=.05)
    assert manifest["outer"]==1
    for suffix in ("_CNC.dxf","_DIMENSIONED.dxf"): assert (tmp_path/("part"+suffix)).exists()

def test_nested_circle_is_hole():
    doc=ezdxf.new("R2010"); m=doc.modelspace(); m.add_lwpolyline([(0,0),(100,0),(100,100),(0,100)],close=True); m.add_circle((50,50),10)
    assert [x.layer for x in extract_loops(doc,flatten=.02,join_tol=.05)]==["CUT","HOLES"]

def test_annotation_entities_are_ignored():
    doc=ezdxf.new("R2010"); m=doc.modelspace(); m.add_lwpolyline([(0,0),(10,0),(10,10),(0,10)],close=True); m.add_text("100"); m.add_line((20,20),(30,20),dxfattribs={"layer":"DIM"})
    assert len(extract_loops(doc))==1
