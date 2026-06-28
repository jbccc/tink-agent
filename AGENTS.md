# AGENTS.md — tink-agent developer guide

Onboarding for engineers joining **tink-agent**. Assumes you're mid/senior but new
to this repo. Read this top-to-bottom once (~15 min); afterwards use it as an index.

Companion docs:
- **`TING.md`** — the hardware: how the EP-2350 "Ting" mic works, its `config.json`
  schema, the deployment steps, and device gotchas. Read it before touching anything
  audio- or device-related.
- `README.md` — user-facing install/run instructions.

---

## 1. What this is

A macOS **menu-bar app** that turns a Teenage Engineering EP-2350 "Ting" handheld mic
into a **voice + button controller for AI agent harnesses** (Claude Code, Codex, etc.).

- **Voice** → transcribed (MacWhisper) → typed into the focused app.
- **Mic buttons** → recognized as audio tones → synthesized keystrokes
  (Enter / Esc / Ctrl-C / Shift-Tab).

The whole thing runs off **one audio input stream** and fans it to two consumers. The
mic has **no data link to the computer** — the only signal in is audio — so both voice
and buttons are decoded from that single stream. Internalize this; it explains the
entire architecture.

### The one hardware fact that shapes everything

The mic's USB-C is **power + file storage only**. Its audio reaches the Mac via the
analog line-out → a USB audio adapter that appears as the input device named
**"USB Audio Device"**. The buttons send no HID/MIDI/keyboard events. So:

- "Button press" is implemented as: the mic plays a short **pure tone** sample (you
  configure these on the device), and we **detect that tone** in the audio stream.
- "Push-to-talk" is the mic's **handle**: the device only emits audio while the handle
  is squeezed. We don't get a PTT signal — we infer speech from audio energy. The
  handle is the only PTT; the app always listens.

See `TING.md` for the full device model and the **critical handle-pitch-modulation
gotcha** (you must ship a device `config.json` with a fixed-pitch SAMPLE preset, or
button tones get pitch-shifted into the speech band and become undetectable).

---

## 2. Tech stack

| Concern | Choice | Notes |
|---|---|---|
| Language | Python 3.14 | venv at `.venv` |
| Menu bar UI | `rumps` 0.4 | thin wrapper over `NSStatusItem` |
| Settings/onboarding UI | `pyobjc` (AppKit) | native windows themed via `theme.py`, see `settings_ui.py` |
| Audio capture | `sounddevice` (PortAudio) | input stream, int16 blocks |
| DSP / detection | `numpy` + Goertzel | tone detection, energy VAD |
| Transcription | MacWhisper `mw` CLI | shelled out, not a library |
| Keystrokes | `pynput` | needs Accessibility permission |
| Frontmost app | AppKit `NSWorkspace` | for the target-app guard + logging |
| Auto-start / packaging | **LaunchAgent** | NOT a `.app` (see §8) |
| Tests | `pytest` | all logic unit-tested offline |

There is **no build step** for the app itself — it runs as `python -m tink_agent`.
Packaging = a LaunchAgent plist that runs exactly that.

---

## 3. Architecture & processing pipeline

```
 mic handle held → device line-out → USB adapter (default "USB Audio Device"; user-selectable)
        │
   AudioCapture (sounddevice InputStream, 16 kHz mono int16, 800-sample/50 ms blocks)
        │  on_block(block)  — runs on the PortAudio callback thread
        ▼
   Engine.handle_block(block)
        ├─▶ ToneDetector.process(block) → slot|None      (Goertzel @ 4 freqs + tonality)
        │        └─ slot fired → ActionRouter.fire_slot() → pynput keystroke
        │                         (+ ActivityLogger.action, + on_event)
        │
        └─▶ VoiceGate.process(block, detector.tone_active) → utterance|None  (energy VAD)
                 └─ utterance closed → submit_fn(worker thread):
                        Transcriber.transcribe() → mw CLI → text
                        └─ ActionRouter.type_text(text) → pynput types
                                            (+ ActivityLogger.transcript, + on_event)
```

Key properties of this flow — **do not break these**:

1. **Tone detection runs first**, then voice gating, because `VoiceGate` reads
   `detector.tone_active` to **exclude tone frames** from the speech buffer. Order
   matters (set in `Engine.handle_block`).
