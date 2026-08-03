import pytest
from operator_workflow import validate_job

def test_cnc_blocked_without_confirmation():
    with pytest.raises(ValueError): validate_job({"selected_reference":"x.dxf","overall_width_mm":100,"overall_height_mm":50,"dimensions_confirmed":False,"geometry_confirmed":True,"dimensions":[]})
def test_cnc_blocked_on_unresolved_dimension():
    job={"selected_reference":"x.dxf","overall_width_mm":100,"overall_height_mm":50,"dimensions_confirmed":True,"geometry_confirmed":True,"dimensions":[{"value_mm":10,"target":None,"confirmed":True}]}
    with pytest.raises(ValueError): validate_job(job)
def test_confirmed_job_passes():
    job={"selected_reference":"x.dxf","overall_width_mm":100,"overall_height_mm":50,"dimensions_confirmed":True,"geometry_confirmed":True,"dimensions":[{"value_mm":10,"target":"hole_1.diameter","confirmed":True}]}
    assert validate_job(job)
