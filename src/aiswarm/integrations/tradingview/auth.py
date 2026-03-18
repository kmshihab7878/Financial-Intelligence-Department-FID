"""TradingView webhook authentication."""

from __future__ import annotations

import hashlib
import hmac

from aiswarm.utils.logging import get_logger
from aiswarm.utils.secrets import get_secrets_provider

logger = get_logger(__name__)


def validate_webhook_passphrase(passphrase: str) -> bool:
    """Validate the webhook passphrase against the configured secret.

    Uses constant-time comparison to prevent timing attacks.
    Returns True if the passphrase matches, False otherwise.
    """
    secrets = get_secrets_provider()
    expected = secrets.get_secret("AIS_TV_WEBHOOK_SECRET") or ""
    if not expected:
        logger.warning("AIS_TV_WEBHOOK_SECRET not configured — rejecting all webhooks")
        return False
    return hmac.compare_digest(passphrase, expected)


def validate_webhook_hmac(body: bytes, signature: str) -> bool:
    """Validate HMAC-SHA256 signature of the request body.

    Alternative to passphrase-based auth. The signature header should
    contain the hex-encoded HMAC-SHA256 of the request body.
    """
    secrets = get_secrets_provider()
    secret = secrets.get_secret("AIS_TV_WEBHOOK_SECRET") or ""
    if not secret:
        return False
    expected_sig = hmac.HMAC(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, expected_sig)
