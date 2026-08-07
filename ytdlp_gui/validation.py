from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse


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
