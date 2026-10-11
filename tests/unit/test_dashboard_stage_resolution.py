def test_resolve_char_id(tmp_path):
    from companion.dashboard_api import resolve_char_id

    (tmp_path / "characters").mkdir()
    (tmp_path / "characters" / "BOMSHAK.json").write_text("{}")
    assert resolve_char_id(" bomshak ", tmp_path) == "BOMSHAK"
    assert resolve_char_id("Other", tmp_path) == "Other"
    assert resolve_char_id(None, tmp_path) == "BOMSHAK"
    assert resolve_char_id("", tmp_path) == "BOMSHAK"
