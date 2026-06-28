# Button Actions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a native macOS "Map a Button" window that lets the user assign each of the 8 Tink slots an action from a ~24-entry catalog (keystrokes, combos, text macros), implementing the imported `Tink Button Actions.dc.html` design.

**Architecture:** A module-level `ACTION_CATALOG` in `actions.py` becomes the single source of truth for what each action id does (router) and how it appears (UI). The router gains the new keystrokes/combos plus `type:<text>` macro handling. A new `button_actions.py` builds a themed AppKit window (device illustration with live LEDs + Mode/Slot segmented controls + an action popup) that delegates edits to a new `TinkAgentApp.set_slot_action`, which persists config and updates the running router. Opened from a link in the Settings window.

**Tech Stack:** Python, pyobjc (AppKit), rumps, pynput, pytest. macOS-only.

## Global Constraints

- All UI built from `tink_agent/theme.py` helpers (Archivo font; palette `BG/CARD/GREEN/ORANGE/MUTED/SUBTLE`). No raw colors except inside the device drawing.
- All keyboard side effects go through `ActionRouter` and its deferred main-thread dispatch — never call pynput directly elsewhere.
- No change to the config JSON schema. `slot_actions` stays `{int slot: str action-id}`. Defaults unchanged: `1:enter 2:escape 3:ctrl_c 4:shift_tab 5:up 6:down 7:noop 8:noop`.
- Bank A = slots 1–4, Bank B = slots 5–8. Global slot number `N = mode_index*4 + slot_index + 1`.
- Text macros (`type:<text>`) type the literal text **then press Enter**.
- Tests run with `.venv/bin/pytest`. Keep the whole suite green.
- Unknown/unmapped action ids must be a safe no-op (forward-compatible).

---

### Task 1: Action catalog + router extension

**Files:**
- Modify: `tink_agent/actions.py`
- Test: `tests/test_actions.py`

**Interfaces:**
- Produces: `ACTION_CATALOG` (list of `{"id": str, "label": str, "glyph": str}`), `action_label(action_id: str) -> str`. Router `_perform` handles new ids: `esc_esc, ctrl_d, shift_enter, left, right, space, backspace, cmd_v, key_1, key_2, key_3`, and any `type:<text>` id.
- Consumes: existing `ActionRouter.fire_slot`, `_perform`, `_do_type`.

- [ ] **Step 1: Extend FakeKey/FakeKeyboard in the test file**

In `tests/test_actions.py`, replace the `FakeKey` class with one carrying every key the catalog uses:

```python
class FakeKey:
    enter = "ENTER"
    esc = "ESC"
    ctrl = "CTRL"
    shift = "SHIFT"
    cmd = "CMD"
    tab = "TAB"
    up = "UP"
    down = "DOWN"
    left = "LEFT"
    right = "RIGHT"
    space = "SPACE"
    backspace = "BACKSPACE"
```

- [ ] **Step 2: Write the failing tests**

Append to `tests/test_actions.py`:

