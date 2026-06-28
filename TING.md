# TING.md — Teenage Engineering EP-2350 "Ting"

Reference doc for the EP-2350 Ting mic as a **voice + button input device for AI agent harnesses** (Claude Code, Codex).
Authoritative source: the on-device `readme.pdf` (TINGDISK), cross-checked with TE web docs. Last verified: 2026-06-27.

---

## TL;DR — what matters for our project

1. **The mic is NOT a USB audio interface.** Its USB-C port only does **power + file management** (mounts as a disk; on this Mac it appears as `/Volumes/TINGDISK`). Audio does **not** travel over USB.
2. **Audio reaches the Mac via the analog line-out → Ugreen USB adapter.** On this machine that adapter is the C-Media **`USB Audio Device`** (1 input ch, 48 kHz). In `ffmpeg -f avfoundation` it is device index **`[5] USB Audio Device`** (verify index each session — it can shift).
3. **The buttons send NO data to the computer.** Orange/green/white buttons + the handle are *purely on-device* — no HID, MIDI, or keyboard. There is no data channel for button state.
   - ⇒ "press a button to approve (send Enter)" **cannot be wired directly.** It must be **inferred from the audio stream**: assign a button a distinct tone via `config.json` sample, detect that cue in the capture, synthesize the keystroke. See "Phase 2 implications".
4. **The mic is only live while the handle is pushed.** Pushing the handle powers on AND enables the microphone (walkie-talkie PTT behavior). Releasing → (battery) power-save after 5 min, off after 20 min; on USB it stays powered.
5. **Customization = drop `config.json` + `1.wav`..`4.wav` onto TINGDISK, then RESTART the unit.** Changes are NOT picked up live — you must power-cycle (button above USB-C off, push handle on).

---

## Hardware overview

| Spec | Value |
|---|---|
| Form factor | Handheld mic, walkie-talkie style |
| Dimensions / weight | 88 × 56 × 16 mm, 100 g |
| MCU | **RP2350** (runs MicroPython internally; UF2 bootloader) |
| Audio out | **Stereo line output**, 2 VRMS / 8 dBu — designed for RIDDIM or a mixer, **NOT headphones** |
| Volume | Round **green trim pot under the lower lid** |
| SNR | 98 dBA |
| Power | 2× AAA **or** USB-C (5 V ≥ 1 A). USB power overrides batteries; batteries are NOT charged |
| Power save (battery) | Power-save 5 min after handle release; off after 20 min; low-batt = blinking LED |
| Power (USB) | Stays on until cable pulled |
| Storage | ~1 MB user space on TINGDISK |

### Controls
- **Handle (squeeze / "PTT")** — push to power on **and to enable the mic**. Handle **position (0–100%) modulates an effect parameter** (which one is preset-defined). Continuous control, not a clean digital button.
- **Orange button** — selects voice/effect preset position: **`[ clean, echo, echo+spring, pixie, robot ]`** (clean + 4 effect presets). **4 mode LEDs** show the position; position 0 (clean) = **no mode LED lit**.
- **Green button** — selects sample slot: factory **`[ siren, alarm, gunshot, monkey boy ]`** (4 slots; replaceable). **4 slot LEDs** show the selection.
- **White button** — plays the selected sample.
- **Shake (accelerometer)** — temporarily modifies the effect; behavior is preset-dependent.

> **Our app repurposes orange as a mode switch.** `ting-config/config.json` ships two
> `SAMPLE`-only presets: pos 0 (pitch 0.0) = **mode A**, pos 1 (pitch +10.5) = **mode B**
> (same 4 tone samples played ~×1.84 higher). Combined with green's 4 slots, that's 8
> detectable tones → 8 actions. **Mode A = no mode LED; mode B = first mode LED lit.**
> Validated on hardware 2026-06-27: all 8 tones clean and on-nominal (≤ +9 Hz),
> top ~7153 Hz survives the resampler. See the orange-mode design spec.

> All of the above only affect the **audio at the line-out**. None are exposed to the host as input events.

---

## Connectivity model (important)

