from assessments.templatetags.assessment_extras import get_item


def test_get_item_with_string_key():
    mapping = {"1": "one", 1: "integer one"}
    assert get_item(mapping, 1) == "one"
    assert get_item(mapping, "1") == "one"

def test_get_item_with_non_string_key_fallback():
    mapping = {1: "integer one"}
    assert get_item(mapping, 1) == "integer one"

def test_get_item_missing_key():
    mapping = {"1": "one"}
    assert get_item(mapping, 2) is None

def test_get_item_not_a_mapping():
    assert get_item(None, "key") is None
    assert get_item(["a", "b"], 1) is None
