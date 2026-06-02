# Release Gate: tincan-y29r — Desktop Notifications + Tray Menu (tincan-rovp)

**Bead:** tincan-y29r
**Feature:** Desktop notifications (KDE/GNOME) + tray context menu + Settings dialog (tincan-rovp)
**Review beads:** tincan-s0rk (rovp.1/.3/.4, PASS) + tincan-1jqi (rovp.5/.2, PASS)
**Commits evaluated:** 216239c (Settings/gear — rovp.3/.4), b8ba036 (DesktopNotifier — rovp.1), a86b223 (tray+click — rovp.5/.2); all on main
**Main HEAD at gate time:** 2a69bd5 (fix(pairing): add _done guards — tincan-8kyf)
**Gate run:** 2026-06-02
**Verdict:** ✅ PASS (see Criterion 5 note)

---

## Gate Checklist

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | Review PASS present | ✅ PASS | tincan-s0rk CLOSED (close: pass) — 216239c+b8ba036, 1 LOW + 2 INFO, no blockers; tincan-1jqi CLOSED (close: pass) — a86b223, 1 MEDIUM + 2 LOW + 2 INFO, no blockers |
| 2 | Acceptance criteria met | ✅ PASS | All rovp.1–rovp.5 ACs verified against code — see detail below |
| 3 | Tests pass + lint clean | ✅ PASS | 399 pass (see note); pre-existing exclusions only; ruff: All checks passed |
| 4 | No HIGH findings open | ✅ PASS | Highest severity across both review beads: MEDIUM (1, thread model advisory); zero HIGH |
| 5 | Final branch is clean | ⚠️ CONDITIONAL PASS | 4 modified tracked files on main worktree (see note); pre-existing, none in tincan_gui/ (the rovp path) |
| 6 | Branch diverges cleanly from main | N/A | Local-only repo; commits are on main |
| 7 | Single feature theme | ✅ PASS | All 3 commits touch tincan_gui/ only; feature is coherent (notifications + tray + settings) |

---

## Criterion 2 — Acceptance criteria

### rovp.1 — D-Bus desktop notification dispatch with dedup guard (b8ba036)