```python
from tink_agent.actions import ACTION_CATALOG, action_label


def test_catalog_entries_well_formed_and_ids_unique():
    ids = [a["id"] for a in ACTION_CATALOG]
    assert len(ids) == len(set(ids))                 # unique
    for a in ACTION_CATALOG:
        assert a["id"] and a["label"] and a["glyph"]  # all fields present
    assert "noop" in ids


def test_default_slot_actions_are_all_in_catalog():
    from tink_agent.config import Config
    ids = {a["id"] for a in ACTION_CATALOG}
    for action in Config().slot_actions.values():
        assert action in ids


def test_action_label_falls_back_for_unknown():
    assert action_label("enter") == "Enter"
    assert action_label("totally_unknown") == "totally_unknown"


def test_cmd_v_holds_cmd():
    kb = FakeKeyboard()
    r = ActionRouter({1: "cmd_v"}, keyboard=kb)
    assert r.fire_slot(1) == "cmd_v"
    assert ("hold", "CMD") in kb.events
    assert ("press", "v") in kb.events


def test_shift_enter_holds_shift():
    kb = FakeKeyboard()
    ActionRouter({1: "shift_enter"}, keyboard=kb).fire_slot(1)
    assert ("hold", "SHIFT") in kb.events
    assert ("press", "ENTER") in kb.events


def test_esc_esc_presses_escape_twice():
    kb = FakeKeyboard()
    ActionRouter({1: "esc_esc"}, keyboard=kb).fire_slot(1)
    assert kb.events.count(("press", "ESC")) == 2


def test_key_digit_types_char():
    kb = FakeKeyboard()
    ActionRouter({1: "key_2"}, keyboard=kb).fire_slot(1)
    assert ("press", "2") in kb.events and ("release", "2") in kb.events


def test_type_macro_types_text_then_enter():
    kb = FakeKeyboard()
    r = ActionRouter({1: "type:continue"}, keyboard=kb)
    assert r.fire_slot(1) == "type:continue"
    assert ("type", "continue") in kb.events
    assert ("press", "ENTER") in kb.events          # macro submits


def test_unknown_action_is_safe_noop():
    kb = FakeKeyboard()
    r = ActionRouter({1: "bogus"}, keyboard=kb)
    assert r.fire_slot(1) == "bogus"                # returned for logging
    assert kb.events == []                          # but nothing performed
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_actions.py -q`
Expected: FAIL — `ImportError: cannot import name 'ACTION_CATALOG'` (and new behavior tests fail).

- [ ] **Step 4: Add the catalog + helper to `actions.py`**

Insert at the top of `tink_agent/actions.py`, right after `from __future__ import annotations`:

```python
# Catalog of selectable per-slot actions: the single source of truth shared by
# the router (what an id does, below) and the Button Actions UI (label + glyph).
# `type:<text>` ids type the literal text then press Enter (submit).
ACTION_CATALOG = [
    {"id": "enter",         "label": "Enter",                  "glyph": "⏎"},
    {"id": "escape",        "label": "Escape",                 "glyph": "⎋"},
    {"id": "esc_esc",       "label": "Double Esc (clear)",     "glyph": "⎋⎋"},
    {"id": "ctrl_c",        "label": "Ctrl + C (interrupt)",   "glyph": "⌃C"},
    {"id": "ctrl_d",        "label": "Ctrl + D",               "glyph": "⌃D"},
    {"id": "tab",           "label": "Tab",                    "glyph": "⇥"},
    {"id": "shift_tab",     "label": "Shift + Tab (mode)",     "glyph": "⇤"},
    {"id": "shift_enter",   "label": "Shift + Enter (newline)","glyph": "⇧⏎"},
    {"id": "up",            "label": "Arrow Up",               "glyph": "↑"},
    {"id": "down",          "label": "Arrow Down",             "glyph": "↓"},
    {"id": "left",          "label": "Arrow Left",             "glyph": "←"},
    {"id": "right",         "label": "Arrow Right",            "glyph": "→"},
    {"id": "space",         "label": "Space",                  "glyph": "␣"},
    {"id": "backspace",     "label": "Backspace",              "glyph": "⌫"},
    {"id": "cmd_v",         "label": "Paste",                  "glyph": "⌘V"},
    {"id": "key_1",         "label": "Type “1”",     "glyph": "1"},
    {"id": "key_2",         "label": "Type “2”",     "glyph": "2"},
    {"id": "key_3",         "label": "Type “3”",     "glyph": "3"},
    {"id": "type:yes",      "label": "Send “yes”",       "glyph": "y"},
    {"id": "type:continue", "label": "Send “continue”",  "glyph": "»"},
    {"id": "type:/clear",   "label": "Send /clear",            "glyph": "/"},
    {"id": "type:/compact", "label": "Send /compact",          "glyph": "/"},
    {"id": "noop",          "label": "No action",              "glyph": "–"},
]

_CATALOG_BY_ID = {a["id"]: a for a in ACTION_CATALOG}


def action_label(action_id: str) -> str:
    a = _CATALOG_BY_ID.get(action_id)
    return a["label"] if a else (action_id or "No action")
```

