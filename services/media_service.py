"""
Media Service for handling image/file uploads and serving.

Stores files locally (uploads/) for simplicity.
Can be extended to use GCS via vertex_ai.save_to_gcs() for production.
"""

import os
import uuid
import base64
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# Local upload directory
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Allowed MIME types for upload
ALLOWED_MIME_TYPES = {
    "image/jpeg", "image/png", "image/webp", "image/gif", "image/bmp",
    "application/pdf",
    "video/mp4", "video/webm",
}

# Max file size: 20MB (Gemini inline limit)
MAX_FILE_SIZE = 20 * 1024 * 1024


def save_upload(file_bytes: bytes, original_filename: str, mime_type: str) -> dict:
    """
    Save an uploaded file and return metadata.

    Returns:
        dict with file_id, filename, mime_type, size, path
    """
    file_id = uuid.uuid4().hex[:12]
    ext = _ext_from_mime(mime_type) or os.path.splitext(original_filename)[1]
    safe_name = f"{file_id}{ext}"
    filepath = os.path.join(UPLOAD_DIR, safe_name)

    with open(filepath, "wb") as f:
        f.write(file_bytes)

    logger.info(f"Saved upload: {safe_name} ({len(file_bytes)} bytes, {mime_type})")

    return {
        "file_id": file_id,
        "filename": safe_name,
        "original_name": original_filename,
        "mime_type": mime_type,
        "size": len(file_bytes),
        "path": filepath,
    }


def get_file_path(file_id: str) -> Optional[str]:
    """Find file by ID in uploads directory (matches anywhere in filename)."""
    for fname in os.listdir(UPLOAD_DIR):
        if file_id in fname:
            return os.path.join(UPLOAD_DIR, fname)
    return None


def get_file_base64(file_id: str) -> Optional[Tuple[str, str]]:
    """
    Get file as base64 string + mime type.
    Returns (base64_data, mime_type) or None.
    """
    path = get_file_path(file_id)
    if not path:
        return None

    mime_type = _mime_from_ext(os.path.splitext(path)[1])
    with open(path, "rb") as f:
        data = base64.b64encode(f.read()).decode("utf-8")

    return data, mime_type


def save_generated_image(image_bytes: bytes, prefix: str = "generated") -> dict:
    """
    Save an agent-generated image (e.g., from Imagen/Gemini).

    Returns dict with file_id, filename, url_path (for serving via API).
    """
    file_id = uuid.uuid4().hex[:12]
    filename = f"{prefix}_{file_id}.png"
    filepath = os.path.join(UPLOAD_DIR, filename)

    with open(filepath, "wb") as f:
        f.write(image_bytes)

    logger.info(f"Saved generated image: {filename} ({len(image_bytes)} bytes)")

    return {
        "file_id": file_id,
        "filename": filename,
        "url_path": f"/api/media/{file_id}",
        "size": len(image_bytes),
    }


def _ext_from_mime(mime_type: str) -> str:
    mapping = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
        "image/bmp": ".bmp",
        "application/pdf": ".pdf",
        "video/mp4": ".mp4",
        "video/webm": ".webm",
    }
    return mapping.get(mime_type, "")


def _mime_from_ext(ext: str) -> str:
    mapping = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".gif": "image/gif",
        ".bmp": "image/bmp",
        ".pdf": "application/pdf",
        ".mp4": "video/mp4",
        ".webm": "video/webm",
    }
    return mapping.get(ext.lower(), "application/octet-stream")
