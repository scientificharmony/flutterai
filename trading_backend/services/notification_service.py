"""
Firebase Cloud Messaging push notification service.
Initialises Firebase lazily — gracefully skips if credentials are missing.
"""
import logging
import os

from config import settings

logger = logging.getLogger(__name__)

_firebase_app = None


def _init_firebase():
    global _firebase_app
    if _firebase_app is not None:
        return True
    if not settings.ENABLE_PUSH_NOTIFICATIONS:
        logger.debug("Push notifications disabled; skipping Firebase init.")
        return False
    path = settings.FIREBASE_SERVICE_ACCOUNT_PATH
    if not path:
        logger.debug("Firebase credentials not configured — push disabled.")
        return False
    if not os.path.exists(path):
        logger.warning("Firebase credentials not found at %s — push disabled.", path)
        return False
    try:
        import firebase_admin
        from firebase_admin import credentials
        cred = credentials.Certificate(path)
        _firebase_app = firebase_admin.initialize_app(cred)
        logger.info("Firebase initialised.")
        return True
    except Exception as exc:
        logger.error("Firebase init failed: %s", exc)
        return False


def send_trade_alert(
    device_token: str,
    title: str,
    body: str,
    alert_id: str,
    ticker: str,
    action_strength: int | None = None,
) -> bool:
    """
    Send a push notification for a trade alert.
    Returns True on success, False if push is unavailable or fails.
    """
    if not _init_firebase():
        return False
    try:
        from firebase_admin import messaging
        message = messaging.Message(
            notification=messaging.Notification(title=title, body=body),
            data={
                "type": "trade_alert",
                "alert_id": alert_id,
                "ticker": ticker,
                "action_strength": str(action_strength or 0),
            },
            token=device_token,
        )
        messaging.send(message)
        return True
    except Exception as exc:
        logger.error("Push send failed for token %s: %s", device_token[:12], exc)
        return False


def send_to_user_devices(
    device_tokens: list[str],
    title: str,
    body: str,
    alert_id: str,
    ticker: str,
    action_strength: int | None = None,
) -> int:
    """Send to all user devices. Returns count of successful sends."""
    sent = 0
    for token in device_tokens:
        if send_trade_alert(token, body=body, title=title, alert_id=alert_id, ticker=ticker, action_strength=action_strength):
            sent += 1
    return sent
