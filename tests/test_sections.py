import os
from pathlib import Path

import pytest

from ytdlp_gui.validation import parse_section, parse_timestamp


@pytest.mark.parametrize("value, expected", [
    ("90", 90), (" 1:30 ", 90), ("01:02:03.125", 3723.125),
    ("0", 0), ("0.001", 0.001), ("120:00", 7200),
])
def test_timestamp_formats(value: str, expected: float) -> None:
    assert parse_timestamp(value) == expected


@pytest.mark.parametrize("value", ["", "-1", "NaN", "inf", "1:60", "1:60:00", "1:2:3:4", "1e3", "1:30junk", "1.5:00", "0.0001"])
def test_invalid_timestamps(value: str) -> None:
    with pytest.raises(ValueError):
        parse_timestamp(value)


def test_optional_range_boundaries() -> None:
    assert parse_section("", "1:30") == (0, 90)
    assert parse_section("1:30", "") == (90, None)
    assert parse_section("0", "") == (0, None)


@pytest.mark.parametrize("start, end", [("", ""), ("30", "30"), ("30", "10"), ("bad", "60"), ("0", "bad")])
def test_invalid_ranges(start: str, end: str) -> None:
    with pytest.raises(ValueError):
        parse_section(start, end)


def test_gui_section_validation_dependencies_and_settings(monkeypatch) -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    from ytdlp_gui import main_window

    class MemorySettings:
        output_folder = str(Path.cwd())
        values = {}

        def get(self, key, default=""):
            return self.values.get(key, default)

        def get_bool(self, key, default=False):
            return self.values.get(key, default)

        def set(self, key, value):
            self.values[key] = value

        def sync(self):
            pass

    monkeypatch.setattr(main_window, "AppSettings", MemorySettings)
    monkeypatch.setattr(main_window, "find_ytdlp", lambda _: "")
    monkeypatch.setattr(main_window, "find_ffmpeg", lambda _: "")
    app = QApplication.instance() or QApplication([])
    window = main_window.MainWindow()
    warnings = []
    monkeypatch.setattr(window, "_warn", warnings.append)
    try:
        window.url_edit.setText("https://example.com/video")
        window.section_check.setChecked(True)
        assert window.section_widget.isEnabled()
        window.start_edit.setText("1:30")
        window.end_edit.setText("1:00")
        window._start_download()
        assert warnings == ["End time must be later than start time."]
        window.end_edit.setText("2:00")
        window.audio_radio.setChecked(True)
        window.audio_format_combo.setCurrentText("Best")
        options = window._options()
        assert (options.section_start, options.section_end) == (90, 120)
        assert window._requires_ffmpeg(options)
        window._save_settings()
        window.start_edit.clear()
        window._restore_settings()
        assert window.start_edit.text() == "1:30"
        window._set_running(True)
        assert not window.section_widget.isEnabled()
        window._set_running(False)
        window.section_check.setChecked(False)
        assert window._options().section_start is None
        assert not window._requires_ffmpeg(window._options())
    finally:
        window.close()
        app.processEvents()
