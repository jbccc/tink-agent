from __future__ import annotations
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .transcribe import write_wav


class Engine:
    def __init__(self, config, detector, voicegate, transcriber, router,
                 on_event=None, submit_fn=None, frontmost_fn=None, logger=None):
        self.config = config
        self.detector = detector
        self.voicegate = voicegate
        self.transcriber = transcriber
        self.router = router
        self.logger = logger
        self.enabled = config.enabled
        self._on_event = on_event or (lambda kind, payload: None)
        # Optional safety guard: when config.target_app is set, actions/typing
        # only fire if the frontmost app's name or bundle id contains it.
        # frontmost_fn() -> str is injectable for tests; defaults to NSWorkspace.
        self._frontmost_fn = frontmost_fn or _default_frontmost
        if submit_fn is not None:
            self._submit = submit_fn
        else:
            self._pool = ThreadPoolExecutor(max_workers=1)
            self._submit = lambda fn: self._pool.submit(fn)

    @property
    def is_capturing(self) -> bool:
        """True while an utterance is open (used by the menu bar indicator)."""
        return bool(getattr(self.voicegate, "active", False))

    def _front(self) -> str:
        try:
            return self._frontmost_fn() or ""
        except Exception:  # noqa: BLE001 — never let the guard crash the path
            return ""

    def _target_ok(self, front: str) -> bool:
        targets = [t.strip().lower()
                   for t in (self.config.target_apps or []) if t and t.strip()]
        if not targets:
            return True
        f = front.lower()
        return any(t in f for t in targets)

    def handle_block(self, block):
        if not self.enabled:
            return
        slot = self.detector.process(block)
        if slot is not None:
            front = self._front()
            if self._target_ok(front):
                action = self.router.fire_slot(slot)
                self._on_event("tone", slot)
                self._on_event("action", action)
                if self.logger:
                    self.logger.action(slot, action, front)
            else:
                self._on_event("blocked", slot)
                if self.logger:
                    self.logger.blocked(f"slot{slot}", front)
        utterance = self.voicegate.process(block, self.detector.tone_active)
        if utterance is not None:
            self._submit(lambda u=utterance: self._handle_utterance(u))

    def _handle_utterance(self, utterance):
        if getattr(self.config, "save_utterances", False):
            self._save_utterance(utterance)
        text = self.transcriber.transcribe(utterance, self.config.sample_rate)
        if not text:
            if self.transcriber.last_error:
                self._on_event("error", self.transcriber.last_error)
            return
        front = self._front()
        if not self._target_ok(front):
            self._on_event("blocked", text)
            if self.logger:
                self.logger.blocked(text, front)
            return
        self.router.type_text(text)
        self._on_event("transcript", text)
        if self.logger:
            self.logger.transcript(text, front)

    def _save_utterance(self, utterance):
        """Write the captured utterance to a WAV so the user can play it back and
        hear exactly what the mic recorded. Best-effort: never break capture."""
        try:
            d = (self.config.utterances_dir
                 or str(Path.home() / "Library" / "Logs" / "TinkAgent-utterances"))
            d = Path(d)
            d.mkdir(parents=True, exist_ok=True)
            # Timestamped, second-resolution + block count so filenames sort by
            # recency and the newest is obviously "the last thing I said".
            stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime())
            path = d / f"utt-{stamp}.wav"
            # If two utterances land in the same second, disambiguate.
            n = 1
            while path.exists():
                n += 1
                path = d / f"utt-{stamp}-{n}.wav"
            write_wav(utterance, path, self.config.sample_rate)
            self._on_event("saved", str(path))
        except Exception as e:  # noqa: BLE001 — saving is a convenience, not critical
            self._on_event("error", f"save utterance failed: {e}")


def _default_frontmost() -> str:
    """Frontmost app identity (name + bundle id) via AppKit, or "" if unavailable."""
    try:
        from AppKit import NSWorkspace
        app = NSWorkspace.sharedWorkspace().frontmostApplication()
        if app is None:
            return ""
        return f"{app.localizedName() or ''} {app.bundleIdentifier() or ''}"
    except Exception:  # noqa: BLE001
        return ""