2. **Transcription never runs on the audio thread.** It's slow (shells out to `mw`),
   so it's dispatched via `submit_fn` (a single-worker `ThreadPoolExecutor` by
   default). The audio callback must stay fast or PortAudio drops blocks.
3. **UI is updated only on the main thread.** Background threads (audio + worker)
   never touch AppKit/rumps — they stash state into plain attributes, and a
   `rumps.Timer` (`TinkAgentApp._tick`, ~5 Hz) renders it. See §6.
4. **Two independent gates**: `Engine.enabled` (allowed to act at all) and the
   **target-app guard** (`_target_ok`, only act when an allowed app is frontmost).

### Why tones vs. speech don't cross-trigger

- Speech can't fire a button: tone detection requires **both** strong single-frequency
  *dominance* AND high *tonality* (the winning bin must hold most of the block's total
  energy). Pure tones score ~1.0 tonality; speech ~0.0. Measured, not guessed.
- Tones can't pollute transcripts: `tone_active` blocks are dropped from the voice
  buffer, and short tone-edge blips fall under `min_utterance_ms` and are discarded.

---

## 4. Module map (`tink_agent/`)

Each file has one responsibility. Sizes are small on purpose — keep them that way.

| File | Responsibility | Key API |
|---|---|---|
| `config.py` | Load/save `~/.tink-agent/config.json` | `Config` dataclass, `Config.load/save/from_dict` |
| `audio.py` | Open the input stream; resolve/enumerate input devices; re-init PortAudio for a fresh device scan | `AudioCapture`, `resolve_device`, `input_device_names`, `reinitialize`, `DeviceNotFound` |
| `detector.py` | Tone detection + voice activity detection | `goertzel`, `ToneDetector`, `VoiceGate` |
| `transcribe.py` | Wrap the `mw` CLI | `Transcriber`, `write_wav` |
| `actions.py` | Map slots→keystrokes/macros; type text; action catalog | `ActionRouter`, `ACTION_CATALOG` |
| `engine.py` | Wire consumers, threading, gates, logging | `Engine.handle_block` |
| `activity_log.py` | Optional TSV activity log | `ActivityLogger` |
| `launchagent.py` | macOS auto-start (LaunchAgent) | `set_run_at_login`, `install_and_start`, `uninstall` |
| `menubar.py` | rumps app, lifecycle, shared setters | `TinkAgentApp`, `rescan_devices`, `main` |
| `theme.py` | Native-leaning AppKit theme: warm window, NSBox grouped cards, `NSSwitch`/`NSPopUpButton` row builders, accent/link buttons, onboarding step row; registers bundled Archivo from `assets/fonts/`. Targets retained in a module list (native controls reject attrs) | `window`, `card`, `switch_row`, `popup_row`, `accent_button`, `StepRow`, palette |
| `settings_ui.py` | Native AppKit Settings window, themed via `theme` (incl. Audio source dropdown + Refresh) | `SettingsController` |
| `setup_checks.py` | Pure-logic checks behind onboarding (perms, TINGDISK, copy) | `mic_status`, `copy_device_config`, `files_match` |
| `onboarding.py` | First-run "Set up TINK" window, themed via `theme` (4 steps + usage, incl. Audio source picker) | `OnboardingController` |
| `button_actions.py` | "Map a Button" window (opened from Settings): SVG device w/ live mode+slot LEDs, Bank/Slot segmented controls, action popup; edits go to `set_slot_action` | `ButtonActionsController`, `slot_number` |
| `__main__.py` | `python -m tink_agent` entry | calls `menubar.main()` |

### 4.1 `config.py` — single source of truth

