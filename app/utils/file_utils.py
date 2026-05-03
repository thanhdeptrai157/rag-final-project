import hashlib
from datetime import datetime, timezone
import uuid

from anyio import Path


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_r2_object_key(filename: str) -> str:
    now = datetime.now(timezone.utc)
    ext = Path(filename).suffix.lower()
    return f"documents/raw/{now.year}/{now.month:02d}/{uuid.uuid4()}{ext}"