| AC | Status | Evidence |
|----|--------|---------|
| Uses org.freedesktop.Notifications Notify() via dbus-python | ✅ PASS | `notifications.py:15-17` — service/path/iface constants; `_notify()` calls `iface.Notify()` |
| Dedup guard per conversation (body+timestamp key) | ✅ PASS | `notifications.py:37,87-96` — `self._seen` dict[conv_id → set[(body, ts)]]; skip if key in seen |
| INBOUND only; skip if not is_new | ✅ PASS | `_should_notify()` line 80: `direction == "inbound"`; line 82: status check + `is_new` guard |
| Summary: display_name truncated at 30 chars + … | ✅ PASS | `_notify():103-104` — `_truncate(display_name, 30)` |
| Body: message text truncated at 100 chars; fallback "New message" | ✅ PASS | `_notify():106-107` — `_truncate(body_text, 100) if body_text else "New message"` |
| timeout = 0 (default DE) | ✅ PASS | `_notify():128` — `dbus.Int32(0)` |
| Default action "default" present | ✅ PASS | `_notify():126` — `["default", "Open"]` (label uses "Open" vs spec's ""; functional match — ActionInvoked fires identically) |
| QSettings read before Notify(): skip if desktop_enabled=False | ✅ PASS | `_should_notify():76-79` — reads `notifications/desktop_enabled` before any other check |

### rovp.2 — Notification click → raise window + select conversation (a86b223)

| AC | Status | Evidence |
|----|--------|---------|
| ActionInvoked signal wired for action_id "default" | ✅ PASS | `notifications.py:63-67` — `_on_action_invoked_signal` checks `action_id == "default"` |
| Looks up conversation from notification ID | ✅ PASS | `notifications.py:65` — `self._notif_to_conv.get(int(notif_id), "")` |
| Raises window + activates window | ✅ PASS | `main.py:350-351` — `self.raise_(); self.activateWindow()` |
| Selects correct conversation | ✅ PASS | `main.py:353` — `self._conv_list.select_conversation(conversation_id)` |
| Notification ID mapped to conversation at send time | ✅ PASS | `notifications.py:130-131` — `self._notif_to_conv[int(notif_id)] = conv_id` after Notify() |

### rovp.3 — Settings gear button in title bar (216239c)

| AC | Status | Evidence |
|----|--------|---------|
| QToolButton with ⚙ symbol | ✅ PASS | `main.py:53-54` — `QToolButton(); gear_btn.setText("⚙")` |
| Size 32×32 | ✅ PASS | `main.py:55` — `setFixedSize(32, 32)` |
| Tooltip "Settings" | ✅ PASS | `main.py:56` — `setToolTip("Settings")` |
| Accessible name "Settings" | ✅ PASS | `main.py:57` — `setAccessibleName("Settings")` |
| Alt+, keyboard shortcut | ✅ PASS | `main.py:188` — `QShortcut(QKeySequence("Alt+,"), self).activated.connect(self._open_settings)` |
| Gear button wired to open Settings dialog | ✅ PASS | `main.py:194` — `self._title_bar.gear_button.clicked.connect(self._open_settings)` |

### rovp.4 — Settings dialog: Desktop notifications toggle (216239c)

| AC | Status | Evidence |
|----|--------|---------|
| Modal QDialog, minimum 400×300 | ✅ PASS | `settings_dialog.py:49-50` — `setModal(True); setMinimumSize(400, 300)` |
| NOTIFICATIONS section header (ALL-CAPS 10pt #9ca3af) | ✅ PASS | `settings_dialog.py:60-61` — `_section_header("Notifications")` |
| QCheckBox "Desktop notifications", accessible name set | ✅ PASS | `settings_dialog.py:64-65` — `QCheckBox("Desktop notifications"); setAccessibleName("Desktop notifications")` |
| Default: checked ON | ✅ PASS | `settings_dialog.py:72-73` — `QSettings.value(..., True, type=bool)` |
| Persists to QSettings key notifications/desktop_enabled | ✅ PASS | `settings_dialog.py:111` — `app_settings().setValue("notifications/desktop_enabled", checked)` |
| APPEARANCE section ghost placeholder | ✅ PASS | `settings_dialog.py:86-95` — greyed "Appearance" header + "Theme options coming soon" ghost label |
| Close button accessible name "Close" | ✅ PASS | `settings_dialog.py:101-103` — `buttons.button(StandardButton.Close).setAccessibleName("Close")` |
| Sync signal notifications_toggled(bool) emitted | ✅ PASS | `settings_dialog.py:43, 112` — Signal defined; emitted in `_on_toggled()` |

### rovp.5 — Tray context menu: notifications toggle + Settings item (a86b223)

| AC | Status | Evidence |
|----|--------|---------|
| Checkable QAction "Desktop notifications" at top before separator | ✅ PASS | `tray.py:113-116` — checkable action added before `addSeparator()` at line 118 |
| State reads from QSettings on menu open | ✅ PASS | `tray.py:136-138` — `_on_menu_about_to_show` reads `notifications/desktop_enabled` |
| Toggle writes to same QSettings key | ✅ PASS | `tray.py:141` — `app_settings().setValue("notifications/desktop_enabled", checked)` |
| Settings… item opens Settings dialog | ✅ PASS | `tray.py:124-125` — `settings_action.triggered.connect(self._window._open_settings)` |
| Tray sync from Settings dialog | ✅ PASS | `tray.py:101-103` — `sync_notifications_action(enabled)` updates tray action check state |

---

## Criterion 3 — Tests

```
python -m pytest tests/ --ignore=tests/tincand/test_dbus_client_live.py \
    --ignore=tests/tincan_gui/test_pairing_wizard.py -q

399 passed, 1 warning in 2.85s
ruff check .: All checks passed!
```

**Pre-existing exclusions (not introduced by rovp commits):**
- `test_dbus_client_live.py` — requires live tincand daemon + real D-Bus session; pre-existing class throughout project history
- `tests/tincan_gui/test_pairing_wizard.py` — ImportError: `tincan_gui.pairing_wizard` not yet implemented; introduced at commit `abcba62` (older than 216239c); tracked by tincan-inb6/tincan-pql5

**black:** Not installed in rig — not verified. ruff covers pycodestyle (E), isort (I), pyflakes (F) and is PASS.

---

## Criterion 4 — Review findings

| Review bead | Finding | Severity |
|-------------|---------|----------|
| tincan-s0rk F1 | settings_dialog.py:55 — findChild before QDialogButtonBox created; returns None (dead code; real accessible name set at line 102) | LOW |
| tincan-s0rk F2 | notifications.py — DesktopNotifier._notify() opens new dbus.SessionBus() on fallback path; wasteful but correct | INFO |
| tincan-s0rk F3 | No unit tests for DesktopNotifier dedup or SettingsDialog; will file needs-tests bead | INFO |
| tincan-1jqi F1 | notifications.py:63-67 / main.py:345-350 — _on_action_invoked_signal dispatches from D-Bus signal callback; architecturally fragile if Qt runs without GLib event loop integration (acceptable for current Linux target) | MEDIUM |
| tincan-1jqi F2 | notifications.py:38 — _notif_to_conv grows unbounded; NotificationClosed not subscribed; accumulates stale entries. No memory safety risk | LOW |
| tincan-1jqi F3 | notifications.py:115-117 — fallback bus created without GLib mainloop; ActionInvoked silent; notifications still send | LOW |
| tincan-1jqi F4 | tray.py:135 — settings_action calls self._window._open_settings() (cross-class private method) | INFO |
| tincan-1jqi F5 | No unit tests for notification click flow, tray menu sync | INFO |

Zero HIGH findings. One MEDIUM (architectural advisory, not a blocker per reviewer verdict).

---

## Criterion 5 note — Main worktree uncommitted changes

`git status` on the main worktree (`/home/jaword/projects/tincan`) shows 4 modified tracked files:

- `docs/TESTING.md`
- `tests/tincand/test_dbus_client_live.py`
- `tincand/__main__.py`
- `tincand/backends/mock.py`

None are in `tincan_gui/` (the rovp feature path). These appear to be in-progress work by builder/validator agents unrelated to tincan-rovp. The rovp feature commits (216239c, b8ba036, a86b223) and their affected files are committed cleanly. Mayor should assess whether these modifications should be committed, stashed, or handled separately before considering the gate closed.

---

## Criterion 6 note — Local-only repo

Project has no git remote. Commits are on local `main`. No push or GitHub PR possible. Merge authority: mayor.

---

## Onboarding (Release Criterion 6)

The "Show Notifications" iOS requirement surfaces in `main.py:362-370` (`_on_show_notifications_help`), wired to the banner's "Show me how" button. Not altered by rovp commits. ✅

---

## Manifest release criteria

| Criterion | Status | Notes |
|-----------|--------|-------|
| 1. Phase DOD met | N/A | rovp is a GUI enhancement; Phase-1 SMS DOD is separate |
| 2. All automated tests pass | ✅ PASS | 399 pass; pre-existing exclusions documented |
| 3. Lint clean (ruff) | ✅ PASS | All checks passed |
| 4. No hardcoded iOS-version assumptions | ✅ PASS | rovp files are purely Linux GUI (org.freedesktop.Notifications, Qt); no iOS version refs |
| 5. LIMITATIONS.md updated if needed | ✅ N/A | rovp does not alter iOS/Bluetooth platform capabilities; no LIMITATIONS.md update needed |
| 6. Onboarding surfaces Show Notifications | ✅ PASS | Banner + "Show me how" handler unchanged by rovp commits |

---

## Push / PR status

Project configured as local-only (no git remote). Commits 216239c + b8ba036 + a86b223 already on main.
Merge authority: mayor.
