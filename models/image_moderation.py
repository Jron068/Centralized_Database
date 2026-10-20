"""Fail-closed image content moderation for resort photo uploads."""

import base64
import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class ImageModerationError(Exception):
    """Raised when an image cannot be safely scanned or is flagged."""


MAX_IMAGE_BYTES = 8 * 1024 * 1024
_FORMATS = {
    "jpg": ("image/jpeg", lambda b: b.startswith(b"\xff\xd8\xff")),
    "jpeg": ("image/jpeg", lambda b: b.startswith(b"\xff\xd8\xff")),
    "png": ("image/png", lambda b: b.startswith(b"\x89PNG\r\n\x1a\n")),
    "webp": ("image/webp", lambda b: len(b) >= 12 and b[:4] == b"RIFF" and b[8:12] == b"WEBP"),
}


def scan_resort_image(data, extension):
    """Validate image bytes, then reject it if moderation flags the image.

    Uploads are blocked if the moderation key is missing or the service cannot
    return a valid result, so an outage never silently skips scanning.
    """
    ext = (extension or "").lower().lstrip(".")
    fmt = _FORMATS.get(ext)
    if not fmt or not data or len(data) > MAX_IMAGE_BYTES or not fmt[1](data):
        raise ImageModerationError("Use a valid JPG, PNG, or WEBP image up to 8 MB.")

    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        raise ImageModerationError(
            "Image scanning is unavailable. Configure OPENAI_API_KEY before uploading resort photos."
        )

    mime_type = fmt[0]
    encoded = base64.b64encode(data).decode("ascii")
    payload = {
        "model": os.getenv("OPENAI_MODERATION_MODEL", "omni-moderation-latest"),
        "input": [{
            "type": "image_url",
            "image_url": {"url": f"data:{mime_type};base64,{encoded}"},
        }],
    }
    request = Request(
        "https://api.openai.com/v1/moderations",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=20) as response:
            result = json.loads(response.read(1024 * 1024).decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
        raise ImageModerationError(
            "The image could not be scanned right now. Please try again later."
        ) from exc

    results = result.get("results") or []
    if not results or "flagged" not in results[0]:
        raise ImageModerationError("The image scanner returned no valid result. Upload was stopped.")
    if results[0]["flagged"]:
        raise ImageModerationError("This image was flagged by the content scanner and was not uploaded.")
    return {"model": result.get("model"), "flagged": False}
