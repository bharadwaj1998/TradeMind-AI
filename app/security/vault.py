"""
TradeMind AI — Secure Credential Vault
Stores sensitive credentials using the OS keyring (Windows Credential Manager).
Falls back to AES-encrypted local file if keyring is unavailable.
"""
import os
import json
import base64
from pathlib import Path
from typing import Optional

try:
    import keyring
    _KEYRING_OK = True
except ImportError:
    _KEYRING_OK = False

try:
    from cryptography.fernet import Fernet
    _CRYPTO_OK = True
except ImportError:
    _CRYPTO_OK = False

from app.config import APP_DATA_DIR

_SERVICE_NAME = "TradeMind-AI"
_FALLBACK_FILE = APP_DATA_DIR / ".vault"
_KEY_FILE      = APP_DATA_DIR / ".vkey"


def _get_or_create_key() -> bytes:
    """Load or generate a Fernet encryption key for the fallback vault."""
    if _KEY_FILE.exists():
        return _KEY_FILE.read_bytes()
    key = Fernet.generate_key()
    _KEY_FILE.write_bytes(key)
    _KEY_FILE.chmod(0o600)
    return key


class Vault:
    """
    Simple key/value secure store.

    Priority:
        1. OS keyring (Windows Credential Manager) — most secure
        2. AES-encrypted local file (fallback when keyring unavailable)
    """

    def save(self, key: str, value: str) -> None:
        if _KEYRING_OK:
            keyring.set_password(_SERVICE_NAME, key, value)
        elif _CRYPTO_OK:
            self._file_set(key, value)
        else:
            raise RuntimeError(
                "Neither keyring nor cryptography package is available. "
                "Install them: pip install keyring cryptography"
            )

    def load(self, key: str, default: Optional[str] = None) -> Optional[str]:
        if _KEYRING_OK:
            val = keyring.get_password(_SERVICE_NAME, key)
            return val if val is not None else default
        elif _CRYPTO_OK:
            return self._file_get(key, default)
        return default

    def delete(self, key: str) -> None:
        if _KEYRING_OK:
            try:
                keyring.delete_password(_SERVICE_NAME, key)
            except Exception:
                pass
        elif _CRYPTO_OK:
            self._file_delete(key)

    def has(self, key: str) -> bool:
        return self.load(key) is not None

    def load_all_broker_creds(self) -> dict:
        """Convenience: load all Angel One credentials at once."""
        return {
            "api_key":     self.load("angel_api_key",     ""),
            "client_id":   self.load("angel_client_id",   ""),
            "password":    self.load("angel_password",     ""),
            "totp_secret": self.load("angel_totp_secret", ""),
        }

    # ── Encrypted file fallback ───────────────────────────────────────────
    def _load_file_store(self) -> dict:
        if not _FALLBACK_FILE.exists():
            return {}
        try:
            f   = Fernet(_get_or_create_key())
            raw = f.decrypt(_FALLBACK_FILE.read_bytes())
            return json.loads(raw)
        except Exception:
            return {}

    def _save_file_store(self, data: dict) -> None:
        f   = Fernet(_get_or_create_key())
        enc = f.encrypt(json.dumps(data).encode())
        _FALLBACK_FILE.write_bytes(enc)

    def _file_set(self, key: str, value: str) -> None:
        data = self._load_file_store()
        data[key] = value
        self._save_file_store(data)

    def _file_get(self, key: str, default=None):
        return self._load_file_store().get(key, default)

    def _file_delete(self, key: str) -> None:
        data = self._load_file_store()
        data.pop(key, None)
        self._save_file_store(data)
