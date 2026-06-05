"""NotificationFilter + SeenAppsRegistry — app notification filtering.

QSettings keys:
  notifications/app_mirroring_enabled  (bool, default True)
  notifications/app_filter/{app_id}    (str, 'allow' or 'deny')
  notifications/seen_apps/{app_id}     (str, label_hint)
"""
from __future__ import annotations

from tincan_gui._settings import app_settings


class NotificationFilter:
    """Decide whether a given app_id's notifications should be shown.

    Unknown app IDs default to allowed — opt-out rather than opt-in.
    """

    def is_enabled(self) -> bool:
        """Return True when app notification mirroring is globally on."""
        return app_settings().value(
            "notifications/app_mirroring_enabled", True, type=bool
        )

    def set_enabled(self, enabled: bool) -> None:
        """Persist the global app notification mirroring toggle."""
        s = app_settings()
        s.setValue("notifications/app_mirroring_enabled", enabled)
        s.sync()

    def is_allowed(self, app_id: str) -> bool:
        """Return True when *app_id*'s notifications are allowed.

        Unknown apps default to 'allow'; explicitly denied apps return False.
        """
        action = app_settings().value(
            f"notifications/app_filter/{app_id}", "allow", type=str
        )
        return action != "deny"

    def set_filter(self, app_id: str, action: str) -> None:
        """Persist the allow/deny decision for *app_id*.

        Raises ValueError when *action* is not 'allow' or 'deny'.
        """
        if action not in ("allow", "deny"):
            raise ValueError(f"action must be 'allow' or 'deny', got {action!r}")
        s = app_settings()
        s.setValue(f"notifications/app_filter/{app_id}", action)
        s.sync()

    def get_all_filters(self) -> dict:
        """Return {app_id: action} for all explicitly-configured apps."""
        s = app_settings()
        s.beginGroup("notifications/app_filter")
        try:
            keys = s.childKeys()
            return {k: str(s.value(k, "allow")) for k in keys}
        finally:
            s.endGroup()


class SeenAppsRegistry:
    """Track which app_ids have produced notifications, keyed by app_id.

    label_hint is the ANCS ATTR_TITLE from the most-recent notification
    (i.e. a sender/event name, NOT an app name). Stored for API completeness
    but not displayed in the current settings UI per PM decision.
    """

    def register(self, app_id: str, label_hint: str) -> None:
        """Record *app_id* with *label_hint*; idempotent (overwrites old hint)."""
        s = app_settings()
        s.setValue(f"notifications/seen_apps/{app_id}", label_hint)
        s.sync()

    def list(self) -> list[dict]:
        """Return all seen apps as [{app_id, label_hint}], sorted by app_id."""
        s = app_settings()
        s.beginGroup("notifications/seen_apps")
        keys = s.childKeys()
        result = [
            {"app_id": k, "label_hint": str(s.value(k, ""))}
            for k in keys
        ]
        s.endGroup()
        return sorted(result, key=lambda r: r["app_id"])
