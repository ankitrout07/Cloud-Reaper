"""Passcode-derived encryption helpers for the settings vault."""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


def generate_salt() -> bytes:
    return Fernet.generate_key()[:16]


def derive_fernet_key(passcode: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=480_000,
    )
    return base64.urlsafe_b64encode(kdf.derive(passcode.encode("utf-8")))


def hash_passcode(passcode: str, salt: bytes) -> str:
    return hashlib.sha256(salt + passcode.encode("utf-8")).hexdigest()


def verify_passcode(passcode: str, salt: bytes, verifier: str) -> bool:
    return hash_passcode(passcode, salt) == verifier


def encrypt_payload(passcode: str, salt: bytes, data: dict[str, Any]) -> str:
    fernet = Fernet(derive_fernet_key(passcode, salt))
    return fernet.encrypt(json.dumps(data).encode("utf-8")).decode("utf-8")


def decrypt_payload(passcode: str, salt: bytes, token: str) -> dict[str, Any]:
    fernet = Fernet(derive_fernet_key(passcode, salt))
    try:
        raw = fernet.decrypt(token.encode("utf-8"))
    except InvalidToken as exc:
        raise ValueError("Unable to decrypt vault entry.") from exc
    return json.loads(raw.decode("utf-8"))
