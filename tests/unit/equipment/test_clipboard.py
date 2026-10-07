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


def test_read_win32_clipboard_retries_on_initial_failure():
    """Verify _read_win32_clipboard retries OpenClipboard when initially locked."""
    from unittest.mock import MagicMock
    from companion.equipment.clipboard import _read_win32_clipboard

    mock_user32 = MagicMock()
    # Fails first 2 times, succeeds on 3rd attempt
    mock_user32.OpenClipboard.side_effect = [False, False, True]
    mock_user32.GetClipboardData.return_value = 1234
    mock_kernel32 = MagicMock()
    mock_kernel32.GlobalLock.return_value = None  # Mock lock failure to exit cleanly

    with patch("ctypes.windll.user32", mock_user32, create=True), \
         patch("ctypes.windll.kernel32", mock_kernel32, create=True), \
         patch("time.sleep", return_value=None):
        res = _read_win32_clipboard()
        assert res == ""
        assert mock_user32.OpenClipboard.call_count == 3
        mock_user32.CloseClipboard.assert_called_once()
