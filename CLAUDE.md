# CLAUDE.md — tink-agent

Guidance for Claude Code working in this repo. Read this first, then the docs it points to.

## What this is

A macOS menu-bar app that turns a Teenage Engineering EP-2350 "Ting" mic into a
voice + button controller for AI coding agents. **One audio input stream** is fanned to
two consumers: voice (→ transcription → typed text) and button tones (→ synthesized
keystrokes). The mic has **no data link** — the only signal in is audio.

## Read these before changing things

- **`AGENTS.md`** — full developer guide: architecture, modules, threading model, how the
  pipeline fits together. Read top-to-bottom once.
- **`TING.md`** — the hardware: device `config.json` schema, tone samples, and the
  critical handle-pitch-modulation gotcha. Read before touching anything audio/device.
- **`README.md`** — user-facing install/run.

## Setup & running

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m tink_agent          # dev run (menu-bar icon appears)
packaging/install.sh                     # install as a LaunchAgent (auto-start)
```

User config lives at `~/.tink-agent/config.json`. macOS **Microphone** + **Accessibility**
permissions are required (grant to the Python binary; see AGENTS.md if keystrokes don't fire).

## Testing

- Run tests with `.venv/bin/pytest -q`. Most OS-touching deps are injected, so tests run
  without the Ting, mic/Accessibility permissions, or an STT tool.
- **Do not run the suite in a way that spawns heavy parallel workers on a constrained
  machine** — prefer `tsc`-style quick checks / targeted files, or ask before a full run.
- Keep the audio callback path fast; transcription and keystroke synthesis run off-thread
  (see the threading notes in AGENTS.md).

## Speech-to-text backends

`stt_backend` in config selects the transcriber:
- `macwhisper` / `whisper-cpp` / `openai-whisper` — local CLI tools.
- `aqua-api` — Aqua Voice "Avalon" cloud API (needs `AQUA_API_KEY` env; paid per audio-second).
- `custom` — any CLI that takes a WAV and prints text.

There is also a **local, free** route that drives the Aqua Voice *desktop app* via a
push-to-talk hotkey instead of the API — see the **`tink-aqua-local-setup`** skill in
`.claude/skills/` (run `/tink-aqua-local-setup` in Claude Code) for the step-by-step.

## Conventions

- Match the surrounding code's style, comment density, and idioms.
- OS-touching effects are injected (`*_fn` params) so logic stays unit-testable — keep that
  pattern when adding features.
- Don't commit or push unless asked. Branch off `main` for anything non-trivial.
