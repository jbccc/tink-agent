from __future__ import annotations
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path

DEFAULT_PATH = Path.home() / ".tink-agent" / "config.json"
MW_BINARY = "/Applications/MacWhisper.app/Contents/MacOS/mw"


@dataclass
class Config:
    device_name: str = "USB Audio Device"
    sample_rate: int = 16000
    block_size: int = 800  # 50 ms at 16 kHz
    # Many USB ADCs run natively at 48 kHz; forcing the stream open at 16 kHz
    # makes CoreAudio resample in real time, which on cheap adapters mangles the
    # audio (bursty delivery, chopped speech). Instead open the device at
    # capture_rate and decimate to sample_rate in software. capture_rate=0 keeps
    # the simple single-rate path (open directly at sample_rate).
    capture_rate: int = 0          # 0 = same as sample_rate (no resample)
    capture_channels: int = 1      # channels to open on the device
    input_channel: int = 0         # which captured channel is the mic
    tones: dict = field(default_factory=lambda: {
        1: 1500, 2: 2300, 3: 3100, 4: 3900,      # mode A (orange pos 0)
        5: 2751, 6: 4218, 7: 5685, 8: 7153,      # mode B (orange pos 1, pitch +10.5)
    })
    tone_rms_min: float = 1000
    tone_dominance_min: float = 0.9
    tone_tonality_min: float = 0.5
    tone_debounce_ms: int = 300
    vad_rms_start: float = 800
    vad_rms_end: float = 500
    vad_hangover_ms: int = 800
    min_utterance_ms: int = 400
    max_utterance_ms: int = 30000
    stt_model: str = ""  # "" = mw's currently selected model (Large v3 Turbo)
    mw_binary: str = MW_BINARY
    # Transcription backend. "macwhisper" | "whisper-cpp" | "openai-whisper" use
    # built-in command templates; "custom" uses stt_command/stt_output below.
    stt_backend: str = "macwhisper"
    stt_command: list = field(default_factory=list)  # custom: tokens with {file}
    stt_output: str = "last_line"  # custom: last_line | all | file | dir
    # Aqua Voice API (backend "aqua-api"): OpenAI-Whisper-compatible endpoint.
    # The API key is read from the AQUA_API_KEY environment variable, never stored.
    aqua_api_url: str = "https://api.aquavoice.com/api/v1/audio/transcriptions"
    aqua_model: str = "avalon-v1.5"
    slot_actions: dict = field(default_factory=lambda: {
        1: "enter", 2: "escape", 3: "ctrl_c", 4: "shift_tab",   # mode A
        5: "up", 6: "down", 7: "noop", 8: "noop",               # mode B (7,8 reserved)
    })
    # Push-to-talk: the Ting button (slot number) that arms one dictation
    # utterance. When set, speech is ONLY transcribed after this button is
    # pressed — ambient conversation is ignored. None = always-on voice activation
    # (the button just... doesn't exist and every voice opens the gate).
    ptt_slot: int | None = None
    # When non-empty, keystrokes/typing only fire if the frontmost app's name or
    # bundle id matches one of these entries (substrings, e.g. bundle ids like
    # "com.apple.Terminal"). Empty list = act in any app.
    target_apps: list = field(default_factory=list)
    target_app: str = ""  # legacy single value; migrated into target_apps on load
    output_mode: str = "type"
    enabled: bool = True
    start_at_login: bool = False
    # First-run onboarding ("Set up TINK") completed at least once.
    onboarding_done: bool = False
    # Activity log: transcripts, target app, and actions written to a TSV file.
    log_activity: bool = False
    log_path: str = ""  # empty -> ~/Library/Logs/TinkAgent-activity.log
    # Save each captured utterance as a WAV so you can hear what the mic recorded
    # (diagnose "transcript cut off": was it the audio or the STT?).
    save_utterances: bool = False
    utterances_dir: str = ""  # empty -> ~/Library/Logs/TinkAgent-utterances

    def to_dict(self) -> dict:
        d = asdict(self)
        # JSON object keys must be strings; normalise int-keyed maps.
        d["tones"] = {str(k): v for k, v in self.tones.items()}
        d["slot_actions"] = {str(k): v for k, v in self.slot_actions.items()}
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Config":
        d = dict(d)
        if "tones" in d:
            d["tones"] = {int(k): int(v) for k, v in d["tones"].items()}
        if "slot_actions" in d:
            d["slot_actions"] = {int(k): str(v) for k, v in d["slot_actions"].items()}
        # Backfill mode-B slots (5-8) for configs written before they existed,
        # without clobbering any slot the user has set.
        defaults = cls()
        if "tones" in d:
            d["tones"] = {**defaults.tones, **d["tones"]}
        if "slot_actions" in d:
            d["slot_actions"] = {**defaults.slot_actions, **d["slot_actions"]}
        # Migrate legacy single target_app -> target_apps list.
        if not d.get("target_apps") and d.get("target_app"):
            d["target_apps"] = [d["target_app"]]
        known = {f for f in cls().__dict__}
        return cls(**{k: v for k, v in d.items() if k in known})

    def save(self, path=None) -> None:
        path = Path(path or DEFAULT_PATH)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2))

    @classmethod
    def load(cls, path=None) -> "Config":
        path = Path(path or DEFAULT_PATH)
        if not path.exists():
            c = cls()
            c.save(path)
            return c
        return cls.from_dict(json.loads(path.read_text()))
