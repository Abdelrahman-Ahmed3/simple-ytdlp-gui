import json

from ytdlp_gui.command_builder import OUTPUT_PREFIX, PROGRESS_PREFIX
from ytdlp_gui.progress import human_bytes, parse_output_path, parse_progress_line


def test_json_progress_line() -> None:
    payload = {
        "_percent_str": " 68.2%",
        "_speed_str": "12.4MiB/s",
        "downloaded_bytes": 91_226_112,
        "total_bytes": 134_217_728,
        "_eta_str": "00:04",
    }
    update = parse_progress_line(PROGRESS_PREFIX + "avc1.640028|" + json.dumps(payload))
    assert update is not None
    assert update.percent == 68.2
    assert update.downloaded == 91_226_112
    assert update.total == 134_217_728
    assert update.eta == "00:04"
    assert update.operation == "Downloading video"


def test_audio_stream_is_identified() -> None:
    update = parse_progress_line(PROGRESS_PREFIX + 'none|{"_percent_str":"5.0%"}')
    assert update is not None
    assert update.operation == "Downloading audio"


def test_numeric_json_fields_and_calculated_eta() -> None:
    update = parse_progress_line(
        PROGRESS_PREFIX
        + 'none|{"_percent":25.0,"downloaded_bytes":250,"total_bytes":1000,"speed":125}'
    )
    assert update is not None
    assert update.percent == 25.0
    assert update.speed == "125 B/s"
    assert update.eta == "6"


def test_standard_ytdlp_progress_is_a_fallback() -> None:
    update = parse_progress_line("[download]  42.0% of  128.00MiB at  12.40MiB/s ETA 00:04")
    assert update is not None
    assert update.percent == 42.0
    assert update.total == 134_217_728
    assert update.downloaded == 56_371_446
    assert update.speed == "12.40MiB/s"
    assert update.eta == "00:04"


def test_operation_detection() -> None:
    assert parse_progress_line('[Merger] Merging formats into "video.mp4"').operation == "Merging"
    assert parse_progress_line('[ExtractAudio] Destination: "audio.mp3"').operation == "Converting audio"


def test_output_path_and_human_size() -> None:
    assert parse_output_path(OUTPUT_PREFIX + r"C:\Downloads\title.mp4") == r"C:\Downloads\title.mp4"
    assert human_bytes(134_217_728) == "128.0 MB"
