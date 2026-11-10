"""Extract the audio format from a DIDL-Lite resource."""

from collections.abc import Mapping

MIME_TO_FORMAT = {
    "audio/flac": "FLAC",
    "audio/x-flac": "FLAC",
    "audio/mpeg": "MP3",
    "audio/mp3": "MP3",
    "audio/x-mp3": "MP3",
    "audio/x-mpeg": "MP3",
    "audio/wav": "WAV",
    "audio/wave": "WAV",
    "audio/x-wav": "WAV",
    "audio/vnd.wave": "WAV",
    "audio/l16": "PCM",
    "audio/l24": "PCM",
    "audio/x-ms-wma": "WMA",
    "audio/ogg": "OGG",
    "application/ogg": "OGG",
    "audio/opus": "Opus",
    "audio/aac": "AAC",
    "audio/aacp": "AAC",
    "audio/x-aac": "AAC",
    "audio/x-mpeg-aac": "AAC",
    "audio/vnd.dlna.adts": "AAC",
    "audio/x-aiff": "AIFF",
    "audio/aiff": "AIFF",
    "audio/x-m4a": "M4A",
    "audio/mp4": "MP4",
    "audio/alac": "ALAC",
    "audio/dsd": "DSD",
    "audio/x-dsd": "DSD",
    "audio/x-dsf": "DSF",
}


def parse_audio_format(attributes: Mapping[str, str] | None) -> str | None:
    """Return a human-readable format from the resource protocolInfo."""
    protocol_info = attributes.get("protocolInfo", "") if attributes is not None else ""
    parts = protocol_info.split(":", 3)
    mime = parts[2].split(";", 1)[0].strip().lower() if len(parts) == 4 else ""
    if mime == "*":
        mime = ""
    return MIME_TO_FORMAT.get(mime, mime) if mime else None
