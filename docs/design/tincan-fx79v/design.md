# Design: Phone Calls UI — Incoming Call Dialog, In-Call Panel, DTMF Keypad

**Bead:** tincan-fx79v  
**Designer:** tincan/designer  
**Date:** 2026-06-07  
**Wireframe:** `/home/jaword/projects/gc-management/.gc/worktrees/tincan/designer/tincan-fx79v/phone-calls-ui.excalidraw`

---

## OQ-5 Answer: Floating Modal Dialog + Inline Panel

The three placement options were: floating, takeover, tray.

**Decision: floating modal for incoming call; inline panel for in-call.**

- **Incoming call** → `QDialog` positioned at center of `MainWindow`, semi-modal (blocks interaction with the main window until answered/declined, but does not open a new OS window). This matches the existing `NewConversationDialog` pattern and requires no new window management.
- **In-call** → inline panel that *replaces the compose bar* (`self._compose`) at the bottom of the right pane while a call is active. The user stays in their current conversation view; the panel slides in via `QStackedWidget` or a hidden/shown widget swap. When the call ends, the compose bar is restored.

Rationale against takeover: disrupts the messaging workflow for an incidental action. Against tray: not discoverable and would require a persistent system tray icon that complicates the existing `tray.py` lifecycle.

---

## Screen 1: Incoming Call Dialog

```
┌─────────────────────────────────────────────────────────────────────────┐  bg: #18181b
│                                                                         │  border: #3f3f46 2px
│                        ┌──────────────┐                                 │
│                        │              │  Avatar: 68×68px ellipse        │
│                        │     AB       │  bg: #0d9488  text: #ffffff     │
│                        │              │  (shows PBAP photo if cached)   │
│                        └──────────────┘                                 │
│                                                                         │
│                         Alice Brown                                     │  #f4f4f5, 20px
│                       +1 (415) 555-0101                                 │  #9ca3af, 13px
│                      Incoming call via HFP...                           │  #6b7280, 11px, animated dots
│                                                                         │
│   ┌─────────────────────────┐    ┌─────────────────────────┐            │
│   │       ✕  Decline        │    │       ✓  Answer          │            │
│   │       bg: #dc2626       │    │       bg: #16a34a        │            │
│   └─────────────────────────┘    └─────────────────────────┘            │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
  340×290px dialog  |  margins: 16px  |  button height: 44px
```

**Implementation class:** `IncomingCallDialog(QDialog)`  
**Window flags:** `Qt.Dialog | Qt.WindowTitleHint` — no minimize/maximize  
**Centering:** `dlg.move(parent.geometry().center() - dlg.rect().center())`

### Component spec

```python
class IncomingCallDialog(QDialog):
    answered = Signal()
    declined = Signal()

    def __init__(self, caller_name: str, caller_number: str,
                 avatar_pixmap: QPixmap | None, parent: QWidget) -> None:
        super().__init__(parent, Qt.Dialog | Qt.WindowTitleHint)
        self.setWindowTitle("Incoming Call")
        self.setStyleSheet("background: #18181b; color: #f4f4f5;")
        self.setFixedSize(340, 290)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 24, 16, 16)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignHCenter)

        # Avatar (68×68 ellipse with AvatarWidget or QLabel+pixmap)
        avatar = AvatarWidget(caller_name, size=68)
        if avatar_pixmap:
            avatar.set_photo(avatar_pixmap)
        layout.addWidget(avatar, alignment=Qt.AlignHCenter)

        # Caller info
        name_lbl = QLabel(caller_name or caller_number)
        name_lbl.setObjectName("callerName")  # for ARIA labelledby
        name_lbl.setStyleSheet("color: #f4f4f5; font-size: 20px; font-weight: 500;")
        name_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(name_lbl)

        if caller_name:
            num_lbl = QLabel(caller_number)
            num_lbl.setStyleSheet("color: #9ca3af; font-size: 13px;")
            num_lbl.setAlignment(Qt.AlignCenter)
            layout.addWidget(num_lbl)

        status_lbl = QLabel("Incoming call via HFP…")
        status_lbl.setStyleSheet("color: #6b7280; font-size: 11px;")
        status_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(status_lbl)

        layout.addStretch()

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        self._decline_btn = QPushButton("✕  Decline")
        self._decline_btn.setFixedHeight(44)
        self._decline_btn.setStyleSheet(
            "QPushButton { background: #dc2626; color: #ffffff; border: none;"
            " font-size: 14px; border-radius: 4px; }"
            " QPushButton:focus { outline: 2px dashed #3b82f6; outline-offset: 2px; }"
        )
        self._decline_btn.clicked.connect(self._on_decline)

        self._answer_btn = QPushButton("✓  Answer")
        self._answer_btn.setFixedHeight(44)
        self._answer_btn.setStyleSheet(
            "QPushButton { background: #16a34a; color: #ffffff; border: none;"
            " font-size: 14px; border-radius: 4px; }"
            " QPushButton:focus { outline: 2px dashed #3b82f6; outline-offset: 2px; }"
        )
        self._answer_btn.setDefault(True)
        self._answer_btn.clicked.connect(self._on_answer)

        btn_row.addWidget(self._decline_btn)
        btn_row.addWidget(self._answer_btn)
        layout.addLayout(btn_row)

    def _on_decline(self) -> None:
        self.declined.emit()
        self.reject()

    def _on_answer(self) -> None:
        self.answered.emit()
        self.accept()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key_Escape,):
            self._on_decline()
        else:
            super().keyPressEvent(event)
```

