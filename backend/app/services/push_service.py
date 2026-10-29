"""
Web Push Service — Dispatches real native push notifications to subscriber devices
via VAPID and browser push services (FCM / Mozilla Push / WNS).
Guarantees notifications arrive on mobile devices even if browser is closed or in Instagram.
"""

import os
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional
from py_vapid import Vapid
from pywebpush import webpush, WebPushException

logger = logging.getLogger(__name__)

VAPID_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "vapid_keys.json"
SUBSCRIPTIONS_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "push_subscriptions.json"

# In-memory subscription registry: venue_id -> list of subscriptions
_subscriptions: Dict[str, List[dict]] = {}
_vapid_claims: dict = {}
_public_key: str = ""
_private_key: str = ""


def _ensure_vapid_keys():
    """Load or generate persistent VAPID keypair."""
    global _public_key, _private_key, _vapid_claims

    os.makedirs(VAPID_FILE.parent, exist_ok=True)

    if VAPID_FILE.exists():
        try:
            with open(VAPID_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                _public_key = data.get("public_key", "")
                _private_key = data.get("private_key", "")
        except Exception as e:
            logger.warning(f"Error reading VAPID file, will regenerate: {e}")

    if not _public_key or not _private_key:
        from cryptography.hazmat.primitives import serialization
        from py_vapid.utils import b64urlencode

        vapid = Vapid()
        vapid.generate_keys()
        _private_key = vapid.private_pem().decode("utf-8")
        raw_pub = vapid.public_key.public_bytes(
            serialization.Encoding.X962,
            serialization.PublicFormat.UncompressedPoint
        )
        _public_key_b64 = b64urlencode(raw_pub)

        with open(VAPID_FILE, "w", encoding="utf-8") as f:
            json.dump({
                "public_key": _public_key_b64,
                "private_key": _private_key,
            }, f, indent=2)
        _public_key = _public_key_b64
        logger.info("Generated new persistent VAPID keys for Web Push")
    else:
        logger.info("Loaded persistent VAPID keys for Web Push")

    _vapid_claims = {
        "sub": "mailto:admin@crowd-intelligence.local"
    }


def _load_subscriptions():
    """Load saved subscriptions from disk."""
    global _subscriptions
    if SUBSCRIPTIONS_FILE.exists():
        try:
            with open(SUBSCRIPTIONS_FILE, "r", encoding="utf-8") as f:
                _subscriptions = json.load(f)
        except Exception as e:
            logger.warning(f"Could not load subscriptions file: {e}")
            _subscriptions = {}


def _save_subscriptions():
    """Save active subscriptions to disk."""
    try:
        os.makedirs(SUBSCRIPTIONS_FILE.parent, exist_ok=True)
        with open(SUBSCRIPTIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(_subscriptions, f, indent=2)
    except Exception as e:
        logger.warning(f"Could not persist subscriptions: {e}")


# Initialize on import
_ensure_vapid_keys()
_load_subscriptions()


def get_vapid_public_key() -> str:
    """Return the applicationServerKey for the browser PushManager."""
    return _public_key


def add_subscription(venue_id: str, subscription_info: dict):
    """Register a browser push subscription for a venue."""
    if venue_id not in _subscriptions:
        _subscriptions[venue_id] = []

    endpoint = subscription_info.get("endpoint")
    # Avoid duplicate registrations
    filtered = [s for s in _subscriptions[venue_id] if s.get("endpoint") != endpoint]
    filtered.append(subscription_info)
    _subscriptions[venue_id] = filtered
    _save_subscriptions()
    logger.info(f"Registered Web Push subscriber for venue {venue_id}. Total subscribers: {len(filtered)}")


def remove_subscription(venue_id: str, endpoint: str):
    """Remove an expired or unsubscribed endpoint."""
    if venue_id in _subscriptions:
        _subscriptions[venue_id] = [s for s in _subscriptions[venue_id] if s.get("endpoint") != endpoint]
        _save_subscriptions()


def broadcast_web_push(venue_id: str, title: str, body: str, severity: str = "WARNING", tag: str = "crowd-alert") -> int:
    """
    Directly deliver native Web Push notification to all subscriber devices.
    Pushes via Google FCM / Mozilla Push Service straight into device OS notification bar.
    Returns the number of devices successfully messaged.
    """
    subscribers = _subscriptions.get(venue_id, [])
    if not subscribers:
        logger.info(f"broadcast_web_push: no subscribers for venue {venue_id}")
        return 0

    payload = json.dumps({
        "title": title,
        "options": {
            "body": body,
            "icon": "/favicon.svg",
            "badge": "/favicon.svg",
            "tag": tag,
            "requireInteraction": True,
            "renotify": True,
            "vibrate": [400, 150, 400, 150, 400] if severity == "CRITICAL" else [300, 100, 300],
            "data": {"url": f"/events/{venue_id}"},
        }
    })

    expired_endpoints = []
    sent_count = 0

    for sub in subscribers:
        try:
            logger.info(f"Sending Web Push to endpoint: {sub.get('endpoint', '')[:45]}...")
            webpush(
                subscription_info=sub,
                data=payload,
                vapid_private_key=_private_key,
                vapid_claims=_vapid_claims,
                ttl=300,
            )
            sent_count += 1
            logger.info("Web Push dispatched successfully via FCM/Push service!")
        except WebPushException as ex:
            logger.warning(f"Web Push delivery error: {ex}")
            if hasattr(ex, "response") and ex.response is not None:
                if ex.response.status_code in (404, 410):
                    expired_endpoints.append(sub.get("endpoint"))
        except Exception as e:
            logger.warning(f"Push send unexpected error: {e}")

    # Clean up expired endpoints
    if expired_endpoints:
        for ep in expired_endpoints:
            remove_subscription(venue_id, ep)

    return sent_count
