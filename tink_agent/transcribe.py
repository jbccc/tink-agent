"""Speech-to-text via an external CLI (open command template).

Any tool that takes an audio file and emits text works. The command is a list of
tokens with placeholders substituted per utterance:
  {file}        -> the temp WAV we write
  {output}      -> a temp .txt path (use with output_mode="file")
  {output_dir}  -> a temp dir (use with output_mode="dir"; we read the .txt it writes)

output_mode controls how the transcript is read:
  "last_line" -> last non-empty stdout line (MacWhisper prints a status line first)
  "all"       -> all non-empty stdout lines joined (tools that stream to stdout)
  "file"      -> read the {output} file
  "dir"       -> read the .txt written into {output_dir}

Built-in presets live in PRESETS; "custom" uses config.stt_command/stt_output.
"""
from __future__ import annotations
import os
import re
import subprocess
import tempfile
import uuid
import wave
from pathlib import Path
import numpy as np


# Whisper captions non-speech audio (noise, silence, tone edges) as bracketed or
# parenthesised sound tags — "[Music]", "(triumphant music)", "*Sings*", "[BLANK_AUDIO]".
# These must never be typed as keystrokes. Strip any run wrapped in [] () or **,
# then treat a transcript that was ENTIRELY such tags as empty.
_ANNOTATION_RE = re.compile(r"\[[^\]]*\]|\([^)]*\)|\*[^*]*\*")


def clean_transcript(text: str) -> str:
    """Remove Whisper non-speech annotations; return '' if nothing else remains."""
    stripped = _ANNOTATION_RE.sub(" ", text)
    # Collapse whitespace left behind by removed tags.
    return re.sub(r"\s+", " ", stripped).strip()


def _default_http_post(url: str, api_key: str, model: str, wav_bytes: bytes) -> str:
    """POST a WAV to an OpenAI-Whisper-compatible transcription endpoint (Aqua
    Avalon) as multipart/form-data; return the transcript text. Raises on any
    HTTP/network/parse error so the caller can record it and type nothing."""
    import json
    import urllib.request

    boundary = "----tinkagent" + uuid.uuid4().hex
    dd = f"--{boundary}\r\n".encode()
    body = (
        dd
        + b'Content-Disposition: form-data; name="model"\r\n\r\n'
        + model.encode() + b"\r\n"
        + dd
        + b'Content-Disposition: form-data; name="file"; filename="utt.wav"\r\n'
        + b"Content-Type: audio/wav\r\n\r\n"
        + wav_bytes + b"\r\n"
        + f"--{boundary}--\r\n".encode()
    )
    req = urllib.request.Request(url, data=body, headers={
        "Authorization": f"Bearer {api_key}",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
    })
    with urllib.request.urlopen(req, timeout=120) as resp:
        payload = resp.read().decode("utf-8", errors="replace")
    # OpenAI-compatible: {"text": "..."}. Fall back to raw body if not JSON.
    try:
        return json.loads(payload).get("text", "")
    except Exception:  # noqa: BLE001
        return payload.strip()


def write_wav(samples: np.ndarray, path, sample_rate: int) -> None:
    samples = np.asarray(samples, dtype=np.int16).reshape(-1)
    w = wave.open(str(path), "wb")
    try:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(samples.tobytes())
    finally:
        w.close()


# --- backend presets -------------------------------------------------------

def _macwhisper(config):
    cmd = [config.mw_binary, "transcribe", "{file}"]
    if config.stt_model:
        cmd += ["--model", config.stt_model]
    return cmd, "last_line"


def _whisper_cpp(config):
    # whisper.cpp's CLI prints clean text to stdout with -nt (no timestamps).
    return ["whisper-cli", "-f", "{file}", "-nt"], "all"


def _openai_whisper(config):
    return ["whisper", "{file}", "--model", (config.stt_model or "base"),
            "--output_format", "txt", "--output_dir", "{output_dir}"], "dir"


