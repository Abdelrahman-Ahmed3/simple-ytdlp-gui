from __future__ import annotations

import json
import re

from .command_builder import OUTPUT_PREFIX, PROGRESS_PREFIX
from .models import ProgressUpdate


_PERCENT_RE = re.compile(r"([0-9]+(?:\.[0-9]+)?)%")
_STANDARD_PROGRESS_RE = re.compile(
    r"^\[download\]\s+(?P<percent>[0-9]+(?:\.[0-9]+)?)%"
    r"(?:\s+of(?:\s+~)?\s+(?P<total>[0-9.]+\s*[A-Za-z]+))?"
    r"(?:\s+at\s+(?P<speed>.+?)\s+ETA\s+(?P<eta>[0-9:]+|Unknown))?"
)


def _number(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _human_speed(value: float) -> str:
    return f"{human_bytes(round(value))}/s"


def _parse_size(value: str) -> int | None:
    match = re.fullmatch(r"\s*([0-9.]+)\s*([KMGTPE]?)(i?B)\s*", value, re.IGNORECASE)
    if not match:
        return None
    amount = float(match.group(1))
    power = "KMGTPE".find(match.group(2).upper()) + 1 if match.group(2) else 0
    base = 1024 if match.group(3).lower().startswith("i") else 1000
    return round(amount * (base**power))


def parse_progress_line(line: str) -> ProgressUpdate | None:
    text = line.strip()
    if text.startswith(PROGRESS_PREFIX):
        payload = text[len(PROGRESS_PREFIX) :]
        media_codec = ""
        if not payload.startswith("{") and "|" in payload:
            media_codec, payload = payload.split("|", 1)
        operation = "Downloading audio" if media_codec.lower() in {"none", "audio only"} else "Downloading video"
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            match = _PERCENT_RE.search(payload)
            return ProgressUpdate(percent=float(match.group(1)) if match else None, operation=operation)
        downloaded = _number(data.get("downloaded_bytes"))
        total = _number(data.get("total_bytes") or data.get("total_bytes_estimate"))
        percent_raw = str(data.get("_percent_str") or "")
        match = _PERCENT_RE.search(percent_raw)
        percent_value = float(match.group(1)) if match else None
        if percent_value is None:
            raw_percent = data.get("_percent", data.get("percent"))
            try:
                percent_value = float(raw_percent) if raw_percent is not None else None
            except (TypeError, ValueError):
                percent_value = None
        if percent_value is None and downloaded is not None and total:
            percent_value = downloaded * 100 / total
        if percent_value is None:
            fragment_index = _number(data.get("fragment_index"))
            fragment_count = _number(data.get("fragment_count"))
            if fragment_index is not None and fragment_count:
                percent_value = fragment_index * 100 / fragment_count

        speed_value = data.get("speed")
        speed = str(data.get("_speed_str") or "").strip()
        if not speed and isinstance(speed_value, (int, float)) and speed_value > 0:
            speed = _human_speed(float(speed_value))

        eta_value = data.get("_eta_str")
        if eta_value in (None, ""):
            eta_value = data.get("eta")
        eta = str(eta_value).strip() if eta_value is not None else ""
        if not eta and downloaded is not None and total is not None and isinstance(speed_value, (int, float)) and speed_value > 0:
            eta = str(max(0, round((total - downloaded) / speed_value)))
        return ProgressUpdate(
            percent=percent_value,
            speed=speed,
            downloaded=downloaded,
            total=total,
            eta=eta,
            operation=operation,
        )
    if "[Merger]" in text or "Merging formats" in text:
        return ProgressUpdate(operation="Merging")
    if "[ExtractAudio]" in text or "Destination:" in text and "audio" in text.lower():
        return ProgressUpdate(operation="Converting audio")
    if "[VideoConvertor]" in text or "[VideoRemuxer]" in text:
        return ProgressUpdate(operation="Converting video")
    standard = _STANDARD_PROGRESS_RE.match(text)
    if standard:
        percent = float(standard.group("percent"))
        total = _parse_size(standard.group("total") or "")
        downloaded = round(total * percent / 100) if total is not None else None
        speed = (standard.group("speed") or "").strip()
        eta = (standard.group("eta") or "").strip()
        return ProgressUpdate(
            percent=percent,
            speed="" if speed.lower().startswith("unknown") else speed,
            downloaded=downloaded,
            total=total,
            eta="" if eta.lower() == "unknown" else eta,
            operation="Downloading",
        )
    return None


def parse_output_path(line: str) -> str | None:
    text = line.strip()
    if text.startswith(OUTPUT_PREFIX):
        return text[len(OUTPUT_PREFIX) :]
    return None


def human_bytes(value: int | None) -> str:
    if value is None:
        return "?"
    amount = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if amount < 1024 or unit == "TB":
            return f"{amount:.1f} {unit}" if unit != "B" else f"{int(amount)} B"
        amount /= 1024
    return f"{amount:.1f} TB"


def format_eta(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        return ""
    if stripped.isdigit():
        seconds = int(stripped)
        return f"{seconds // 60:02d}:{seconds % 60:02d}"
    return stripped
