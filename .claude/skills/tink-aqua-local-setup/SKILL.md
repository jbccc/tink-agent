---
name: tink-aqua-local-setup
description: Set up tink-agent to drive the Aqua Voice desktop app for LOCAL (free, no-API) speech-to-text using the Ting mic. Use when a user wants Ting voice input to dictate through Aqua Voice instead of paying per-audio for the Aqua/Avalon API, or asks to "wire the Ting to Aqua", "set up local dictation", "avoid the API cost", or "share the Aqua setup". Covers the Aggregate Device audio split, tink-agent's dictation_hotkey mode, and the F12 push-to-talk trigger.
---

# Ting → Aqua Voice: local (free) dictation setup

This wires the Teenage Engineering Ting mic to dictate through the **Aqua Voice desktop
app** locally, so you don't pay the Aqua/Avalon **API** per second of audio. tink-agent
detects when you're speaking and *presses Aqua's push-to-talk hotkey for you*; Aqua does
the transcription on-device and types into your focused app. The Ting's buttons still fire
keystrokes (Enter/Escape/Ctrl-C/…) as usual.

## Why it's built this way (read first)

- The Ting sends **no button/handle data** — only analog audio reaches the Mac, through a
  USB audio adapter that appears as **`USB Audio Device`**.
- That USB adapter is **exclusive**: only one app can read it at a time. But both
  tink-agent (needs it for voice-gating + button tones) **and** Aqua (needs it to dictate)
  want it.
- The fix: wrap the USB device in a macOS **Aggregate Device**. An aggregate is a virtual,
  **multi-client** device — several apps can read it at once. Point *both* apps at it.
- tink-agent can't hand audio to Aqua directly, and Aqua has no file/CLI API for the
  desktop app. So tink-agent instead **synthesizes Aqua's push-to-talk hotkey** (F12):
  presses it when your voice starts, releases it when you pause.

```
Ting → USB adapter ──> Aggregate Device (multi-client) ──┬─> tink-agent: voice gate → holds F12; also button tones
                                                         └─> Aqua Voice: dictates while F12 held → types
```

## Prerequisites

- tink-agent installed and its base setup done (venv, `~/.tink-agent/config.json`,
  LaunchAgent running, **Microphone + Accessibility permissions granted to Python**). If
  not, do that first — this skill assumes the mic already captures the Ting.
- The **Aqua Voice desktop app** installed (`/Applications/Aqua Voice.app`) and signed in.
  (This uses the app's local transcription, NOT the Avalon API — so no API key needed.)
- The Ting on battery, line-out → USB audio adapter → Mac, powered on.

## Step 1 — Create the Aggregate Device

1. Open **Audio MIDI Setup** (`open -a "Audio MIDI Setup"`).
2. Bottom-left **`+`** → **Create Aggregate Device**.
3. In the right panel, **check only `USB Audio Device`**.
   - **Do NOT add BlackHole or any virtual device** — mixing a hardware device with a
     virtual one causes clock drift and the input goes silent or garbage. One hardware
     device in the aggregate is all you need to make it multi-client.
4. Set **Clock Source** = `USB Audio Device`.
5. (Optional) rename it, e.g. `Ting Aggregate`. Note the exact name — you'll point both
   apps at it.

Verify it exists with 1 input channel:
```bash
.venv/bin/python -c "import sounddevice as sd; sd._terminate(); sd._initialize(); [print(d['name'], 'in=', d['max_input_channels']) for d in sd.query_devices() if 'aggregate' in d['name'].lower()]"
```

## Step 2 — Point tink-agent at the aggregate + dictation mode

Set these in `~/.tink-agent/config.json` (or via the helper below). The Ting is on
**channel 0** of a USB-only aggregate; capture opens at the aggregate's native **48000 Hz**
and decimates to 16 kHz internally.

```bash
.venv/bin/python - <<'PY'
from tink_agent.config import Config
c = Config.load()
c.device_name      = "Aggregate Device"   # <- exact aggregate name from Step 1
c.output_mode      = "dictation_hotkey"    # press a key on voice instead of transcribing
c.dictation_hotkey = "f12"                 # must match Aqua's activate hotkey (Step 3)
c.capture_rate     = 48000                 # aggregate native rate
c.capture_channels = 1                     # USB-only aggregate = 1 input channel
c.input_channel    = 0                     # Ting is on channel 0
c.forward_audio_to = ""                    # not used
c.vad_hangover_ms  = 3000                  # pause tolerance: silence this long ends the
                                           # utterance & releases F12. Higher = won't cut
                                           # you off mid-sentence but Aqua types later.
c.save()
print("tink-agent configured for local Aqua dictation")
PY
```

Restart tink-agent so it reloads the config (and re-scans audio devices):
```bash
tinkctl restart          # if the tinkctl helper is installed (see below)
# or, without it:
launchctl kickstart -k gui/$(id -u)/io.github.tajchert.tinkagent
```

> **`tinkctl`** (`~/.local/bin/tinkctl`) wraps start/stop/restart/status/log and always
> re-enumerates audio devices — the fix for "no audio after the USB adapter dropped out of
> the Aggregate Device." A companion `tink-device-watch` LaunchAgent auto-restarts the app
> whenever the audio-device set changes, so a Ting replug self-heals. Both are machine-local
> (not in this repo); see the app's operational notes if they're missing.

## Step 3 — Point Aqua at the aggregate + set F12 push-to-talk

Do this in **Aqua's own Settings UI** — Aqua rewrites its hotkeys on launch, so editing its
`settings.json` from outside does NOT stick.

1. Open Aqua's **Settings / Preferences**.
2. Set the **microphone / input** to the **Aggregate Device** (same one).
3. Set the **push-to-talk / activate** shortcut to **`F12`** (hold-to-talk style).
   - `F12` is used because it's not a key you'll press by accident and tink-agent can
     synthesize it cleanly. Any function key you don't otherwise use works — just make
     tink-agent's `dictation_hotkey` match it exactly (pynput key name, lowercase, e.g.
     `f12`, `f13`, `f15`).
