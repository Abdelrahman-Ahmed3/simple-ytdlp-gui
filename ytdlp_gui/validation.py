from __future__ import annotations

from pathlib import Path
import re
from urllib.parse import urlparse


def parse_timestamp(value: str) -> float:
    """Parse nonnegative seconds, MM:SS, or HH:MM:SS (fractional seconds allowed)."""
    value = value.strip()
    if not re.fullmatch(r"[0-9]+(?::[0-9]+){0,2}(?:\.[0-9]{1,3})?", value):
        raise ValueError("Use seconds, MM:SS, or HH:MM:SS (for example, 90 or 1:30).")
    parts = value.split(":")
    numbers = [float(part) for part in parts]
    if len(numbers) > 1 and numbers[-1] >= 60:
        raise ValueError("Seconds must be below 60 in a timestamp.")
    if len(numbers) == 3 and numbers[1] >= 60:
        raise ValueError("Minutes must be below 60 in HH:MM:SS.")
    seconds = sum(number * 60 ** index for index, number in enumerate(reversed(numbers)))
    if not seconds < float("inf"):
        raise ValueError("The timestamp is too large.")
    return seconds


def parse_section(start: str, end: str) -> tuple[float, float | None]:
    try:
        start_seconds = parse_timestamp(start) if start.strip() else 0.0
    except ValueError as exc:
        raise ValueError(f"Start time: {exc}") from exc
    try:
        end_seconds = parse_timestamp(end) if end.strip() else None
    except ValueError as exc:
        raise ValueError(f"End time: {exc}") from exc
    if end_seconds is not None and end_seconds <= start_seconds:
        raise ValueError("End time must be later than start time.")
    if not start.strip() and not end.strip():
        raise ValueError("Enter a start or end time for the section.")
    return start_seconds, end_seconds


def validate_url(url: str) -> str | None:
    value = url.strip()
    if not value:
        return "Paste a video URL first."
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return "Enter a complete http:// or https:// URL."
    return None


def validate_output_folder(value: str) -> str | None:
    if not value.strip():
        return "Choose an output folder."
    path = Path(value).expanduser()
    if path.exists() and not path.is_dir():
        return "The selected output location is not a folder."
    return None