- [ ] **Step 5: Extend `_perform` for the new actions**

In `tink_agent/actions.py`, replace the `_perform` method body's trailing branches. The method currently ends at the `down` branch (lines ~60-63). Append these `elif` branches **after** the existing `elif action == "down":` block, before `type_text`:

```python
        elif action == "esc_esc":
            kb.press(Key.esc); kb.release(Key.esc)
            kb.press(Key.esc); kb.release(Key.esc)
        elif action == "ctrl_d":
            with kb.pressed(Key.ctrl):
                kb.press("d"); kb.release("d")
        elif action == "shift_enter":
            with kb.pressed(Key.shift):
                kb.press(Key.enter); kb.release(Key.enter)
        elif action == "left":
            kb.press(Key.left); kb.release(Key.left)
        elif action == "right":
            kb.press(Key.right); kb.release(Key.right)
        elif action == "space":
            kb.press(Key.space); kb.release(Key.space)
        elif action == "backspace":
            kb.press(Key.backspace); kb.release(Key.backspace)
        elif action == "cmd_v":
            with kb.pressed(Key.cmd):
                kb.press("v"); kb.release("v")
        elif action in ("key_1", "key_2", "key_3"):
            ch = action[-1]
            kb.press(ch); kb.release(ch)
        elif action.startswith("type:"):
            self._do_type(action[len("type:"):])
            kb.press(Key.enter); kb.release(Key.enter)
```

(No change to `fire_slot` is needed: `type:*` and the new ids are non-`None`, non-`"noop"`, so they already dispatch into `_perform`. Unknown ids fall through every branch and perform nothing — the safe no-op.)

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_actions.py -q`
Expected: PASS (all, including the pre-existing tests).

- [ ] **Step 7: Commit**

```bash
git add tink_agent/actions.py tests/test_actions.py
git commit -m "feat: action catalog + expanded router (combos, arrows, paste, type macros)"
```

---

### Task 2: `set_slot_action` delegate on TinkAgentApp

**Files:**
- Modify: `tink_agent/menubar.py` (add method near the other `set_*` setters, ~line 195)
- Test: `tests/test_menubar.py`

**Interfaces:**
- Produces: `TinkAgentApp.set_slot_action(self, slot: int, action_id: str)` — writes `config.slot_actions[slot]`, saves, and updates the live `engine.router.slot_actions[slot]`.
- Consumes: `self.config.slot_actions`, `self.config.save()`, `self.engine.router.slot_actions` (the router built in `_build_engine`).

- [ ] **Step 1: Write the failing test**

Append to `tests/test_menubar.py`:

```python
def test_set_slot_action_persists_and_updates_live_router():
    calls = []
    cfg = SimpleNamespace(slot_actions={1: "enter"},
                          save=lambda: calls.append("save"))
    router = SimpleNamespace(slot_actions={1: "enter"})
    app = SimpleNamespace(config=cfg, engine=SimpleNamespace(router=router))

    TinkAgentApp.set_slot_action(app, 1, "type:continue")

    assert cfg.slot_actions[1] == "type:continue"   # persisted to config
    assert router.slot_actions[1] == "type:continue" # applied without restart
    assert calls == ["save"]


