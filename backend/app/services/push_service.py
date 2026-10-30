"""
Web push service for sending notifications to subscribed clients using VAPID.
"""

import os
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime, timezone
from py_vapid import Vapid
from pywebpush import webpush, WebPushException

logger = logging.getLogger(__name__)

VAPID_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "vapid_keys.json"
VAPID_PEM_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "vapid_private.pem"
SUBSCRIPTIONS_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "push_subscriptions.json"

# In-memory subscription registry: venue_id -> list of subscription dicts
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

    # Persist PEM file on disk for pywebpush / Vapid.from_file compatibility
    try:
        with open(VAPID_PEM_FILE, "w", encoding="utf-8") as f_pem:
            f_pem.write(_private_key)
    except Exception as e_pem:
        logger.warning(f"Could not write VAPID PEM file: {e_pem}")

    _vapid_claims = {
        "sub": "mailto:admin@crowd-intelligence.local"
    }


def _load_subscriptions():
    """Load saved subscriptions from disk and database."""
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


def add_subscription(
    venue_id: str,
    subscription_info: dict,
    user_identifier: Optional[str] = None,
    is_following: bool = True,
    notifications_enabled: bool = True,
):
    """
    Register or update a browser push subscription for a venue.
    Persists to both memory cache, JSON file, and the database.
    """
    if venue_id not in _subscriptions:
        _subscriptions[venue_id] = []

    endpoint = subscription_info.get("endpoint")
    if not endpoint:
        return

    # Avoid duplicate in-memory registrations
    filtered = [s for s in _subscriptions[venue_id] if s.get("endpoint") != endpoint]
    sub_record = {
        **subscription_info,
        "is_following": is_following,
        "notifications_enabled": notifications_enabled,
        "user_identifier": user_identifier,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    filtered.append(sub_record)
    _subscriptions[venue_id] = filtered
    _save_subscriptions()

    # Persist in Database
    try:
        from app.database import SessionLocal
        from app.models.push_subscription import PushSubscription
        db = SessionLocal()
        try:
            existing = db.query(PushSubscription).filter(
                PushSubscription.venue_id == venue_id,
                PushSubscription.endpoint == endpoint,
            ).first()

            keys = subscription_info.get("keys", {})
            p256dh = keys.get("p256dh", "")
            auth = keys.get("auth", "")

            if existing:
                existing.is_following = is_following
                existing.notifications_enabled = notifications_enabled
                if user_identifier:
                    existing.user_identifier = user_identifier
                if p256dh:
                    existing.p256dh = p256dh
                if auth:
                    existing.auth = auth
                existing.updated_at = datetime.now(timezone.utc)
            else:
                db_sub = PushSubscription(
                    venue_id=venue_id,
                    endpoint=endpoint,
                    p256dh=p256dh,
                    auth=auth,
                    user_identifier=user_identifier,
                    is_following=is_following,
                    notifications_enabled=notifications_enabled,
                )
                db.add(db_sub)
            db.commit()
        except Exception as e_db:
            db.rollback()
            logger.debug(f"DB PushSubscription write note: {e_db}")
        finally:
            db.close()
    except Exception as e_outer:
        logger.debug(f"DB session error in add_subscription: {e_outer}")

    logger.info(f"Registered Web Push subscriber for venue {venue_id}. Total subscribers: {len(filtered)}")


def toggle_subscription_preference(
    venue_id: str,
    endpoint: str,
    notifications_enabled: Optional[bool] = None,
    is_following: Optional[bool] = None,
):
    """Update notification preferences for a specific subscriber."""
    if venue_id in _subscriptions:
        for s in _subscriptions[venue_id]:
            if s.get("endpoint") == endpoint:
                if notifications_enabled is not None:
                    s["notifications_enabled"] = notifications_enabled
                if is_following is not None:
                    s["is_following"] = is_following
                s["updated_at"] = datetime.now(timezone.utc).isoformat()
        _save_subscriptions()

    try:
        from app.database import SessionLocal
        from app.models.push_subscription import PushSubscription
        db = SessionLocal()
        try:
            existing = db.query(PushSubscription).filter(
                PushSubscription.venue_id == venue_id,
                PushSubscription.endpoint == endpoint,
            ).first()
            if existing:
                if notifications_enabled is not None:
                    existing.notifications_enabled = notifications_enabled
                if is_following is not None:
                    existing.is_following = is_following
                existing.updated_at = datetime.now(timezone.utc)
                db.commit()
        except Exception as e_db:
            db.rollback()
        finally:
            db.close()
    except Exception:
        pass


def remove_subscription(venue_id: str, endpoint: str):
    """Remove an expired or unsubscribed endpoint from memory, disk, and database."""
    if venue_id in _subscriptions:
        _subscriptions[venue_id] = [s for s in _subscriptions[venue_id] if s.get("endpoint") != endpoint]
        _save_subscriptions()

    try:
        from app.database import SessionLocal
        from app.models.push_subscription import PushSubscription
        db = SessionLocal()
        try:
            db.query(PushSubscription).filter(
                PushSubscription.venue_id == venue_id,
                PushSubscription.endpoint == endpoint,
            ).delete()
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()
    except Exception:
        pass


def get_subscribers_count(venue_id: str) -> dict:
    """Return count of active followers and enabled notification subscribers."""
    subscribers = _subscriptions.get(venue_id, [])
    followers = sum(1 for s in subscribers if s.get("is_following", True))
    notifications_on = sum(1 for s in subscribers if s.get("is_following", True) and s.get("notifications_enabled", True))
    return {
        "total_followers": followers,
        "notifications_enabled_count": notifications_on,
    }


def broadcast_web_push(
    venue_id: str,
    title: str,
    body: str,
    severity: str = "WARNING",
    tag: str = "crowd-alert",
) -> int:
    """
    Send web push notifications to all active subscribers of a venue.
    """
    raw_subscribers = _subscriptions.get(venue_id, [])
    # Filter subscribers with notifications enabled
    subscribers = [s for s in raw_subscribers if s.get("notifications_enabled", True) and s.get("is_following", True)]
    if not subscribers:
        logger.debug(f"broadcast_web_push: no active subscribers for venue {venue_id}")
        return 0

    is_timeline = (tag == "live-crowd-timeline")
    payload = json.dumps({
        "title": title,
        "options": {
            "body": body,
            "icon": "/favicon.svg",
            "badge": "/favicon.svg",
            "tag": tag,
            "requireInteraction": not is_timeline,
            "renotify": not is_timeline,
            "silent": is_timeline,
            "vibrate": [] if is_timeline else ([400, 150, 400, 150, 400] if severity == "CRITICAL" else [300, 100, 300]),
            "data": {
                "url": f"/events/{venue_id}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "severity": severity,
            },
        }
    })

    expired_endpoints = []
    sent_count = 0
    fail_count = 0

    for sub in subscribers:
        try:
            logger.info(f"Sending Web Push to endpoint: {sub.get('endpoint', '')[:45]}...")
            webpush(
                subscription_info=sub,
                data=payload,
                vapid_private_key=str(VAPID_PEM_FILE),
                vapid_claims=_vapid_claims,
                ttl=300,
            )
            sent_count += 1
            logger.info("Web Push dispatched successfully via FCM/Push service!")
        except WebPushException as ex:
            logger.warning(f"Web Push delivery error: {ex}")
            fail_count += 1
            if hasattr(ex, "response") and ex.response is not None:
                if ex.response.status_code in (404, 410):
                    expired_endpoints.append(sub.get("endpoint"))
        except Exception as e:
            logger.warning(f"Push send unexpected error: {e}")
            fail_count += 1

    # Clean up expired endpoints
    if expired_endpoints:
        for ep in expired_endpoints:
            remove_subscription(venue_id, ep)

    # Save to NotificationHistory in DB
    try:
        from app.database import SessionLocal
        from app.models.push_subscription import NotificationHistory
        db = SessionLocal()
        try:
            hist = NotificationHistory(
                venue_id=venue_id,
                title=title,
                body=body,
                severity=severity,
                tag=tag,
                subscribers_count=len(subscribers),
                successful_deliveries=sent_count,
                failed_deliveries=fail_count,
            )
            db.add(hist)
            db.commit()
        except Exception as e_hist:
            db.rollback()
            logger.debug(f"Failed to record notification history: {e_hist}")
        finally:
            db.close()
    except Exception:
        pass

    return sent_count