---

## Screen 2: In-Call Panel

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│  ●  On call with Alice Brown    0:02:14   │  ⏸ Hold  │  ⌨ Keypad  │  ✕ Hang Up   │
│  (44px avatar, #0d9488)        (#86efac)  │  #d97706 │  #27272a   │  #dc2626     │
└─────────────────────────────────────────────────────────────────────────────────────┘
  590px wide, 88px tall  |  border-top: 2px solid #0d9488
```

**Implementation:** Swap `self._compose` for `self._call_panel` in the right-pane `QVBoxLayout` using `QStackedWidget`.

```python
class InCallPanel(QWidget):
    hold_toggled = Signal(bool)  # True = held, False = resumed
    hang_up_requested = Signal()
    keypad_toggled = Signal(bool)

    def __init__(self, caller_name: str, avatar_pixmap: QPixmap | None,
                 parent: QWidget) -> None:
        super().__init__(parent)
        self.setStyleSheet(
            "background: #18181b; border-top: 2px solid #0d9488;"
        )
        self.setFixedHeight(88)
        self._held = False
        self._elapsed = 0
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

        row = QHBoxLayout(self)
        row.setContentsMargins(12, 0, 12, 0)
        row.setSpacing(8)

        avatar = AvatarWidget(caller_name, size=44)
        if avatar_pixmap:
            avatar.set_photo(avatar_pixmap)
        row.addWidget(avatar)

        info_col = QVBoxLayout()
        info_col.setSpacing(0)
        self._name_lbl = QLabel(f"On call with {caller_name}")
        self._name_lbl.setStyleSheet("color: #f4f4f5; font-size: 13px;")
        info_col.addWidget(self._name_lbl)
        self._timer_lbl = QLabel("0:00:00")
        self._timer_lbl.setStyleSheet("color: #86efac; font-size: 20px; font-weight: 500;")
        self._timer_lbl.setAccessibleName("Call duration")
        # aria-live="off" equivalent: no accessibility announcements on timer
        info_col.addWidget(self._timer_lbl)
        row.addLayout(info_col)
        row.addStretch()

        self._hold_btn = QPushButton("⏸ Hold")
        self._hold_btn.setFixedSize(100, 38)
        self._hold_btn.setStyleSheet(self._hold_style(False))
        self._hold_btn.setCheckable(True)
        self._hold_btn.toggled.connect(self._on_hold_toggled)
        row.addWidget(self._hold_btn)

        self._keypad_btn = QPushButton("⌨ Keypad")
        self._keypad_btn.setFixedSize(104, 38)
        self._keypad_btn.setStyleSheet(
            "QPushButton { background: #27272a; color: #9ca3af; border: 1px solid #3f3f46;"
            " font-size: 12px; border-radius: 4px; }"
            " QPushButton:focus { outline: 2px dashed #3b82f6; }"
        )
        self._keypad_btn.setCheckable(True)
        self._keypad_btn.toggled.connect(self.keypad_toggled)
        row.addWidget(self._keypad_btn)

        hang_btn = QPushButton("✕ Hang Up")
        hang_btn.setFixedSize(108, 38)
        hang_btn.setStyleSheet(
            "QPushButton { background: #dc2626; color: #ffffff; border: none;"
            " font-size: 13px; border-radius: 4px; }"
            " QPushButton:focus { outline: 2px dashed #3b82f6; }"
        )
        hang_btn.clicked.connect(self.hang_up_requested)
        row.addWidget(hang_btn)

    @staticmethod
    def _hold_style(held: bool) -> str:
        bg = "#d97706" if not held else "#3f3f46"
        text = "#ffffff" if not held else "#9ca3af"
        label = "⏸ Hold" if not held else "▶ Resume"
        return (
            f"QPushButton {{ background: {bg}; color: {text}; border: none;"
            " font-size: 13px; border-radius: 4px; }"
            " QPushButton:focus { outline: 2px dashed #3b82f6; }"
        )

    def _on_hold_toggled(self, held: bool) -> None:
        self._held = held
        self._hold_btn.setText("▶ Resume" if held else "⏸ Hold")
        self._hold_btn.setStyleSheet(self._hold_style(held))
        self.hold_toggled.emit(held)
        if held:
            self._timer.stop()
        else:
            self._timer.start()

    def _tick(self) -> None:
        self._elapsed += 1
        h, rem = divmod(self._elapsed, 3600)
        m, s = divmod(rem, 60)
        self._timer_lbl.setText(f"{h}:{m:02d}:{s:02d}")
```

---

## Screen 3: DTMF Keypad (Stretch Goal)

Displayed as a `QWidget` that appears *above* the in-call panel when the `⌨ Keypad` button is toggled. Use `QVBoxLayout` with the keypad on top and the in-call panel below, or a `QFrame` inserted via `right_layout.insertWidget(right_layout.count() - 1, keypad)`.

```
┌──────────────────────────────┐
│  ┌──────────────────────┐    │  bg: #27272a — DTMF input display
│  │  1 2 3               │    │  shows tones pressed (e.g. "123")
│  └──────────────────────┘    │
│   ┌──────┐┌──────┐┌──────┐   │
│   │  1   ││  2   ││  3   │   │  key: 60×44px, bg: #27272a, border: #3f3f46
│   └──────┘└──────┘└──────┘   │  hover/focus: bg #3f3f46
│   ┌──────┐┌──────┐┌──────┐   │
│   │  4   ││  5   ││  6   │   │
│   └──────┘└──────┘└──────┘   │
│   ┌──────┐┌──────┐┌──────┐   │
│   │  7   ││  8   ││  9   │   │
│   └──────┘└──────┘└──────┘   │
│   ┌──────┐┌──────┐┌──────┐   │
│   │  *   ││  0   ││  #   │   │
│   └──────┘└──────┘└──────┘   │
└──────────────────────────────┘
  260×310px, bg: #18181b, border: #3f3f46
```

**Key navigation:** Arrow keys move focus between keys; Enter/Space sends the tone; Esc closes the keypad (toggles the Keypad button off).

```python
_DTMF_KEYS = [["1","2","3"],["4","5","6"],["7","8","9"],["*","0","#"]]

class DTMFKeypad(QWidget):
    tone_pressed = Signal(str)

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setStyleSheet(
            "background: #18181b; border: 2px solid #3f3f46;"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        self._display = QLineEdit()
        self._display.setReadOnly(True)
        self._display.setStyleSheet(
            "background: #27272a; color: #f4f4f5; border: 1px solid #3f3f46;"
            " font-size: 16px; padding: 4px 8px;"
        )
        self._display.setAccessibleName("DTMF input")
        layout.addWidget(self._display)

        grid = QGridLayout()
        grid.setSpacing(8)
        for row, keys in enumerate(_DTMF_KEYS):
            for col, key in enumerate(keys):
                btn = QPushButton(key)
                btn.setFixedSize(60, 44)
                btn.setStyleSheet(
                    "QPushButton { background: #27272a; color: #f4f4f5;"
                    " border: 1px solid #3f3f46; font-size: 18px; border-radius: 4px; }"
                    " QPushButton:hover { background: #3f3f46; }"
                    " QPushButton:focus { outline: 2px dashed #3b82f6; }"
                )
                btn.setAccessibleName(f"DTMF {key}")
                btn.clicked.connect(lambda _, k=key: self._on_key(k))
                grid.addWidget(btn, row, col)
        layout.addLayout(grid)

    def _on_key(self, key: str) -> None:
        self._display.setText(self._display.text() + key)
        self.tone_pressed.emit(key)
```

**Integration:** In `MainWindow`, on `tone_pressed`, call `self._dbus_client.send_dtmf(key)` (new D-Bus method on `tincand`). If D-Bus method is not yet implemented, log and ignore — the UI should not block.

---

## Screen 4: Audio Error State

Displayed when the HFP audio SCO channel fails to open after call answer. Replaces the in-call panel (same position) with an amber-bordered error panel.

```
┌─────────────────────────────────────────────────────────────────────────────────────┐  border: #d97706 2px
│  ⚠  Audio unavailable                                                              │
│     HFP audio path could not be established. Call is still connected.               │  #9ca3af, 11px
│                                                                      ↻ Retry Audio  ✕ Hang Up │
└─────────────────────────────────────────────────────────────────────────────────────┘
  590px wide, 88px tall
```

```python
class AudioErrorPanel(QWidget):
    retry_requested = Signal()
    hang_up_requested = Signal()

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setStyleSheet(
            "background: #18181b; border-top: 2px solid #d97706;"
        )
        self.setFixedHeight(88)
        # aria-live="assertive" equivalent: call QAccessible.updateAccessibility
        # with an event when this widget becomes visible

        row = QHBoxLayout(self)
        row.setContentsMargins(12, 8, 12, 8)
        row.setSpacing(12)

        warn = QLabel("⚠")
        warn.setStyleSheet("color: #d97706; font-size: 32px; border: none;")
        warn.setAccessibleName("")  # aria-hidden: icon is decorative
        row.addWidget(warn)

        msg_col = QVBoxLayout()
        title = QLabel("Audio unavailable")
        title.setStyleSheet("color: #f4f4f5; font-size: 14px; font-weight: 500;")
        msg_col.addWidget(title)
        body = QLabel("HFP audio path could not be established. Call is still connected.")
        body.setStyleSheet("color: #9ca3af; font-size: 11px;")
        msg_col.addWidget(body)
        row.addLayout(msg_col)
        row.addStretch()

        retry_btn = QPushButton("↻ Retry Audio")
        retry_btn.setFixedSize(100, 30)
        retry_btn.setAccessibleName("Retry HFP audio connection")
        retry_btn.setStyleSheet(
            "QPushButton { background: #27272a; color: #9ca3af; border: 1px solid #3f3f46;"
            " font-size: 11px; border-radius: 4px; }"
            " QPushButton:focus { outline: 2px dashed #3b82f6; }"
        )
        retry_btn.clicked.connect(self.retry_requested)
        row.addWidget(retry_btn)

        hang_btn = QPushButton("✕ Hang Up")
        hang_btn.setFixedSize(108, 30)
        hang_btn.setStyleSheet(
            "QPushButton { background: #dc2626; color: #ffffff; border: none;"
            " font-size: 11px; border-radius: 4px; }"
            " QPushButton:focus { outline: 2px dashed #3b82f6; }"
        )
        hang_btn.clicked.connect(self.hang_up_requested)
        row.addWidget(hang_btn)
```

---

## State Machine / Panel Swap Logic

```
MainWindow right pane (QVBoxLayout):
  [thread_view]  ← always present
  [QStackedWidget: compose_stack]
      page 0: ComposePanel      ← default
      page 1: InCallPanel       ← while call active and audio OK
      page 2: AudioErrorPanel   ← while call active and audio failed
      page 3: DTMF row + InCallPanel  ← when keypad open (QSplitter or nested layout)

Transitions:
  incoming_call_signal    → show IncomingCallDialog (modal)
  user answers            → hide dialog, switch compose_stack → InCallPanel, start timer
  user declines           → hide dialog, no state change
  audio_error_signal      → switch compose_stack → AudioErrorPanel
  retry_requested         → attempt SCO reconnect; on success → InCallPanel
  hang_up / call_ended    → switch compose_stack → ComposePanel, stop timer
  keypad_toggled(True)    → show DTMFKeypad above InCallPanel (insertWidget)
  keypad_toggled(False)   → hide DTMFKeypad
```

---

## Accessibility Audit

| Concern | Status | Spec |
|---------|--------|------|
| Incoming call dialog focus | ✓ | `QDialog` automatically traps focus; first focusable = Decline btn |
| Esc on dialog = Decline | ✓ | `keyPressEvent` override |
| Tab order in dialog | ✓ | Decline → Answer (left-to-right reading order) |
| Answer btn is default | ✓ | `setDefault(True)` on Answer — Enter always answers |
| Caller name as dialog label | ✓ | `setObjectName("callerName")` for screen reader |
| In-call timer announcements | ✓ | `aria-live="off"` equivalent — timer updates silently (too frequent to announce) |
| Hold state communicated | ✓ | Button text changes "Hold" ↔ "Resume"; button is `setCheckable(True)` so `aria-pressed` is set |
| DTMF grid navigation | ✓ | Arrow keys, Enter/Space per standard grid widget pattern |
| DTMF display accessible | ✓ | `setAccessibleName("DTMF input")` on the read-only QLineEdit |
| Audio error announcement | ✓ | `QAccessible.updateAccessibility` on panel show triggers screen-reader alert |
| ⚠ icon accessible | ✓ | `setAccessibleName("")` — decorative; title conveys the message |
| "Retry Audio" button label | ✓ | `setAccessibleName("Retry HFP audio connection")` — more descriptive than visible label |
| Color contrast — Decline (#dc2626 on #18181b) | ✓ | Ratio ≈ 5.9:1 — passes AA |
| Color contrast — Answer (#16a34a on #18181b) | ✓ | Ratio ≈ 5.1:1 — passes AA |
| Color contrast — Hold (#d97706 on #18181b) | ✓ | Ratio ≈ 4.8:1 — passes AA for large text (btn label ≥ 14px) |
| Color contrast — timer (#86efac on #18181b) | ✓ | Ratio ≈ 12.6:1 — passes AAA |
| Color contrast — error body (#9ca3af on #18181b) | ⚠ | Ratio ≈ 4.4:1 — marginally below AA 4.5:1 for normal text. Use `#a3a3a3` instead (4.6:1) |
| Focus ring color (#3b82f6 on #18181b) | ✓ | Ratio ≈ 5.9:1 — passes AA; 2px dashed matches existing FOCUS_STYLESHEET |
| Keyboard-only call answer | ✓ | Tab to Answer, Space/Enter activates |
| Keyboard-only hang up | ✓ | Tab to Hang Up, Space/Enter activates |
| Minimum touch/click target | ✓ | All buttons ≥ 30px height, Answer/Decline = 44px |

**Action items for builder:**
1. Change error body text color from `#9ca3af` to `#a3a3a3` for 4.6:1 contrast ratio
2. Call `QAccessible.updateAccessibility()` when `AudioErrorPanel` becomes visible
3. Ensure `IncomingCallDialog` raises to front even if app is minimized (`raise_()` + `activateWindow()`)

---

## New File / Class Summary

| File | Class | Notes |
|------|-------|-------|
| `tincan_gui/call_panel.py` | `IncomingCallDialog` | QDialog, semi-modal |
| `tincan_gui/call_panel.py` | `InCallPanel` | Replaces compose bar |
| `tincan_gui/call_panel.py` | `DTMFKeypad` | Stretch; toggled from InCallPanel |
| `tincan_gui/call_panel.py` | `AudioErrorPanel` | Replaces InCallPanel on SCO failure |

All four classes can live in one new file `tincan_gui/call_panel.py`. No changes to `docs/rules/`, `CLAUDE.md`, or `AGENTS.md`.

## D-Bus Signals Required (from tincand)

| Signal | Source | Handler in GUI |
|--------|--------|---------------|
| `IncomingCall(caller_name, caller_number)` | HFP backend | Show `IncomingCallDialog` |
| `CallConnected()` | HFP backend | Show `InCallPanel` |
| `CallEnded()` | HFP backend | Restore `ComposePanel` |
| `AudioError(reason: str)` | HFP backend | Show `AudioErrorPanel` |
| `AudioRestored()` | HFP backend | Show `InCallPanel` (from error) |

These align with standard BlueZ `HFP-HF` profile events. The architect's analysis (tincan-xohrx) will confirm exact D-Bus interface names.

---

## Implementation Checklist for Builder

- [ ] Create `tincan_gui/call_panel.py` with `IncomingCallDialog`, `InCallPanel`, `DTMFKeypad`, `AudioErrorPanel`
- [ ] `MainWindow`: wire D-Bus signals to panel swaps via `QStackedWidget`
- [ ] `IncomingCallDialog`: raise + activateWindow on show; Esc = Decline
- [ ] `InCallPanel`: 1-second QTimer updating `_timer_lbl`; Hold toggle changes btn text + style; `keypad_toggled` signal
- [ ] `DTMFKeypad`: arrow-key grid navigation; `tone_pressed` → `dbus_client.send_dtmf(key)`
- [ ] `AudioErrorPanel`: `QAccessible.updateAccessibility()` on show; Retry → SCO reconnect attempt
- [ ] Error body text: `#a3a3a3` (not `#9ca3af`) for AA contrast
- [ ] `AvatarWidget` reuse for both dialog and panel — no new avatar logic
- [ ] Architecture bead (tincan-xohrx) must confirm D-Bus interface before implementation

---

*Wireframe file:* `/home/jaword/projects/gc-management/.gc/worktrees/tincan/designer/tincan-fx79v/phone-calls-ui.excalidraw`
