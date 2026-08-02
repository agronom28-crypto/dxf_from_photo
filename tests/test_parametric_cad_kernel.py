import pytest
from parametric_cad_kernel import Arc, compile_model
from production_validator import validate

def stadium(confirmed=True):
    return {"part_id":"stadium","parameters":{"L":525,"R":35,"D":10},"required_parameters":["L","R","D"],"operator_confirmed":confirmed,"paths":[{"id":"outer","layer":"CUT","start":["R",0],"segments":[{"id":"bottom","type":"line","to":["L-R",0]},{"id":"right","type":"arc","center":["L-R","R"],"radius":"R","start_deg":-90,"end_deg":90},{"id":"top","type":"line","to":["R","2*R"]},{"id":"left","type":"arc","center":["R","R"],"radius":"R","start_deg":90,"end_deg":270}]}],"circles":[{"id":"hole","center":["L/2","R"],"diameter":"D"}]}
def test_exact_arc_model_is_valid():
    model=compile_model(stadium()); assert isinstance(model.paths[0][1],Arc); assert validate(model).cnc_allowed
def test_unconfirmed_model_is_blocked(): assert not validate(compile_model(stadium(False))).cnc_allowed
def test_missing_dimension_is_blocked():
    spec=stadium(); del spec["parameters"]["R"]
    with pytest.raises(ValueError): compile_model(spec)
def test_unused_required_dimension_is_blocked():
    spec=stadium(); spec["parameters"]["X"]=12; spec["required_parameters"].append("X")
    with pytest.raises(ValueError): compile_model(spec)
def test_open_contour_is_blocked():
    spec=stadium(); spec["paths"][0]["segments"].pop()
    with pytest.raises(ValueError): compile_model(spec)