4. Make sure Aqua is set to **launch at login** and **keep running** — if Aqua isn't
   running, tink-agent presses F12 but nothing dictates.

## Step 4 — Verify end to end

Confirm tink-agent presses the hotkey when you speak (talk into the Ting during this):
```bash
.venv/bin/python - <<'PY'
from pynput import keyboard; import time
KEY = keyboard.Key.f12
print(">>> TALK INTO THE TING for 12s <<<")
ev=[]
def p(k):
    if k==KEY: ev.append("PRESS"); print("  F12 PRESS  (voice → Aqua dictating)")
def r(k):
    if k==KEY: ev.append("RELEASE"); print("  F12 RELEASE (pause → Aqua types)")
l=keyboard.Listener(on_press=p,on_release=r); l.start(); time.sleep(12); l.stop()
print("OK" if ev else "NO F12 — tink-agent not capturing the aggregate; check Step 2")
PY
```

Then the real test: click into a text field, grip the Ting, speak, pause — **Aqua should
type your words**. Tap the Ting buttons — they should still fire Enter/Escape/etc.

## Troubleshooting

- **No F12 fires while talking** → tink-agent isn't hearing the aggregate. Re-check the
  `device_name` matches the aggregate exactly, and restart tink-agent. Confirm the
  aggregate actually carries the Ting: run a live RMS meter on it **while speaking** (audio
  tests read silence if no one is talking — a very common false alarm).
- **F12 fires but Aqua doesn't type** → Aqua isn't running, its mic isn't the aggregate, or
  its activate hotkey isn't F12. Fix in Aqua's Settings UI.
- **Aggregate reads silence / a pinned huge constant level** → BlackHole or another virtual
  device got added to the aggregate. Remove it — aggregate should contain ONLY the USB
  device.
- **Everything silent after reboot / replug** → the aggregate persists, but the USB
  adapter can drop out of it when its device ID shifts. Reattach it in Audio MIDI Setup and
  restart tink-agent (`tinkctl restart`, or `launchctl kickstart -k
  gui/$(id -u)/io.github.tajchert.tinkagent`). The `tink-device-watch` agent, if installed,
  does this restart automatically on any device-set change. Make sure the Ting is powered
  on with the adapter connected and the handle engaged.
- **A button press triggers dictation (F12) instead of firing its action** → should not
  happen: a detected tone can't open the voice gate. If it does, the tone isn't being
  detected as a tone (check purity/levels while pressing the button — see the handle/pitch
  gotcha in `TING.md`), so it leaks into the voice path.

## Switching back to the paid API (if ever needed)

The API path is simpler (no aggregate, no Aqua app) but costs ~$0.39/hour of audio. To use
it: set `device_name="USB Audio Device"`, `output_mode="type"`, `stt_backend="aqua-api"`,
and export `AQUA_API_KEY` in the LaunchAgent's environment
(`launchctl setenv AQUA_API_KEY "<key>"`).
