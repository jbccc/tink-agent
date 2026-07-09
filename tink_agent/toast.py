"""Tiny top-right "live" toast — a borderless, click-through pill that fades in,
holds ~2s, then fades out and closes. Replaces the intrusive auto-onboarding
window with a non-interactive "Tink Agent is live" confirmation on startup.

Main thread only (AppKit). Self-contained: builds its own window and drives the
fade with NSAnimationContext, holding a module ref so it isn't GC'd mid-fade.
"""
from __future__ import annotations

import objc
from AppKit import (
    NSWindow, NSView, NSTextField, NSImageView, NSImage, NSColor, NSFont,
    NSMakeRect, NSBezierPath, NSScreen, NSAnimationContext, NSTimer,
    NSWindowStyleMaskBorderless, NSBackingStoreBuffered, NSFloatingWindowLevel,
    NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorStationary, NSViewWidthSizable,
)
from Foundation import NSObject

from . import theme

_LIVE = []  # keep toasts alive across the async fade so they aren't GC'd

MARGIN = 16          # gap from the screen's top-right corner
W, H = 190, 44
FADE = 0.25          # fade-in / fade-out seconds
HOLD = 2.0           # fully-visible dwell seconds


class _PillView(theme.Flipped):
    """Rounded, filled pill background (dark green with a hairline)."""

    def drawRect_(self, rect):
        b = self.bounds()
        r = b.size.height / 2.0
        path = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(b, r, r)
        theme.GREEN.setFill()
        path.fill()


class _Toast(NSObject):
    @objc.python_method
    def build(self, icon_path: str, text: str):
        screen = NSScreen.mainScreen()
        vf = screen.visibleFrame()
        # Top-right, just under the menu bar (visibleFrame excludes the menu bar).
        x = vf.origin.x + vf.size.width - W - MARGIN
        y = vf.origin.y + vf.size.height - H - MARGIN
        win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(x, y, W, H), NSWindowStyleMaskBorderless,
            NSBackingStoreBuffered, False)
        win.setLevel_(NSFloatingWindowLevel)
        win.setOpaque_(False)
        win.setBackgroundColor_(NSColor.clearColor())
        win.setIgnoresMouseEvents_(True)         # click-through
        win.setHasShadow_(True)
        win.setAlphaValue_(0.0)
        win.setCollectionBehavior_(
            NSWindowCollectionBehaviorCanJoinAllSpaces
            | NSWindowCollectionBehaviorStationary)

        pill = _PillView.alloc().initWithFrame_(NSMakeRect(0, 0, W, H))
        win.setContentView_(pill)

        # icon (template-tinted to the cream text color would need extra work;
        # the raw icon reads fine on the green pill)
        img = NSImage.alloc().initWithContentsOfFile_(icon_path)
        if img is not None:
            iv = NSImageView.alloc().initWithFrame_(NSMakeRect(12, (H - 22) / 2, 22, 22))
            iv.setImage_(img)
            iv.setImageScaling_(2)  # NSImageScaleProportionallyUpOrDown
            pill.addSubview_(iv)

        lbl = NSTextField.alloc().initWithFrame_(NSMakeRect(42, 0, W - 52, H))
        lbl.setStringValue_(text)
        lbl.setBezeled_(False)
        lbl.setDrawsBackground_(False)
        lbl.setEditable_(False)
        lbl.setSelectable_(False)
        lbl.setFont_(theme.font(13, "semibold"))
        lbl.setTextColor_(theme.color("#F3F0E7"))  # cream on green
        # vertically center the single line
        cell = lbl.cell()
        cell.setLineBreakMode_(4)  # truncate tail
        pill.addSubview_(lbl)
        self.window = win
        return self

    @objc.python_method
    def show(self):
        self.window.orderFrontRegardless()
        NSAnimationContext.beginGrouping()
        NSAnimationContext.currentContext().setDuration_(FADE)
        self.window.animator().setAlphaValue_(1.0)
        NSAnimationContext.endGrouping()
        # Schedule fade-out after the hold.
        self._timer = NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            FADE + HOLD, self, "fadeOut:", None, False)

    def fadeOut_(self, _timer):
        NSAnimationContext.beginGrouping()
        NSAnimationContext.currentContext().setDuration_(FADE)
        self.window.animator().setAlphaValue_(0.0)
        NSAnimationContext.endGrouping()
        NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            FADE, self, "done:", None, False)

    def done_(self, _timer):
        try:
            self.window.orderOut_(None)
            self.window.close()
        finally:
            if self in _LIVE:
                _LIVE.remove(self)


def show_live(icon_path: str, text: str = "Tink Agent is live") -> None:
    """Show the top-right live toast. Main thread only."""
    try:
        t = _Toast.alloc().init().build(icon_path, text)
        _LIVE.append(t)
        t.show()
    except Exception:  # noqa: BLE001 — a cosmetic toast must never break startup
        pass
