"""Unit tests for passive platform clipboard reader."""

from unittest.mock import patch
import pytest
from companion.equipment.clipboard import get_clipboard_text, read_item_input

BOOTS_TEXT = """Item Class: Boots
Rarity: Rare
Loath Trail
Furtive Boots
--------
+66 to maximum Life
"""


def test_get_clipboard_text_mocked():
    with patch("companion.equipment.clipboard._read_os_clipboard", return_value=BOOTS_TEXT):
        text = get_clipboard_text()
        assert "Loath Trail" in text


def test_read_item_input_from_file(tmp_path):
    f = tmp_path / "item.txt"
    f.write_text(BOOTS_TEXT, encoding="utf-8")

    text = read_item_input(file_path=f)
    assert "Loath Trail" in text


def test_read_item_input_from_clipboard():
    with patch("companion.equipment.clipboard._read_os_clipboard", return_value=BOOTS_TEXT):
        text = read_item_input(file_path=None)
        assert "Loath Trail" in text
