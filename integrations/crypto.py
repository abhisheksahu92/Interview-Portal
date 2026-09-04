"""Symmetric encryption for connector credentials at rest.

Connector API keys live in ``ConnectorConfig.settings``, which is persisted as a
Fernet token rather than plaintext JSON, so a database dump does not hand over
every customer's HRMS credentials.

The key comes from ``INTEGRATIONS_ENCRYPTION_KEY`` when set (a urlsafe-base64
32-byte Fernet key, rotatable without touching ``SECRET_KEY``); otherwise it is
derived deterministically from ``SECRET_KEY`` with HKDF-SHA256 so a default
install works with no extra configuration. Rotating ``SECRET_KEY`` without
setting an explicit key makes existing connector settings unreadable — they
decrypt to ``{}`` and the connector reports itself unconfigured rather than
raising.
"""

import base64
import json
import logging

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from django.conf import settings

logger = logging.getLogger(__name__)

_INFO = b"interview-portal.integrations.connector-settings.v1"


def derive_key(secret_key: str) -> bytes:
    """A Fernet key deterministically derived from ``secret_key``."""
    raw = HKDF(
        algorithm=hashes.SHA256(), length=32, salt=None, info=_INFO
    ).derive(secret_key.encode())
    return base64.urlsafe_b64encode(raw)


def fernet() -> Fernet:
    """The :class:`~cryptography.fernet.Fernet` used for connector settings."""
    configured = getattr(settings, "INTEGRATIONS_ENCRYPTION_KEY", "")
    if configured:
        return Fernet(configured.encode() if isinstance(configured, str) else configured)
    return Fernet(derive_key(settings.SECRET_KEY))


def encrypt_json(value) -> str:
    """JSON-encode then Fernet-encrypt ``value``; returns a text token."""
    if value is None:
        value = {}
    return fernet().encrypt(json.dumps(value, sort_keys=True).encode()).decode()


def decrypt_json(token, default=None):
    """Inverse of :func:`encrypt_json`; returns ``default`` on any bad token."""
    if default is None:
        default = {}
    if not token:
        return default
    try:
        return json.loads(fernet().decrypt(str(token).encode()).decode())
    except (InvalidToken, ValueError, TypeError):
        logger.warning("integrations: connector settings could not be decrypted")
        return default
