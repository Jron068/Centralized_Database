"""Supabase Storage helpers for uploads that must survive ephemeral app hosts."""

import json
import mimetypes
import os
from pathlib import Path
from time import monotonic
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

from flask import current_app, url_for

_signed_url_cache = {}


class FileStorageError(RuntimeError):
    """Raised when persistent file storage is unavailable or rejects a request."""


def _settings():
    base_url = (os.getenv("SUPABASE_URL") or "").strip().rstrip("/")
    service_key = (os.getenv("SUPABASE_STORAGE_SERVICE_ROLE_KEY") or "").strip()
    if not base_url or not service_key:
        raise FileStorageError(
            "Uploads are unavailable. Configure SUPABASE_URL and "
            "SUPABASE_STORAGE_SERVICE_ROLE_KEY in the hosting environment."
        )
    parsed_url = urlsplit(base_url)
    if parsed_url.scheme != "https" or not parsed_url.netloc:
        raise FileStorageError("SUPABASE_URL must be a valid HTTPS URL.")
    return base_url, service_key


def _bucket(private):
    name = "SUPABASE_PRIVATE_STORAGE_BUCKET" if private else "SUPABASE_PUBLIC_STORAGE_BUCKET"
    default = "payment-proofs" if private else "resort-media"
    return (os.getenv(name) or default).strip()


def upload_file(data, object_path, *, private=False, content_type=None):
    """Upload bytes and return a stable database reference without exposing credentials."""
    clean_path = "/".join(part for part in object_path.replace("\\", "/").split("/") if part)
    if not clean_path or any(part in {".", ".."} for part in clean_path.split("/")):
        raise ValueError("Invalid upload path.")

    if not (os.getenv("SUPABASE_URL") or "").strip() or not (
        os.getenv("SUPABASE_STORAGE_SERVICE_ROLE_KEY") or ""
    ).strip():
        if os.getenv("FLASK_DEBUG") != "1":
            _settings()
        destination = Path(current_app.static_folder) / "uploads" / Path(*clean_path.split("/"))
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        return f"uploads/{clean_path}"

    base_url, service_key = _settings()
    bucket = _bucket(private)
    url = f"{base_url}/storage/v1/object/{quote(bucket, safe='')}/{quote(clean_path, safe='/')}"
    request = Request(
        url,
        data=data,
        headers={
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
            "Content-Type": content_type or mimetypes.guess_type(clean_path)[0] or "application/octet-stream",
            "x-upsert": "false",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=30) as response:
            if response.status not in (200, 201):
                raise FileStorageError(f"Supabase Storage rejected the upload (HTTP {response.status}).")
    except HTTPError as exc:
        raise FileStorageError(f"Supabase Storage rejected the upload (HTTP {exc.code}).") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise FileStorageError("Could not reach Supabase Storage. Please try again.") from exc
    return f"supabase://{bucket}/{clean_path}"


def delete_uploaded_file(file_path):
    """Delete an object created in Supabase Storage; local legacy paths are unchanged."""
    parsed = urlsplit(file_path or "")
    if parsed.scheme != "supabase":
        if file_path and file_path.startswith("uploads/"):
            static_root = Path(current_app.static_folder).resolve()
            local_path = (static_root / file_path).resolve()
            if os.path.commonpath((str(static_root), str(local_path))) != str(static_root):
                raise ValueError("Invalid local upload path.")
            if local_path.is_file():
                local_path.unlink()
        return
    base_url, service_key = _settings()
    bucket = parsed.netloc
    expected = {_bucket(False), _bucket(True)}
    object_path = parsed.path.lstrip("/")
    if bucket not in expected or not object_path:
        raise ValueError("Invalid Supabase Storage reference.")

    request = Request(
        f"{base_url}/storage/v1/object/{quote(bucket, safe='')}/{quote(object_path, safe='/')}",
        headers={"apikey": service_key, "Authorization": f"Bearer {service_key}"},
        method="DELETE",
    )
    try:
        with urlopen(request, timeout=30) as response:
            if response.status not in (200, 204):
                raise FileStorageError(f"Supabase Storage rejected the delete (HTTP {response.status}).")
    except HTTPError as exc:
        raise FileStorageError(f"Supabase Storage rejected the delete (HTTP {exc.code}).") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise FileStorageError("Could not reach Supabase Storage to delete the file.") from exc


def file_url(file_path):
    """Resolve a database file reference, signing private objects for a short time."""
    if not file_path:
        return None
    parsed = urlsplit(file_path)
    if parsed.scheme != "supabase":
        if file_path.startswith("/static/"):
            return file_path
        return url_for("static", filename=file_path)

    bucket = parsed.netloc
    object_path = parsed.path.lstrip("/")
    if bucket == _bucket(False):
        base_url, _ = _settings()
        return (
            f"{base_url}/storage/v1/object/public/{quote(bucket, safe='')}/"
            f"{quote(object_path, safe='/')}"
        )
    if bucket != _bucket(True) or not object_path:
        raise ValueError("Invalid Supabase Storage reference.")
    cached_url = _signed_url_cache.get(file_path)
    if cached_url and cached_url[0] > monotonic():
        return cached_url[1]

    base_url, service_key = _settings()
    request = Request(
        f"{base_url}/storage/v1/object/sign/{quote(bucket, safe='')}/{quote(object_path, safe='/')}",
        data=b'{"expiresIn":300}',
        headers={
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=10) as response:
            result = response.read(64 * 1024).decode("utf-8")
    except HTTPError as exc:
        raise FileStorageError(f"Could not create a private file link (HTTP {exc.code}).") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise FileStorageError("Could not reach Supabase Storage to create a private file link.") from exc

    try:
        signed_path = json.loads(result)["signedURL"]
    except (KeyError, TypeError, ValueError) as exc:
        raise FileStorageError("Supabase Storage returned an invalid private file link.") from exc
    if signed_path.startswith(("https://", "http://")):
        signed_url = signed_path
    elif signed_path.startswith("/storage/v1/"):
        signed_url = f"{base_url}{signed_path}"
    else:
        signed_url = f"{base_url}/storage/v1/{signed_path.lstrip('/')}"
    _signed_url_cache[file_path] = (monotonic() + 240, signed_url)
    return signed_url