def test_set_slot_action_coerces_slot_to_int():
    cfg = SimpleNamespace(slot_actions={}, save=lambda: None)
    router = SimpleNamespace(slot_actions={})
    app = SimpleNamespace(config=cfg, engine=SimpleNamespace(router=router))
    TinkAgentApp.set_slot_action(app, "5", "down")
    assert cfg.slot_actions[5] == "down"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_menubar.py::test_set_slot_action_persists_and_updates_live_router -q`
Expected: FAIL — `AttributeError: type object 'TinkAgentApp' has no attribute 'set_slot_action'`.

- [ ] **Step 3: Add the method**

In `tink_agent/menubar.py`, add after `set_device_name` (around line 202, before `rescan_devices`):

```python
    def set_slot_action(self, slot, action_id: str):
        """Assign the action a slot fires. Persists to config and updates the
        running router so it takes effect without restarting capture."""
        slot = int(slot)
        self.config.slot_actions[slot] = action_id
        self.config.save()
        self.engine.router.slot_actions[slot] = action_id
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_menubar.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tink_agent/menubar.py tests/test_menubar.py
git commit -m "feat: TinkAgentApp.set_slot_action persists + applies to live router"
```

---

### Task 3: Button Actions window (`button_actions.py`) + segmented theme helper

**Files:**
- Modify: `tink_agent/theme.py` (add `segmented(...)` helper + imports)
- Create: `tink_agent/button_actions.py`
- Test: `tests/test_button_actions.py`

**Interfaces:**
- Produces: `theme.segmented(titles, selected, on_select, x, y, w, h=26) -> NSSegmentedControl`.
- Produces (button_actions.py): `slot_number(mode_index, slot_index) -> int`; `catalog_index_of(action_id) -> int`; `ButtonActionsController` (NSObject) with `initWithApp_`, `show`, and python_method `_apply_action_index(catalog_index)`; `DeviceView` (NSView) with `set_selection_(mode_index, slot_index)`.
- Consumes: `TinkAgentApp.set_slot_action`, `app.config.slot_actions`, `app.config.tones`, `actions.ACTION_CATALOG`, `theme.*`.

- [ ] **Step 1: Write the failing tests (pure logic)**

Create `tests/test_button_actions.py`:

```python
from types import SimpleNamespace

from tink_agent.button_actions import (
    slot_number, catalog_index_of, ButtonActionsController,
)
from tink_agent.actions import ACTION_CATALOG


def test_slot_number_maps_bank_and_button_to_1_to_8():
    assert slot_number(0, 0) == 1     # Bank A, button 1
    assert slot_number(0, 3) == 4     # Bank A, button 4
    assert slot_number(1, 0) == 5     # Bank B, button 1
    assert slot_number(1, 3) == 8     # Bank B, button 4


def test_catalog_index_roundtrips():
    for i, a in enumerate(ACTION_CATALOG):
        assert catalog_index_of(a["id"]) == i


def test_catalog_index_unknown_falls_back_to_noop_entry():
    noop_i = next(i for i, a in enumerate(ACTION_CATALOG) if a["id"] == "noop")
    assert catalog_index_of("nope") == noop_i


