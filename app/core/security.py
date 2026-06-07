import base64
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHashError

from app.core.config import Config


JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_TYPE = "access"
REFRESH_TOKEN_TYPE = "refresh"

PASSWORD_HASH_ALGORITHM = "argon2id"

_password_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=4,
    hash_len=32,
    salt_len=16,
)


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _password_hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False
    except Exception:
        return False


def password_needs_rehash(password_hash: str) -> bool:
    try:
        return _password_hasher.check_needs_rehash(password_hash)
    except Exception:
        return True


def create_access_token(subject: str, claims: dict[str, Any] | None = None) -> str:
    return _create_token(
        subject=subject,
        expires_in_minutes=Config.ACCESS_TOKEN_EXPIRE_MINUTES,
        token_type=ACCESS_TOKEN_TYPE,
        claims=claims,
    )


def create_refresh_token(subject: str, claims: dict[str, Any] | None = None) -> str:
    return _create_token(
        subject=subject,
        expires_in_minutes=Config.REFRESH_TOKEN_EXPIRE_MINUTES,
        token_type=REFRESH_TOKEN_TYPE,
        claims=claims,
    )


def _create_token(
    *,
    subject: str,
    expires_in_minutes: int,
    token_type: str,
    claims: dict[str, Any] | None = None,
) -> str:
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=expires_in_minutes)

    payload = {
        "sub": subject,
        "token_type": token_type,
        "exp": int(expires_at.timestamp()),
        "iat": int(now.timestamp()),
    }

    if claims:
        payload.update(claims)

    header = {"alg": JWT_ALGORITHM, "typ": "JWT"}

    signing_input = (
        _base64url_encode_json(header) + "." + _base64url_encode_json(payload)
    )
    signature = _sign(signing_input)

    return f"{signing_input}.{signature}"


def decode_access_token(token: str) -> dict[str, Any] | None:
    return _decode_token(token=token, expected_token_type=ACCESS_TOKEN_TYPE)


def decode_refresh_token(token: str) -> dict[str, Any] | None:
    return _decode_token(token=token, expected_token_type=REFRESH_TOKEN_TYPE)


def _decode_token(token: str, expected_token_type: str) -> dict[str, Any] | None:
    try:
        header_part, payload_part, signature = token.split(".", 2)
        signing_input = f"{header_part}.{payload_part}"

        if not hmac.compare_digest(_sign(signing_input), signature):
            return None

        header = _base64url_decode_json(header_part)
        if header.get("alg") != JWT_ALGORITHM:
            return None

        payload = _base64url_decode_json(payload_part)
        if payload.get("token_type") != expected_token_type:
            return None

        expires_at = int(payload.get("exp", 0))
        if expires_at < int(datetime.now(timezone.utc).timestamp()):
            return None

        return payload
    except Exception:
        return None


def _sign(signing_input: str) -> str:
    digest = hmac.new(
        Config.JWT_SECRET_KEY.encode("utf-8"),
        signing_input.encode("utf-8"),
        hashlib.sha256,
    ).digest()

    return _base64url_encode_bytes(digest)


def _base64url_encode_json(value: dict[str, Any]) -> str:
    data = json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return _base64url_encode_bytes(data)


def _base64url_encode_bytes(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _base64url_decode_json(value: str) -> dict[str, Any]:
    padding = "=" * (-len(value) % 4)
    data = base64.urlsafe_b64decode(value + padding)
    decoded = json.loads(data.decode("utf-8"))

    return decoded if isinstance(decoded, dict) else {}