`Config` is a `@dataclass` of every tunable. Defaults are the **validated** values
(don't change without re-measuring on hardware). Persisted as JSON at
`~/.tink-agent/config.json`. `load()` writes defaults on first run.

Gotchas:
- JSON object keys are strings, so `tones` and `slot_actions` (int-keyed) are converted
  in `to_dict`/`from_dict`. Follow that pattern for any new int-keyed map.
- **Migrations** live in `from_dict` (e.g. legacy `target_app` → `target_apps` list).
- Unknown keys are dropped on load (forward/backward compatible).

Important fields:
```
device_name="USB Audio Device"   # selectable via Settings / onboarding "Audio source" dropdown
sample_rate=16000   block_size=800
# 8 slots: 1-4 = mode A (orange pos 0), 5-8 = mode B (orange pos 1, pitch +10.5).
# Mode-B freqs hardware-validated 2026-06-27 (measured within +-9 Hz of nominal).
tones={1:1500,2:2300,3:3100,4:3900, 5:2751,6:4218,7:5685,8:7153}   tone_rms_min=1000
tone_dominance_min=0.9   tone_tonality_min=0.5   tone_debounce_ms=300
vad_rms_start=800  vad_rms_end=500  vad_hangover_ms=800
min_utterance_ms=400  max_utterance_ms=30000
slot_actions={1:"enter",2:"escape",3:"ctrl_c",4:"shift_tab",
              5:"up",6:"down",7:"noop",8:"noop"}  # 7,8 reserved
# from_dict backfills slots 5-8 for legacy 4-entry configs (no clobber of user keys).
target_apps=[]   # empty = any app; else bundle-id/name substrings
log_activity=False   enabled=True   start_at_login=False
mw_binary="/Applications/MacWhisper.app/Contents/MacOS/mw"
```

### 4.2 `audio.py` — capture

- `resolve_device(name, query_fn=None)` — finds the **first input device whose name
  contains `name`**. Resolve by **name, never a fixed index** — indices shift between
  sessions. Raises `DeviceNotFound`.
- `input_device_names(query_fn=None) -> list[str]` — returns names of all currently
  connected input devices. Used to populate the "Audio source" dropdown in Settings and
  onboarding.
- `reinitialize()` — PortAudio caches its device list at init, so hot-plug/unplug is
  invisible to `query_devices()` until re-init. Settings' **Refresh** calls
  `TinkAgentApp.rescan_devices()`, which stops capture, calls this, and restarts.
- `AudioCapture(device_name, sample_rate, block_size, on_block, stream_factory=None,
  resolve_fn=None)` — opens a `sounddevice.InputStream`; calls `on_block(block)` with a
  **1-D int16 numpy array** per block. `stream_factory`/`resolve_fn` are injected in
  tests so PortAudio is never opened. `start()`, `stop()`, `is_running`.

### 4.3 `detector.py` — the DSP core

`goertzel(samples, freq, sample_rate) -> power` — single-frequency power, O(n).

`ToneDetector(tones, rms_min, dominance_min, debounce_ms, sample_rate, tonality_min=0.5)`
- `process(block) -> slot|None`. Gate = `rms > rms_min` AND `dominance >= dominance_min`
  AND `tonality >= tonality_min`, where
  - `dominance = best_bin_power / sum(all 4 bin powers)`,
  - `tonality = best_bin_power / (block_energy * N/2)` (≈1.0 for a pure on-bin tone, ≈0
    for speech).
- Sets `tone_active` (bool) every block — read by `VoiceGate`.
- **Debounce** is transition-based: fires once per burst; a *real silence gap*
  (`rms < rms_min`) is what resets the press state — a tonality wobble mid-burst does
  **not** re-fire. (This subtlety was a real bug; keep it.)

`VoiceGate(rms_start, rms_end, hangover_ms, min_utterance_ms, sample_rate, block_size,
max_utterance_ms=30000)`
- `process(block, tone_active) -> utterance(np.int16)|None`. Energy VAD with hysteresis:
  rise above `rms_start` → open; below `rms_end` for `hangover_ms` → close & return PCM.
- Blocks with `tone_active=True` are **excluded** from the buffer (mutual exclusion).
- Buffer is **capped** at `max_utterance_ms` (force-flush) so a long hold can't grow
  memory unbounded or stall the `np.concatenate` in `_close()`.
- `active` property → utterance currently open (drives the capture indicator).

### 4.4 `transcribe.py` — STT

- `write_wav(samples, path, sample_rate)` — 16-bit mono WAV.
- `Transcriber(mw_binary, model="", runner=subprocess.run)`,
  `transcribe(samples, sample_rate) -> str`. Writes a temp WAV, runs
  `mw transcribe <wav> [--model …]`, returns the **last non-empty stdout line** (mw
  prints a `Transcribing …` status line first). Returns `""` and sets `last_error` on
  failure. `runner` injected in tests.

### 4.5 `actions.py` — output

`ActionRouter(slot_actions, keyboard=None)`
- `fire_slot(slot) -> action_id` — performs the mapped action; `"noop"`/`"unmapped"`
  do nothing.
- `type_text(text)` — types into the frontmost app.
- Supported actions live in `ACTION_CATALOG` (id/label/glyph — the single source of
  truth for both `_perform` and the Button Actions popup): keys/combos (`enter`,
  `escape`, `esc_esc`, `ctrl_c`, `ctrl_d`, `tab`, `shift_tab`, `shift_enter`, arrows,
  `space`, `backspace`, `cmd_v`, `key_1/2/3`), `type:<text>` macros (type the text then
  Enter), and `noop`. Unknown ids = safe no-op. Add new ones to the catalog + `_perform`.
- `keyboard` is a lazily-created `pynput` controller (so importing the module needs no
  Accessibility permission); tests inject a fake. Errors are caught into `last_error`
  (e.g. missing Accessibility) — never crash the audio path.

### 4.6 `engine.py` — the orchestrator

`Engine(config, detector, voicegate, transcriber, router, on_event=None,
submit_fn=None, frontmost_fn=None, logger=None)`. The heart is `handle_block` (see
§3 diagram). Helpers:
- `is_capturing` → `voicegate.active`.
- `_front()` → frontmost app identity ("name bundleid") via `frontmost_fn`
  (`_default_frontmost` uses `NSWorkspace`); injected in tests.
- `_target_ok(front)` → True if `config.target_apps` is empty or any entry is a
  substring of `front`.
- `on_event(kind, payload)` kinds: `"tone"`, `"action"`, `"transcript"`, `"error"`,
  `"blocked"`. The menu/settings consume these.

### 4.7 `menubar.py` — app shell & lifecycle

`TinkAgentApp(rumps.App)` owns everything. Menu is intentionally slim: status line,
**Enabled** toggle, **Settings…**, Quit (rumps adds Quit). Everything else is in the
Settings window.

- `_build_engine()` constructs the full chain + `ActivityLogger`.
- `_tick(self, _)` (rumps.Timer, 0.2 s, main thread): lazily starts audio on first tick
  (deferred so `run()` paints the icon before opening the mic — see §8), swaps the icon
  (`ICON_IDLE`/`ICON_ACTIVE`) by capture state, updates the status line, and refreshes
  the Settings window if open.
- **Shared setters** are the single place state changes (called by BOTH the menu and the
  settings window, so they stay in sync): `set_enabled`, `set_listening`,
  `set_start_at_login`, `toggle_target`, `set_log_activity`. Each applies + persists.
- Capture lifecycle: `start_listening`/`stop_listening` (own the `AudioCapture`).
- `main()` constructs the app, sets **accessory activation policy** (no Dock / no
  Cmd-Tab), then `run()`.

### 4.8 `settings_ui.py` — native settings

`SettingsController(NSObject)` builds the window via `theme.window` (`W,H = 440,504`):
two `theme.card` (`NSBox`) groups — **General** (`NSSwitch` rows) and **Input**
(Transcription / Audio source `NSPopUpButton`s + Refresh, Allowed-apps button) — plus
the accent **Set Up TINK** button and orange config/log links. Pattern:
- Controls are wired with plain Python callbacks (`theme` helpers route them through a
  retained `_Target`), not hand-written ObjC selectors. Every callback delegates to a
  `TinkAgentApp` setter — **no logic lives in the UI**.
- **Refresh** → `_refresh_click` shows a "Refreshing…" state, then `doRescan_` calls
  `app.rescan_devices()` (true device re-scan) and repopulates the popup.
- `show()` calls `refresh()` (sync control states + the "N apps…"/"Any app" caption +
  the Set-Up button's primary/secondary state from `onboarding_done`), then fronts the
  window. Windows are pinned to the light **Aqua** appearance so native controls stay
  readable on the cream theme in Dark Mode.
- The target-app picker lives in a **separate window** (`_build_picker()`, `PW,PH =
  380,460`), opened by the `openApps_` button and dismissed by **Done** (`closePicker_`,
  just `orderOut_`). It's a scrollable, multi-select checklist of **installed** apps
  (`_installed_apps()` scans `_APP_DIRS` — `/Applications`, `…/Utilities`,
  `/System/Applications`, `~/Applications` — top-level `.app`s only, bundle id via
  `NSBundle`). Each checkbox is tagged with its bundle id via `setIdentifier_`;
  `appToggled_` calls `app.toggle_target(bundle_id, on)` and refreshes the button count.
  A selected app that isn't installed locally still shows, labeled `(not installed)`.

pyobjc gotcha: custom init is `initWithApp_` using `objc.super(...).init()` — **not**
`NSObject.init(self)` (that raises `TypeError: Need 0 arguments, got 1`).

### 4.9 `launchagent.py` — auto-start (see §8 for why)

Functions to manage `~/Library/LaunchAgents/io.github.tajchert.tinkagent.plist`:
- `set_run_at_login(enabled, python, repo, …)` — writes/removes the plist **only**
  (governs the next login; does not start/stop the running instance).
- `install_and_start(...)` — writes plist + `launchctl bootstrap gui/$UID` (starts now).
- `uninstall(...)` — `bootout` + remove plist.
- `is_enabled()` — plist file present. `runner` injected in tests.

---

## 5. Config & data flow reference

- **User config**: `~/.tink-agent/config.json` (the `Config` dataclass).
- **Device config** (separate!): `ting-config/config.json` + `ting-config/samples/*.wav`
  are copied onto the mic's `TINGDISK` drive. These define the **button tone samples**
  and the fixed-pitch SAMPLE preset. Regenerate tones with `assets/make_icon.py`? No —
  tones are generated ad-hoc with ffmpeg (see git history / `TING.md`); the icons are in
  `assets/make_icon.py`.
- **Activity log**: `~/Library/Logs/TinkAgent-activity.log` (TSV, opt-in).
- **App run log**: `~/Library/Logs/TinkAgent.log` (LaunchAgent stdout/stderr).

---

## 6. Threading model (read before touching engine/UI)

Three contexts:
1. **PortAudio callback thread** — runs `AudioCapture._callback` → `Engine.handle_block`
   → tone detection + voice gating + keystrokes. Must be fast. No `mw`, no AppKit.
2. **Transcription worker** (`ThreadPoolExecutor`, 1 worker) — runs `mw` + typing.
   Serial, so transcripts can't interleave.
3. **Main thread** — rumps run loop + `rumps.Timer` + all AppKit/UI mutation +
   menu/settings callbacks.

Rule: background threads **stash** state into plain attributes (atomic writes); the
main-thread timer renders. Never call rumps/AppKit off the main thread.

---

## 7. Dev workflow

```bash
# setup
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# run (development — shows the icon, attached to your terminal's permissions)
.venv/bin/python -m tink_agent

# tests (all logic is offline-testable; no hardware needed)
.venv/bin/pytest -q
```

After changing code while installed as a LaunchAgent, reload it:
```bash
UID_NUM=$(id -u); P="$HOME/Library/LaunchAgents/io.github.tajchert.tinkagent.plist"
launchctl bootout "gui/$UID_NUM" "$P"; launchctl bootstrap "gui/$UID_NUM" "$P"
```
The LaunchAgent runs `python -m tink_agent` from the repo in place, so a reload picks up
source changes (no rebuild).

### Testing conventions (important)

Every effECTful dependency is **injected** so tests run with no hardware/permissions:
- audio: `stream_factory`, `resolve_fn`, `query_fn`
- transcription: `runner` (fake subprocess)
- keystrokes: `keyboard` (fake controller)
- frontmost app: `frontmost_fn`
- threading: `submit_fn=lambda fn: fn()` (synchronous)
- time/launchctl: `now_fn`, `runner`

Real recordings live in `tests/fixtures/` (`tones.wav`, `speech.wav`) and back the
**regression tests that matter most**: speech must fire zero slots; the four tones must
detect in order. If you touch `detector.py`, these are your safety net.

Follow this DI pattern for anything new that touches the OS.

---

## 8. macOS packaging — why a LaunchAgent, not a `.app`

A menu-bar app must join the GUI (Aqua) session to draw its `NSStatusItem`. A plain
`.app` whose launcher script `exec`s the framework Python **does not join the GUI
session**, so its icon never appears (we verified: a minimal rumps app failed the same
way from a bundle but worked from a terminal / via launchd). So we ship a **LaunchAgent**
— launchd runs `python -m tink_agent` in the GUI session.

- Install/auto-start: `packaging/install.sh` (writes plist + bootstraps). Remove:
  `packaging/uninstall.sh`.
- In-app **"Start at login"** toggles the plist file via `launchagent.set_run_at_login`.
- `main()` sets `NSApplicationActivationPolicyAccessory` so there's no Dock icon and no
  Cmd-Tab entry.
- Permissions attach to **"Python"** (the framework binary), not a dedicated app
  identity. Grant Microphone + Accessibility to Python. A self-contained py2app bundle
  (own identity) is a known future option but not done — bundling PortAudio on 3.14 is
  fiddly.

Deferred-audio-start detail: opening the mic in `__init__` could block before `run()`
ever drew the icon, so audio start is deferred to the first `_tick`.

---

## 9. How to extend (common tasks)

- **Add a button action**: add a case in `ActionRouter._perform`; set it in
  `config.slot_actions`. Add a test in `tests/test_actions.py`.
- **Add a config field**: add to `Config` (with a sane default); handle int-keyed maps
  in `to_dict`/`from_dict`; add a migration there if renaming. Surface it in
  `settings_ui.py` + a shared setter in `menubar.py`. Test round-trip in
  `tests/test_config.py`.
- **Add a Settings control**: add the control in `SettingsController._build`, a
  `fooToggled_` selector delegating to an app setter, and sync it in `refresh()`.
- **Change detection thresholds**: they're config fields; tune in
  `~/.tink-agent/config.json`. If you change the *algorithm*, re-run the
  `tests/fixtures` regression tests and re-validate on hardware.
- **New cross-thread state for the UI**: stash in an attribute from the worker/audio
  thread; render it in `_tick`. Never touch AppKit off-main.

---

## 10. Gotchas / landmines

- **Device pitch modulation** (the big one): without a fixed-pitch SAMPLE preset in the
  *device* `config.json`, holding the handle pitches button tones down into the speech
  band → undetectable + leak into transcripts. The shipped `ting-config/config.json`
  fixes it. See `TING.md`.
- **Audio device index is not stable** — always resolve by name.
- **`mw` prints a status line** before the transcript — take the last non-empty line.
- **pyobjc init** — use `objc.super(Cls, self).init()`.
- **Don't run `mw` or AppKit on the audio thread.**
- **The handle is the only PTT** — there's no "listening only while pressed" we can
  implement, because the press is invisible until we hear the audio it lets through.
- **Two safety gates** exist (`enabled` + target-app guard); when debugging "nothing
  happens", check both, plus that the frontmost app matches `target_apps`.
- **Permissions**: no keystrokes → Accessibility not granted to Python; no audio →
  Microphone not granted, or device not connected/handle not held.

---

## 11. Glossary

- **PTT** — push-to-talk; here, the mic's physical handle (hardware-gated, no signal to
  the host).
- **Slot** — a (mode, sample) pair mapped to a tone frequency and a keystroke action.
  Green selects which of the 4 samples; white plays it; **orange selects the mode**: pos 0
  = mode A (slots 1–4, base pitch), pos 1 = mode B (slots 5–8, pitch +10.5 → higher
  frequencies). 8 detectable tones total. The app is stateless — each tone's frequency
  encodes both mode and sample, so it never tracks orange. Mode/slot are shown on the
  mic's 4 mode + 4 slot LEDs (mode A = no mode LED lit). See the orange-mode design spec.
- **Goertzel** — efficient single-frequency power estimator used for tone detection.
- **Dominance / tonality** — the two tone-detection gates (relative bin power; absolute
  pure-tone-ness). See §4.3.
- **VAD** — voice activity detection (the energy gate in `VoiceGate`).
- **TINGDISK** — the mic's USB mass-storage volume holding its `config.json` + samples.