def test_apply_action_index_calls_delegate_with_slot_number_and_id():
    calls = []
    fake_app = SimpleNamespace(set_slot_action=lambda n, a: calls.append((n, a)))
    # Build a controller without its AppKit window (plain init, then inject state).
    c = ButtonActionsController.alloc().init()
    c.app = fake_app
    c._mode_index = 1
    c._slot_index = 2                 # -> slot_number(1, 2) == 7
    enter_i = catalog_index_of("enter")
    c._apply_action_index(enter_i)
    assert calls == [(7, "enter")]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_button_actions.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'tink_agent.button_actions'`.

- [ ] **Step 3: Add the `segmented` helper to `theme.py`**

In `tink_agent/theme.py`, add `NSSegmentedControl` and `NSSegmentStyleRounded` to the AppKit import block that begins at line 91 (`from AppKit import (`). Then add this function after `popup_row` (after line 289):

```python
def segmented(titles, selected, on_select, x, y, w, h=26):
    """A themed NSSegmentedControl. `on_select` receives the selected index."""
    seg = NSSegmentedControl.alloc().initWithFrame_(NSMakeRect(x, y, w, h))
    seg.setSegmentStyle_(NSSegmentStyleRounded)
    seg.setSegmentCount_(len(titles))
    seg.setFont_(font(13, "medium"))
    for i, t in enumerate(titles):
        seg.setLabel_forSegment_(t, i)
        seg.setWidth_forSegment_(float(w) / len(titles), i)
    seg.setSelectedSegment_(selected)
    t = _Target.alloc().initWithCb_(lambda: on_select(int(seg.selectedSegment())))
    seg.setTarget_(t)
    seg.setAction_("fire:")
    _retain(seg, t)
    return seg
```

- [ ] **Step 4: Create `tink_agent/button_actions.py`**

```python
"""Native (AppKit) 'Map a Button' window — themed via theme.py.

Lets the user assign each of the 8 Tink slots (2 banks x 4 buttons) an action
from ACTION_CATALOG. Delegates persistence to TinkAgentApp.set_slot_action.
Main thread only. Implements the imported `Tink Button Actions.dc.html` design.
"""
from __future__ import annotations

import objc
from AppKit import NSApplication, NSMakeRect, NSBezierPath
from Foundation import NSObject

from . import theme
from .actions import ACTION_CATALOG

W, H = 600, 408
M = 18
DEVICE_W = 286


def slot_number(mode_index: int, slot_index: int) -> int:
    """Global slot id 1-8. Bank A (mode 0) -> 1-4, Bank B (mode 1) -> 5-8."""
    return mode_index * 4 + slot_index + 1


def catalog_index_of(action_id: str) -> int:
    for i, a in enumerate(ACTION_CATALOG):
        if a["id"] == action_id:
            return i
    return next(i for i, a in enumerate(ACTION_CATALOG) if a["id"] == "noop")


def _popup_titles():
    return [f"{a['glyph']}   {a['label']}" for a in ACTION_CATALOG]


class DeviceView(theme.Flipped):
    """Draws a stylized Tink device; lights the LED for the selected bank+slot."""

    def initWithFrame_(self, frame):
        self = objc.super(DeviceView, self).initWithFrame_(frame)
        if self is None:
            return None
        self._mode_index = 0
        self._slot_index = 0
        return self

    @objc.python_method
    def set_selection_(self, mode_index, slot_index):
        self._mode_index = mode_index
        self._slot_index = slot_index
        self.setNeedsDisplay_(True)

    def drawRect_(self, rect):
        b = self.bounds()
        tan = theme.color("#D9D0B7"); cream = theme.color("#EFEBDF")
        dark = theme.color("#231F20")
        green = theme.GREEN; orange = theme.ORANGE
        bw, bh = 150, 232
        bx = (b.size.width - bw) / 2.0 + 8
        by = (b.size.height - bh) / 2.0

        def rrect(x, y, w, h, r):
            return NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
                NSMakeRect(x, y, w, h), r, r)

        # green handle (left)
        green.setFill(); rrect(bx - 24, by + 24, 26, bh - 70, 7).fill()
        # body: tan top, cream bottom, green outline
        tan.setFill(); rrect(bx, by, bw, bh * 0.52, 11).fill()
        cream.setFill(); rrect(bx, by + bh * 0.46, bw, bh * 0.54, 11).fill()
        outline = rrect(bx, by, bw, bh, 11)
        green.setStroke(); outline.setLineWidth_(2.0); outline.stroke()
        # grille block on the tan area
        dark.setFill()
        rrect(bx + 16, by + 16, bw - 70, bh * 0.52 - 32, 4).fill()
        # accent buttons on the right edge: orange (mode), green (slot), white (fire)
        orange.setFill(); rrect(bx + bw - 20, by + 14, 26, 26, 6).fill()
        green.setFill(); rrect(bx + bw - 20, by + 56, 26, 26, 6).fill()
        cream.setFill(); wb = rrect(bx + bw - 20, by + 150, 26, 26, 6)
        wb.fill(); green.setStroke(); wb.setLineWidth_(2.0); wb.stroke()
        # wordmark
        theme._attr_title("TINK", theme.font(20, "bold"), orange).drawAtPoint_(
            (bx + 14, by + bh - 52))
        theme._attr_title("AGENT", theme.font(10, "semibold"), green).drawAtPoint_(
            (bx + 15, by + bh - 30))

        # LED dots: 2 mode dots (A/B) over 4 slot dots, near the right grille edge.
        def dot(cx, cy, lit, on_color):
            d = NSBezierPath.bezierPathWithOvalInRect_(
                NSMakeRect(cx - 5, cy - 5, 10, 10))
            (on_color if lit else theme.color("#3A352F")).setFill()
            d.fill()

        lx = bx + bw - 44
        for i in range(2):                                  # mode dots
            dot(lx, by + 26 + i * 16, i == self._mode_index, orange)
        for i in range(4):                                  # slot dots
            dot(lx, by + 74 + i * 16, i == self._slot_index, theme.color("#2FA56B"))


