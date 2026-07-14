"""Encrypted local credential storage.

The encryption key is sourced from AXONFLOW_SECRET_KEY when configured. For local
development a 0600 key file is generated beside the SQLite database and ignored by Git.
"""

from __future__ import annotations

import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from axonflow.security.secrets import SecretManager


class CredentialEncryptionError(ValueError):
    """Raised when a credential cannot be encrypted or decrypted."""


class CredentialCipher:
    def __init__(self, workspace_dir: Path) -> None:
        self._key_path = workspace_dir / ".axonflow.key"
        self._fernet = Fernet(self._load_key())

    def _load_key(self) -> bytes:
        configured = os.environ.get("AXONFLOW_SECRET_KEY")
        if configured:
            return configured.encode("utf-8")

        if self._key_path.exists():
            return self._key_path.read_bytes().strip()

        key = Fernet.generate_key()
        self._key_path.parent.mkdir(parents=True, exist_ok=True)
        self._key_path.write_bytes(key)
        self._key_path.chmod(0o600)
        return key

    def encrypt(self, secret: str) -> str:
        if not secret.strip():
            raise CredentialEncryptionError("Credential secret cannot be empty")
        return self._fernet.encrypt(secret.encode("utf-8")).decode("utf-8")

    def decrypt(self, encrypted_secret: str) -> str:
        try:
            return self._fernet.decrypt(encrypted_secret.encode("utf-8")).decode("utf-8")
        except (InvalidToken, ValueError) as exc:
            raise CredentialEncryptionError("Credential cannot be decrypted") from exc


def masked_secret(secret: str) -> str:
    return SecretManager.mask_key(secret)