```
                 ┌─────────────────────────────┐
   USB-C ───────▶│ Power (5V/1A) + TINGDISK     │   files only — NO audio, NO button data
                 │ mass storage when powered on │
   EP-2350 Ting  └─────────────────────────────┘
        │
        │ stereo line-out (analog, post-effects, 2 VRMS)
        ▼
   ┌──────────────────┐   USB    ┌──────────────┐
   │ Ugreen USB audio │ ───────▶ │ macOS input  │  "USB Audio Device" (C-Media)
   │ adapter (C-Media)│          │ avfoundation │   1 in ch, 48 kHz, ffmpeg idx [5]
   └──────────────────┘          └──────────────┘
```

- **Edit config/samples:** USB-C + power on → `/Volumes/TINGDISK` mounts. Then **restart unit** to apply.
- **Capture voice:** read the `USB Audio Device` input (the Ugreen). Mic only passes audio while handle is pushed.
- Both cables can be connected at once (USB-C for power/files, line-out→Ugreen for audio).

### Verified on this machine (2026-06-27)
- `/Volumes/TINGDISK` mounts when powered on. Default contents: `1_.wav` (factory sample), `readme.pdf`, `System Volume Information/`. **No `config.json` by default — you create it.**
- Factory `1_.wav`: PCM s16le, **16 kHz, stereo, 16-bit, 6.41 s, 410 KB**.
- `USB Audio Device` = C-Media, 1 in ch, 48 kHz; ffmpeg avfoundation `[5]`.

---

## `config.json` — authoritative schema (from on-device readme)

Create `config.json` at TINGDISK root. It **overrides presets and selects which samples play**. Strict JSON (parsing errors will fail to load). Uninitialized parameters use defaults.

**Recovery:** if a config is so extreme the unit won't start, **hold green + white while powering on**, then fix the file.
**Apply changes:** samples/config are read only at boot — power off (button above USB-C) and push handle to restart.

