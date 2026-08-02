from clarification_engine import needs_question

def test_confident_reading_does_not_interrupt_operator():
    ask,reason=needs_question({"candidates":[{"text":"1830","confidence":.96}]})
    assert not ask and reason is None
def test_unreadable_handwriting_creates_question():
    ask,reason=needs_question({"candidates":[{"text":"1830","confidence":.54}]})
    assert ask and reason=="low_ocr_confidence"
def test_close_alternatives_are_ambiguous():
    ask,reason=needs_question({"candidates":[{"text":"1830","confidence":.93},{"text":"1880","confidence":.89}]})
    assert ask and reason=="ambiguous_handwriting"
def test_same_text_from_multiple_passes_is_not_ambiguous():
    ask,_=needs_question({"candidates":[{"text":"35","confidence":.94},{"text":"35","confidence":.91}]})
    assert not ask
