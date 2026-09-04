import os
from cryptography.fernet import Fernet

# For production, this should be set in the environment and NEVER hardcoded.
# For local dev, we use a fallback key to prevent crashes if it's missing.
_FALLBACK_KEY = b'rX3aW5y6ZkL8mP2tC7qN4bH9vF1sJ0xV3wK6yT9mC2s='
_ENCRYPTION_KEY = os.environ.get("ENCRYPTION_KEY", _FALLBACK_KEY.decode("utf-8")).encode("utf-8")

_fernet = Fernet(_ENCRYPTION_KEY)

def encrypt_value(value: str) -> str:
    if not value:
        return ""
    return _fernet.encrypt(value.encode("utf-8")).decode("utf-8")

def decrypt_value(encrypted_value: str) -> str:
    if not encrypted_value:
        return ""
    try:
        return _fernet.decrypt(encrypted_value.encode("utf-8")).decode("utf-8")
    except Exception:
        # Invalid key or corrupted data
        return ""
