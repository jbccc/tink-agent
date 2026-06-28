# Button Actions — Customizable Slot/Mode Mapping

**Date:** 2026-06-28
**Status:** Approved design, ready for implementation plan

## Problem

The Tink mic exposes 8 button slots (2 modes × 4 buttons). Each slot fires a
keyboard action when the white button is pressed (the action is inferred from a
detected tone — see project notes). Today the slot→action map (`config.slot_actions`)
is editable **only by hand-editing `~/.tink-agent/config.json`**, and the router
(`actions.py`) supports just 8 hard-coded actions. There is no UI for this.

## Goal

Add a native macOS "Button Actions" window that lets the user assign each of the 8
slots an action from a curated catalog (~24 entries: keystrokes, combos, and text
macros). Defaults stay identical to today. The screen implements the imported
design `Tink Button Actions.dc.html` ("Map a Button"), rebuilt with native AppKit
components and the existing `theme.py` styling.

## Non-goals

- No change to tone detection, frequencies, or how modes are physically switched.
- No per-slot custom free-text entry (catalog is a fixed predefined list).
- No change to the JSON config schema (string ids already fit).
- Not changing the voice/transcription path.

## Action catalog

A new module-level `ACTION_CATALOG` in `actions.py` is the single source of truth,
shared by the router and the UI. Each entry: `{id, label, glyph}`. Order below is
the dropdown order.

### Keys & combos
| id | label | glyph |
|---|---|---|
| `enter` | Enter | ⏎ |
| `escape` | Escape | ⎋ |
| `esc_esc` | Double Esc (clear input) | ⎋⎋ |
| `ctrl_c` | Ctrl + C (interrupt) | ⌃C |
| `ctrl_d` | Ctrl + D | ⌃D |
| `tab` | Tab | ⇥ |
| `shift_tab` | Shift + Tab (cycle mode) | ⇤ |
| `shift_enter` | Shift + Enter (newline) | ⇧⏎ |
| `up` | Arrow Up | ↑ |
| `down` | Arrow Down | ↓ |
| `left` | Arrow Left | ← |
| `right` | Arrow Right | → |
| `space` | Space | ␣ |
| `backspace` | Backspace | ⌫ |
| `cmd_v` | Paste | ⌘V |
| `key_1` | Type "1" | 1 |
| `key_2` | Type "2" | 2 |
| `key_3` | Type "3" | 3 |
| `noop` | No action | – |

### Text macros
Macros type the string **then press Enter** (so they submit in the agent prompt).
| id | label |
|---|---|
| `type:yes` | Send "yes" |
| `type:continue` | Send "continue" |
| `type:/clear` | Send "/clear" |
| `type:/compact` | Send "/compact" |

### Defaults (unchanged from current config)
```
1: enter      2: escape    3: ctrl_c    4: shift_tab    (Mode A / Bank A)
5: up         6: down      7: noop      8: noop         (Mode B / Bank B)
```

## Router changes (`actions.py`)

- Add `ACTION_CATALOG` (list of `{id, label, glyph}`) and a helper
  `action_label(id)` / `action_exists(id)` for the UI.
- Extend `_perform(action)` to handle the new keystroke ids:
  `esc_esc` (press/release Esc twice), `ctrl_d`, `shift_enter` (Shift held + Enter),
  `left`, `right`, `space`, `backspace`, `cmd_v` (Cmd held + V), `key_1/2/3`
  (type the digit character).
- Add `type:` handling in `fire_slot`/`_perform`: if the action id starts with
  `type:`, type the remainder via the existing typing path, then press Enter.
  Reuses the deferred main-thread dispatch already in place.
- Unknown / unmapped ids remain a safe no-op (returns the id for logging, performs
  nothing) — forward-compatible with future catalog additions.
- `fire_slot` still returns the action id string for logging.

## UI — new window (`button_actions.py`)

A lazily-created `ButtonActionsController` + `NSWindow`, opened from a new
**"Button Actions…"** `MenuItem` in the Settings window (sits beside
"Set Up TINK…"). All controls built from `theme.py` helpers so the look matches
existing screens (Archivo font; palette `BG/CARD/GREEN/ORANGE/MUTED`).

Layout mirrors `Tink Button Actions.dc.html`:

- **Left card — device illustration.** A custom `NSView` subclass
  (`DeviceView`) that draws the Tink device (body, grille, accent buttons, TINK
  AGENT wordmark, cable) via Core Graphics, plus 8 LED dots: one orange "mode"
  LED group and four green "slot" LEDs. The LEDs for the **currently selected
  mode + slot** are lit (filled + brighter); others dim. ORANGE/GREEN/WHITE
  callout pills label the three buttons. Redrawn (`setNeedsDisplay`) whenever
  selection changes.
- **Right column:**
  - **Mode** — `NSSegmentedControl`, 2 segments (Bank A / Bank B). Selecting a
    bank switches the editable slot set: Bank A → slots 1–4, Bank B → slots 5–8.
  - **Slot** — `NSSegmentedControl`, 4 segments (1–4), selecting which button
    within the bank is being edited.
  - **Detail card** — header "Slot {N} · {Hz} Hz" (Hz read-only from
    `config.tones[N]`), a caption ("Bank A · base tone" / "Bank B · tone pitched
    +10.5%"), and an `NSPopUpButton` listing the full catalog (glyph + label).
    The popup's current selection reflects `config.slot_actions[N]`.

`N` (the global slot number 1–8) = `mode_index * 4 + slot_index + 1`.

### Edit flow
Changing the popup calls `app.set_slot_action(N, action_id)`, which:
1. updates `config.slot_actions[N]`,
2. updates the live `engine.router.slot_actions[N]` (so it takes effect without
   restart),
3. saves config to disk (same delegate pattern Settings already uses for toggles).

Mode/slot segment changes only move the editing cursor + relight LEDs; they do not
mutate config.

## Config (`config.py`)

No schema change. `slot_actions` already maps int slot → action-id string, and
`type:*` ids are valid strings. Existing load/save, the str↔int key conversion, and
the mode-B backfill all continue to work.

## Testing

- **`test_actions.py`** (extend): each new keystroke id presses the correct
  pynput keys/modifiers; `type:foo` types "foo" then Enter; unknown id performs
  nothing; `fire_slot` returns the id.
- **`test_button_actions.py`** (new): `ACTION_CATALOG` ids are unique and the
  default `slot_actions` values all exist in the catalog; `(mode_index, slot_index)
  → N` mapping; selecting an action updates both config and the live router and
  persists; LED-lit logic picks the right mode + slot indices. UI controller
  tested with a fake `app` delegate (no live AppKit window), consistent with how
  `test_menubar.py` / settings tests stub AppKit.
- Full `.venv/bin/pytest` suite stays green.

## Files touched

| File | Change |
|---|---|
| `tink_agent/actions.py` | `ACTION_CATALOG`, expanded `_perform`, `type:` handling, helpers |
| `tink_agent/button_actions.py` | **new** — window controller + `DeviceView` |
| `tink_agent/settings_ui.py` | add "Button Actions…" link/button opening the window |
| `tink_agent/menubar.py` | lazily build `ButtonActionsController`; add `set_slot_action` delegate |
| `tests/test_actions.py` | new-action + macro tests |
| `tests/test_button_actions.py` | **new** |