class ButtonActionsController(NSObject):
    def initWithApp_(self, app):
        self = objc.super(ButtonActionsController, self).init()
        if self is None:
            return None
        self.app = app
        self._mode_index = 0
        self._slot_index = 0
        self._build()
        return self

    @objc.python_method
    def _build(self):
        win, c = theme.window("Map a Button", W, H)
        self.window = win

        # left: device card
        dcard = theme.card(M, M, DEVICE_W, H - 2 * M)
        self.device = DeviceView.alloc().initWithFrame_(
            NSMakeRect(0, 0, DEVICE_W, H - 2 * M))
        dcard.contentView().addSubview_(self.device)
        c.addSubview_(dcard)

        # right column
        rx = M + DEVICE_W + 16
        rw = W - rx - M
        y = M + 4

        mh = theme.section_header("Orange button · Mode")
        mh.setFrame_(NSMakeRect(rx, y, rw, 16)); c.addSubview_(mh); y += 22
        self.seg_mode = theme.segmented(
            ["Bank A", "Bank B"], 0, self._on_mode, rx, y, rw, 26)
        c.addSubview_(self.seg_mode); y += 40

        sh = theme.section_header("Green button · Slot")
        sh.setFrame_(NSMakeRect(rx, y, rw, 16)); c.addSubview_(sh); y += 22
        self.seg_slot = theme.segmented(
            ["1", "2", "3", "4"], 0, self._on_slot, rx, y, rw, 26)
        c.addSubview_(self.seg_slot); y += 44

        # detail card
        ch = 150
        card = theme.card(rx, y, rw, ch)
        body = card.contentView()
        self.hdr = theme.label("Slot 1", size=17, weight="bold", color=theme.GREEN)
        self.hdr.setFrame_(NSMakeRect(14, 12, rw - 28, 22)); body.addSubview_(self.hdr)
        self.cap = theme.label("", size=12, color=theme.SUBTLE)
        self.cap.setFrame_(NSMakeRect(14, 36, rw - 28, 16)); body.addSubview_(self.cap)
        wl = theme.label("WHITE BUTTON FIRES", size=10.5, weight="semibold",
                         color=theme.MUTED)
        wl.setFrame_(NSMakeRect(14, 64, rw - 28, 14)); body.addSubview_(wl)
        _, self.popup = theme.popup_row("", rw, 84, h=40)
        # popup_row puts the popup at x=130; widen/relocate it to fill the card.
        self.popup.setFrame_(NSMakeRect(14, 92, rw - 28, 26))
        self.popup.addItemsWithTitles_(_popup_titles())
        self._wire_popup()
        body.addSubview_(self.popup)
        c.addSubview_(card); y += ch + 10

        hint = theme.label(
            "Orange + Green together choose one of 8 slots. The mic's lights "
            "mirror your selection.", size=11.5, color=theme.SUBTLE, wrap=True)
        hint.setFrame_(NSMakeRect(rx, y, rw, 34)); c.addSubview_(hint)

    @objc.python_method
    def _wire_popup(self):
        t = theme._Target.alloc().initWithCb_(
            lambda: self._apply_action_index(int(self.popup.indexOfSelectedItem())))
        self.popup.setTarget_(t)
        self.popup.setAction_("fire:")
        theme._retain(self.popup, t)

    # --- callbacks ---
    @objc.python_method
    def _on_mode(self, index):
        self._mode_index = index
        self._update_detail()

    @objc.python_method
    def _on_slot(self, index):
        self._slot_index = index
        self._update_detail()

    @objc.python_method
    def _apply_action_index(self, catalog_index):
        action_id = ACTION_CATALOG[catalog_index]["id"]
        self.app.set_slot_action(slot_number(self._mode_index, self._slot_index),
                                 action_id)

    @objc.python_method
    def _update_detail(self):
        n = slot_number(self._mode_index, self._slot_index)
        hz = self.app.config.tones.get(n, "—")
        self.hdr.setStringValue_(f"Slot {n}  ·  {hz} Hz")
        self.cap.setStringValue_(
            "Bank B · tone pitched +10.5%" if self._mode_index == 1
            else "Bank A · base tone")
        current = self.app.config.slot_actions.get(n, "noop")
        self.popup.selectItemAtIndex_(catalog_index_of(current))
        self.device.set_selection_(self._mode_index, self._slot_index)

    # --- show ---
    @objc.python_method
    def show(self):
        self._update_detail()
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        self.window.makeKeyAndOrderFront_(None)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_button_actions.py tests/test_theme.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add tink_agent/theme.py tink_agent/button_actions.py tests/test_button_actions.py
git commit -m "feat: Map a Button window (device LEDs, mode/slot segmented, action popup)"
```

---

### Task 4: Wire the window into the menu bar and Settings

**Files:**
- Modify: `tink_agent/menubar.py` (init field + `open_button_actions`)
- Modify: `tink_agent/settings_ui.py` (add a link button)

**Interfaces:**
- Consumes: `ButtonActionsController.alloc().initWithApp_(self)` and `.show()` from Task 3; `app.open_button_actions` from the Settings link.

- [ ] **Step 1: Add the lazy controller field**

In `tink_agent/menubar.py` `__init__`, after `self._settings = None` (line 37), add:

```python
        self._button_actions = None  # lazily-created Button Actions window
