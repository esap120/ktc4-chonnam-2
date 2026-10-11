from daesingo.search import api_key_from_env


def test_new_key_name_wins_over_legacy_alias() -> None:
    env = {"ELICE_ML_API_KEY": " new ", "GEMINI_API_KEY": "old"}
    assert api_key_from_env(env) == "new"


def test_legacy_key_name_still_works() -> None:
    assert api_key_from_env({"GEMINI_API_KEY": "old"}) == "old"


def test_blank_new_key_falls_back_and_missing_is_empty() -> None:
    assert api_key_from_env({"ELICE_ML_API_KEY": " ", "GEMINI_API_KEY": "old"}) == "old"
    assert api_key_from_env({}) == ""