# name -> (label, builder(config) -> (command, output_mode))
PRESETS = {
    "macwhisper": ("MacWhisper", _macwhisper),
    "whisper-cpp": ("whisper.cpp", _whisper_cpp),
    "openai-whisper": ("openai-whisper", _openai_whisper),
}
BACKEND_ORDER = ["macwhisper", "whisper-cpp", "openai-whisper", "aqua-api", "custom"]
BACKEND_LABELS = {k: v[0] for k, v in PRESETS.items()} | {
    "aqua-api": "Aqua Voice API", "custom": "Custom (edit config)"}


def resolve_stt(config):
    """Return (command_list, output_mode) for the configured backend."""
    backend = (getattr(config, "stt_backend", "") or "macwhisper")
    if backend == "custom":
        cmd = list(config.stt_command) if config.stt_command \
            else [config.mw_binary, "transcribe", "{file}"]
        return cmd, (config.stt_output or "last_line")
    if backend == "aqua-api":
        # No subprocess command; the HTTP branch in Transcriber handles it.
        return [], "aqua"
    builder = PRESETS.get(backend, PRESETS["macwhisper"])[1]
    return builder(config)


def aqua_config(config):
    """(url, model) for the Aqua API from config, with the model override applied."""
    url = getattr(config, "aqua_api_url", "") \
        or "https://api.aquavoice.com/api/v1/audio/transcriptions"
    model = (getattr(config, "stt_model", "") or getattr(config, "aqua_model", "")
             or "avalon-v1.5")
    return url, model


# --- the transcriber -------------------------------------------------------

class Transcriber:
    def __init__(self, command, output_mode="last_line", runner=subprocess.run,
                 aqua_url=None, aqua_model=None, http_post=None):
        self.command = list(command)
        self.output_mode = output_mode
        self._runner = runner
        # Aqua API mode (output_mode == "aqua"): POST the WAV instead of shelling
        # out. http_post is injectable for tests; defaults to _default_http_post.
        self._aqua_url = aqua_url
        self._aqua_model = aqua_model or "avalon-v1.5"
        self._http_post = http_post or _default_http_post
        self.last_error: str | None = None

    @staticmethod
    def _subst(tok, wav, outfile, outdir):
        return (tok.replace("{file}", str(wav))
                   .replace("{output_dir}", str(outdir))
                   .replace("{output}", str(outfile)))

    def transcribe(self, samples: np.ndarray, sample_rate: int) -> str:
        self.last_error = None
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            wav = d / "utt.wav"
            write_wav(samples, wav, sample_rate)
            if self.output_mode == "aqua":
                return self._transcribe_aqua(wav)
            outfile = d / "out.txt"
            cmd = [self._subst(t, wav, outfile, d) for t in self.command]
            try:
                res = self._runner(cmd, capture_output=True, text=True, timeout=120)
            except Exception as e:  # noqa: BLE001
                self.last_error = str(e)
                return ""
            if res.returncode != 0:
                self.last_error = (res.stderr or res.stdout or "stt failed").strip()
                return ""
            return self._parse(res.stdout or "", outfile, d)

    def _transcribe_aqua(self, wav: Path) -> str:
        key = os.environ.get("AQUA_API_KEY", "")
        if not key:
            self.last_error = "AQUA_API_KEY not set"
            return ""
        try:
            text = self._http_post(self._aqua_url, key, self._aqua_model, wav.read_bytes())
        except Exception as e:  # noqa: BLE001 — network/API errors -> type nothing
            self.last_error = str(e)
            return ""
        return clean_transcript(text or "")

    def _parse(self, stdout: str, outfile: Path, outdir: Path) -> str:
        return clean_transcript(self._raw(stdout, outfile, outdir))

    def _raw(self, stdout: str, outfile: Path, outdir: Path) -> str:
        mode = self.output_mode
        if mode == "file":
            return outfile.read_text(encoding="utf-8", errors="replace").strip() \
                if outfile.exists() else ""
        if mode == "dir":
            txts = [p for p in sorted(outdir.glob("*.txt")) if p != outfile]
            return txts[-1].read_text(encoding="utf-8", errors="replace").strip() \
                if txts else ""
        lines = [ln.strip() for ln in stdout.splitlines() if ln.strip()]
        lines = [ln for ln in lines if not ln.lower().startswith("transcribing")]
        if mode == "all":
            return " ".join(lines).strip()
        return lines[-1] if lines else ""  # last_line