```

- [ ] **Step 2: Add the opener method**

In `tink_agent/menubar.py`, add after `open_settings` (around line 235):

```python
    def open_button_actions(self, _=None):
        if self._button_actions is None:
            from .button_actions import ButtonActionsController
            self._button_actions = ButtonActionsController.alloc().initWithApp_(self)
        self._button_actions.show()
```

- [ ] **Step 3: Add the Settings link**

In `tink_agent/settings_ui.py`, in `_build`, after the two existing `link_button` calls (the "Open activity log" block ends at line 145), add:

```python
        c.addSubview_(theme.link_button("Edit button actions",
                                        lambda: self.app.open_button_actions(None),
                                        m + 4, y + 40, 160))
```

- [ ] **Step 4: Run the full test suite**

Run: `.venv/bin/pytest -q`
Expected: PASS (all tests green).

- [ ] **Step 5: Manual verification (launch the app)**

Run: `.venv/bin/python -m tink_agent` (package dir confirmed as `tink_agent/` with a `__main__.py`).

Verify, then quit:
- Menu bar → Settings… → "Edit button actions" opens the "Map a Button" window.
- Mode segmented control switches Bank A/B; Slot 1–4 switches; header shows `Slot N · {Hz} Hz` with the right Hz from config; device LEDs light for the selected bank + slot.
- Changing the action popup updates `~/.tink-agent/config.json` `slot_actions` for the right slot number (check the file).
- Reopen the window: the popup shows the saved action for each slot.

- [ ] **Step 6: Commit**

```bash
git add tink_agent/menubar.py tink_agent/settings_ui.py
git commit -m "feat: open Button Actions window from Settings"
```

---

## Self-Review Notes

- **Spec coverage:** Catalog (Task 1) ✓; router combos + macros (Task 1) ✓; no config schema change (verified — Task 2 writes existing `slot_actions`) ✓; separate window opened from Settings (Tasks 3–4) ✓; device illustration w/ live LEDs (Task 3 `DeviceView`) ✓; mode/slot selectors + popup (Task 3) ✓; live router update (Task 2) ✓; tests (every task) ✓.
- **Type consistency:** `slot_number(mode_index, slot_index)`, `catalog_index_of(action_id)`, `set_slot_action(slot, action_id)`, `ACTION_CATALOG` entry keys `id/label/glyph` — used consistently across tasks and tests.
- **Placeholder scan:** none — every code step is complete. Package name confirmed as `tink_agent`.
