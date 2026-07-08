from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor


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
        # In "dictation_hotkey" mode we don't transcribe; we hold an external
        # app's push-to-talk key while voice is active. Track the held state so
        # we press on the voice-gate's rising edge and release on the falling one.
        self._dictation_key_down = False
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
            # Never leave the dictation PTT key stuck down when disabled mid-hold.
            if self._dictation_key_down:
                self._sync_dictation_key(False)
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
        if self.config.output_mode == "dictation_hotkey":
            # Drive an external dictation app: hold its push-to-talk key while the
            # voice gate is open, release when it closes. No transcription here.
            self._sync_dictation_key(self.voicegate.active)
            return
        if utterance is not None:
            self._submit(lambda u=utterance: self._handle_utterance(u))

    def _sync_dictation_key(self, voice_active: bool):
        if voice_active == self._dictation_key_down:
            return
        key = self.config.dictation_hotkey or "f15"
        if voice_active and self._target_ok(self._front()):
            self.router.press_hold(key)
            self._dictation_key_down = True
            self._on_event("dictation", "start")
        elif self._dictation_key_down:
            # Always release a held key, even if focus moved to a non-target app,
            # so we never get stuck with the PTT key down.
            self.router.release(key)
            self._dictation_key_down = False
            self._on_event("dictation", "stop")

    def _handle_utterance(self, utterance):
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