### Official example
```jsonc
{
  "name": "We count from zero",
  "samples": [
    { "pos": 1, "file": "samples/whistle1.wav", "playmode": "oneshot" },
    { "pos": 0, "file": "live1/loop.wav",        "playmode": "startstop" },
    { "file": "horn.wav",                         "playmode": "hold" },
    { "file": "live1/shottis.wav",                "playmode": "oneshot" }
  ],
  "presets": [
    {
      "pos": 0,
      "list": [
        { "effect": "HARMONY", "pitch": 2.0, "BUS": 2 },
        { "effect": "REVERB",  "time": 0.1, "dry-level": 1.0 },
        { "effect": "DELAY",   "time": 0.5, "dry-level": 0.0, "echo": 0.5, "BUS": 1 },
        { "effect": "SAMPLE",  "speed": 1.0 }
      ],
      "handle":  { "row": 1, "param": "time", "depth": 0.6 },
      "shake":   { "row": 2, "param": "echo", "depth": 1.0 },
      "lfo":     { "row": 3, "param": "echo", "depth": 1.0, "mpy": 1.0, "shape": "random", "phase": 0, "speed": 4.0 },
      "trigger": { "row": 3 }
    },
    {
      "pos": 2,
      "list": [
        { "effect": "HARMONY", "pitch": 2.0 },
        { "effect": "SAMPLE",  "speed": 2.0 },
        { "effect": "REVERB",  "time": 1.0, "spring": 0.5 },
        { "effect": "DELAY",   "time": 0.1, "echo": 0.5 }
      ],
      "handle":  { "row": 2, "param": "pitch", "depth": -0.2 },
      "trigger": { "row": 1 }
    }
  ]
}
```
> (The readme's `lfo` line has a typo — `"speed", 4.0` should be `"speed": 4.0`. Use a colon.)

### Field reference
- **`name`** — pack name (string).
- **`samples[]`** — `pos` (0-indexed slot, optional → defaults to array order), `file` (path on TINGDISK, subdirs OK e.g. `samples/`, `live1/`), `playmode`: `"oneshot"` | `"hold"` | `"startstop"`.
- **`presets[]`** — one per orange-button slot:
  - `pos` — slot index (which orange position this preset occupies).
  - `list[]` — effect chain in order. Each: `{ "effect": <TYPE>, <params…>, "BUS": 1|2 }`. `BUS` is optional routing. **Use `DELAY`, `REVERB`, `HARMONY`, `SSB` at most once per chain.**
  - `handle` / `shake` / `lfo` — modulation: `row` (0-indexed effect in `list`), `param` (param name on that effect), `depth`. `lfo` adds `mpy`, `shape`, `phase`, `speed`.
  - `trigger` — `{ "row": N }` = which effect row responds to sample playback.

### Effects & parameter ranges (10 effects)
| Effect | Parameters (range) |
|---|---|
| **BALANCE** | balance [0.0, 1.0] |
| **DELAY** | time [0.0, 1.2], lowpass-cutoff [0,1], highpass-cutoff [0,1], wet-level [0,1], dry-level [0,1], echo [0,1], cross-feed [0,1], balance [0,1] |
| **DIST** | amount [0.0, 40.0], highpass-cutoff [0,1], lowpass-cutoff [0,1], mix [0,1] |
| **HARMONY** | dry-level [0,1], pitch [0.50, 2.0] |
| **HIGHPASS** | cutoff [0.0, 1.0] |
| **LOWPASS** | cutoff [0.0, 1.0] |
| **SAMPLE** | speed [0.0, 4.0], pitch [-24.0, 24.0], level [0,1], balance [0,1] |
| **REVERB** | dry-level [0,1], wet-level [0,1], time [0,1], spring-mix [0,1], highpass-cutoff [0,1] |
| **RING** | frequency [0.0, 20000.0], mix [0,1] |
| **SSB** | frequency [-20000.0, 20000.0] |

**LFO shapes:** `sine`, `square`, `sawtooth`, `random`.

> The voice modes `echo / echo+spring / pixie / robot` are *presets built from these primitives* (e.g. echo = DELAY; spring = REVERB spring-mix; pixie/robot = HARMONY/RING), not separate effect types.

---

## Samples / WAV requirements
- Override factory samples by placing **`1.wav`, `2.wav`, `3.wav`, `4.wav`** on TINGDISK (or reference any path via `config.json` `file`).
- WAV only, mono or stereo, 8/16/24-bit or 32-bit float, up to 96 kHz.
- **Total ~1 MB** across all samples — keep them short.
- Not active until **restart** (power off via button above USB-C, push handle to start).
- (Factory file is named `1_.wav` with an underscore; your overrides use `1.wav` without.)

---

## Firmware
- Files: `ep2350_firmware_X_X_X.uf2`. Latest: **1.0.8** (2025-12-05) · 1.0.7 (JSON parsing/regression fixes) · 1.0.5.
- Update mode: remove lower lid, attach USB-C, **hold the handle and double-click the small button above the USB port**. A disk **`TING BOOT`** appears (contains `INDEX.HTM`, `INFO_UF2.TXT`). Drag the `.uf2` on; **don't release the handle until it restarts**.
- Download: https://teenage.engineering/downloads/ep-2350
- ⚠️ JSON loading changed across 1.0.5→1.0.7 — confirm firmware before relying on config behavior.

---

## Phase 2 implications (voice → agent, buttons → actions)

**Voice input (✅ verified end-to-end 2026-06-27):**
- Capture from `USB Audio Device`; feed to transcription. `ffmpeg` v8.1.1 installed.
- **MacWhisper CLI = `mw`** at `/Applications/MacWhisper.app/Contents/MacOS/mw` (the docs' `macwhisper` name isn't on PATH; `mw` is the real binary). Subcommands: `version`, `models`, `transcribe <file> [--model engine:id] [--persist] [--stream]`. Installed models: `whisperkit:openai_whisper-large-v3-v20240930` (Large v3 Turbo, default) + `whisperkit:openai_whisper-base`.
- Verified: held handle, spoke Polish 6 s → `mw transcribe` returned exact text in ~3.7 s, language auto-detected. Levels were healthy (mean −27.4 dB, max −7.8 dB).
- Capture example: `ffmpeg -f avfoundation -i ":5" -ac 1 -ar 16000 out.wav` (`:5` = device index; re-verify each session).
- Natural PTT flow: **push handle to talk** (mic only live while held) → capture → transcribe → send as prompt. Handle release is a natural end-of-utterance boundary.

**Buttons → keystrokes (the hard part — must go through audio):**
- No data path. Make buttons produce **uniquely detectable audio cues**, detect them in the capture stream, synthesize keystrokes (`osascript` / `cliclick` / accessibility helper).
- Plan: replace `1.wav`..`4.wav` with **short distinct tones** (e.g. different single frequencies / DTMF-like). **Green** selects which → **white** plays → 4 mappable "buttons" (approve / reject / interrupt / submit). Map detected tone → `Enter` etc.
- **Orange** changes the live effect on your voice — usable as a "mode" signal but harder to detect than a clean tone; prefer sample tones for discrete actions.
- Detection: Goertzel / FFT tone detection on the live stream (low latency, robust if cues are pure tones short bursts). Keep cue tones out of normal speech band where practical.
- Trade-off to validate: tone cues will also be audible in the mixed line-out alongside voice — ensure transcription ignores them (filter band) and detection doesn't false-trigger on speech.

**⚠️ Critical gotcha — sample playback is modulated by the handle (fixed via config preset):**
- With only `samples` defined (no `presets`), the **factory preset modulates the SAMPLE pitch by handle position**. Holding the handle to talk pitches the cue tones *down and smears* them (measured: 1500 Hz → ~539 Hz, ~45% purity), so they fall into the speech band, fail tone detection, and leak into the transcript as garbage. Voice itself stays clean — only sample playback is affected.
- **Fix:** define an explicit preset that plays samples at fixed pitch with no modulation, and keep orange on it:
  ```json
  "presets": [
    { "pos": 0, "list": [ { "effect": "SAMPLE", "speed": 1.0, "pitch": 0.0, "level": 1.0 } ], "trigger": { "row": 0 } }
  ]
  ```
  No `handle`/`shake`/`lfo` keys ⇒ no modulation. Verified: cue tones then play clean (1500 Hz / 100% purity) regardless of handle position; detector fires, zero voice leak. This is what `ting-config/config.json` ships.
- Sample playback also requires the device awake/handle engaged — handle fully released gave silence.

**Detector robustness — tonality gate (added after live testing):**
- Dominance measured only among the 4 tone bins is **not enough**: broadband speech peaking near 1500 Hz fired slot 1 (false Enter). Added a **tonality gate** — the winning bin's power must be a large share of the block's *total* energy (≈1.0 for a pure tone, ≈0 for speech). Real speech now scores ~0.00 vs tones ~0.99. Only real silence resets the per-press state so a tonality wobble mid-burst doesn't re-fire. See `tone_tonality_min` (default 0.5) in `~/.tink-agent/config.json`.

**Tests to run with the user:**
1. ✅ TINGDISK mounts; default contents + factory wav probed.
2. ✅ Audio path + transcription verified (handle-held speech → ffmpeg `[5]` → `mw transcribe` → exact text, ~3.7 s).
3. ✅ Custom tone cues work. Wrote `config.json` + four tone samples (`ting-config/` in repo), restarted unit, recorded a green→white pass. **All 4 detected at 100% single-frequency dominance**, rms ≈ 1600–1935 vs background rms ≈ 560 / ~58% dominance. Detection rule: **burst = rms > 1000 AND dominance > 90%**. Bursts ~0.45 s.
   - Slot 1 = 1500 Hz, slot 2 = 2300 Hz, slot 3 = 3100 Hz, slot 4 = 3900 Hz.
   - Cue assets: `ting-config/config.json`, `ting-config/samples/{1,2,3,4}.wav`. Detection prototype: Goertzel over 50 ms windows on the 16 kHz capture.
4. Next: build the live runtime — continuous capture, handle-gated voice→`mw transcribe`→prompt, plus real-time tone detection → keystrokes (`osascript`/`cliclick`).

---

## Sources
- **On-device `readme.pdf`** (TINGDISK) — authoritative for config schema, effect ranges, controls, recovery.
- [EP-2350 ting guide](https://teenage.engineering/guides/ep-2350) · [downloads/firmware](https://teenage.engineering/downloads/ep-2350) · [sound packs](https://teenage.engineering/downloads/ep-2350/sound-packs)
- [OP Forums: config.json discussion](https://op-forums.com/t/ep-2350-ting-customizable-samples-and-effects-via-config-json/30479)
- [Unofficial Ting Preset Editor](https://labs-te-ting-preset.vercel.app/)
- [MacWhisper CLI docs](https://macwhisper.helpscoutdocs.com/article/57-macwhisper-command-line-tool)
