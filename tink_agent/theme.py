"""Native-leaning visual theme for TinkAgent's AppKit windows.

Presentation only (pyobjc). Palette + Archivo font + thin helpers over native
controls; every control delegates behavior back to TinkAgentApp. Main thread.
"""
from __future__ import annotations

import sys
from pathlib import Path

from AppKit import (
    NSColor, NSFont, NSFontManager, NSTextField,
    NSLineBreakByWordWrapping, NSMakeRect,
)
from Foundation import NSURL
import CoreText

FONTS_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"


def color(hex_str: str, alpha: float = 1.0) -> NSColor:
    h = hex_str.lstrip("#")
    return NSColor.colorWithSRGBRed_green_blue_alpha_(
        int(h[0:2], 16) / 255.0, int(h[2:4], 16) / 255.0,
        int(h[4:6], 16) / 255.0, alpha)

BG = color("#EBE8E0")
CARD = color("#FCFBF7")
GREEN = color("#14543A")
MUTED = color("#7c8a7e")
SUBTLE = color("#8a988b")
PENDING = color("#9aa79b")
ORANGE = color("#F15D24")
HAIRLINE = color("#0F3A28", 0.10)

_REGISTERED = False


def register_fonts() -> None:
    global _REGISTERED
    if _REGISTERED:
        return
    fonts = sorted(FONTS_DIR.glob("*.ttf"))
    for ttf in fonts:
        try:
            CoreText.CTFontManagerRegisterFontsForURL(
                NSURL.fileURLWithPath_(str(ttf)),
                CoreText.kCTFontManagerScopeProcess, None)
        except Exception as e:  # noqa: BLE001 — a bad font must not crash the app
            print(f"[theme] could not register {ttf.name}: {e}",
                  file=sys.stderr, flush=True)
    if fonts:
        _REGISTERED = True


register_fonts()

_WEIGHTS = {"light": 3, "regular": 5, "medium": 6, "semibold": 8, "bold": 9}


def font(size: float, weight: str = "regular") -> NSFont:
    w = _WEIGHTS.get(weight, 5)
    f = NSFontManager.sharedFontManager().fontWithFamily_traits_weight_size_(
        "Archivo", 0, w, size)
    if f is not None and f.familyName() == "Archivo":
        return f
    from AppKit import (
        NSFontWeightLight, NSFontWeightRegular, NSFontWeightMedium,
        NSFontWeightSemibold, NSFontWeightBold,
    )
    sysw = {"light": NSFontWeightLight, "regular": NSFontWeightRegular,
            "medium": NSFontWeightMedium, "semibold": NSFontWeightSemibold,
            "bold": NSFontWeightBold}.get(weight, NSFontWeightRegular)
    return NSFont.systemFontOfSize_weight_(size, sysw)


def label(text, *, size=13.0, weight="regular", color=None, wrap=False) -> NSTextField:
    # Avoid NSTextField.labelWithString_: it calls sizeToFit immediately, which
    # can abort in non-GUI test runners while AppKit registers the process.
    lbl = NSTextField.alloc().initWithFrame_(NSMakeRect(0, 0, 10, 10))
    lbl.setStringValue_(text)
    lbl.setBezeled_(False)
    lbl.setDrawsBackground_(False)
    lbl.setEditable_(False)
    lbl.setSelectable_(False)
    lbl.setFont_(font(size, weight))
    if color is not None:
        lbl.setTextColor_(color)
    if wrap:
        lbl.setUsesSingleLineMode_(False)
        lbl.setLineBreakMode_(NSLineBreakByWordWrapping)
        lbl.cell().setWraps_(True)
        lbl.setMaximumNumberOfLines_(0)
    return lbl


import objc
from AppKit import (
    NSView, NSBox, NSBoxCustom, NSWindow, NSButton, NSMakeRect, NSColor as _NSC,
    NSWindowStyleMaskTitled, NSWindowStyleMaskClosable, NSBackingStoreBuffered,
    NSNoTitle, NSBezelStyleRounded, NSAttributedString, NSFontAttributeName,
    NSForegroundColorAttributeName, NSCenterTextAlignment,
    NSMutableParagraphStyle, NSParagraphStyleAttributeName,
    NSAppearance, NSAppearanceNameAqua,
    NSSegmentedControl, NSSegmentStyleRounded,
)
from Foundation import NSObject


class Flipped(NSView):
    def isFlipped(self):
        return True


class _BGView(NSView):
    def isFlipped(self):
        return True

    def drawRect_(self, rect):
        BG.setFill()
        from AppKit import NSBezierPath
        NSBezierPath.fillRect_(self.bounds())


class _Target(NSObject):
    """Reusable target: forwards an ObjC action to a stored Python callable."""
    def initWithCb_(self, cb):
        self = objc.super(_Target, self).init()
        if self is None:
            return None
        self._cb = cb
        return self

    def fire_(self, sender):
        if self._cb is not None:
            self._cb()


# Native AppKit controls (NSButton/NSPopUpButton/NSSwitch) don't accept arbitrary
# Python attributes, so the helper target can't be stashed on the control itself.
# Keep targets alive for the process lifetime in a module-level list instead — a
# settings UI creates only a handful, so this is not a meaningful leak.
_LIVE_TARGETS = []


def _retain(obj, target):
    """Keep a helper target alive so its target/action callback survives GC.

    `obj` is accepted for call-site readability but not used for storage —
    native controls reject attribute assignment."""
    _LIVE_TARGETS.append(target)


def window(title, w, h):
    style = NSWindowStyleMaskTitled | NSWindowStyleMaskClosable
    win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        NSMakeRect(0, 0, w, h), style, NSBackingStoreBuffered, False)
    win.setTitle_(title)
    win.setReleasedWhenClosed_(False)
    # The theme is a fixed warm-light palette, so pin the window (and every
    # native control inside it) to the light Aqua appearance. Without this, on a
    # Dark-Mode system NSPopUpButton/NSSwitch draw dark-appearance chrome (white
    # text, dark tracks) that is invisible on our cream background.
    aqua = NSAppearance.appearanceNamed_(NSAppearanceNameAqua)
    if aqua is not None:
        win.setAppearance_(aqua)
    win.center()
    root = _BGView.alloc().initWithFrame_(NSMakeRect(0, 0, w, h))
    win.setContentView_(root)
    return win, root


def section_header(text):
    return label(text, size=12.5, weight="semibold", color=MUTED)


def card(x, y, w, h):
    box = NSBox.alloc().initWithFrame_(NSMakeRect(x, y, w, h))
    box.setBoxType_(NSBoxCustom)
    box.setTitlePosition_(NSNoTitle)
    box.setFillColor_(CARD)
    box.setBorderColor_(HAIRLINE)
    box.setBorderWidth_(0.5)
    box.setCornerRadius_(10.0)
    box.setContentViewMargins_((0, 0))
    box.setContentView_(Flipped.alloc().initWithFrame_(NSMakeRect(0, 0, w, h)))
    return box


def hairline(x, y, w):
    v = NSView.alloc().initWithFrame_(NSMakeRect(x, y, w, 0.5))
    v.setWantsLayer_(True)
    v.layer().setBackgroundColor_(HAIRLINE.CGColor())
    return v


def _attr_title(text, fnt, col, center=False):
    attrs = {NSFontAttributeName: fnt, NSForegroundColorAttributeName: col}
    if center:
        para = NSMutableParagraphStyle.alloc().init()
        para.setAlignment_(NSCenterTextAlignment)
        attrs[NSParagraphStyleAttributeName] = para
    return NSAttributedString.alloc().initWithString_attributes_(text, attrs)


def _wire(btn, on_click):
    t = _Target.alloc().initWithCb_(on_click)
    btn.setTarget_(t)
    btn.setAction_("fire:")
    _retain(btn, t)


def accent_button(title, on_click, x, y, w, h=30):
    b = NSButton.alloc().initWithFrame_(NSMakeRect(x, y, w, h))
    b.setBezelStyle_(NSBezelStyleRounded)
    b.setBordered_(True)
    b.setBezelColor_(ORANGE)
    b.setAttributedTitle_(_attr_title(title, font(13, "semibold"),
                                      _NSC.whiteColor(), center=True))
    _wire(b, on_click)
    return b


def set_secondary(btn, is_secondary, title):
    """Swap an accent button between its orange primary and muted secondary look.

    A module function (not a method on the button) because native NSButton
    instances reject attribute assignment."""
    if is_secondary:
        btn.setBezelColor_(CARD)
        btn.setAttributedTitle_(_attr_title(title, font(13, "medium"),
                                            MUTED, center=True))
    else:
        btn.setBezelColor_(ORANGE)
        btn.setAttributedTitle_(_attr_title(title, font(13, "semibold"),
                                            _NSC.whiteColor(), center=True))


def plain_button(title, on_click, x, y, w, h=28):
    b = NSButton.alloc().initWithFrame_(NSMakeRect(x, y, w, h))
    b.setBezelStyle_(NSBezelStyleRounded)
    b.setAttributedTitle_(_attr_title(title, font(13, "medium"), GREEN, center=True))
    _wire(b, on_click)
    return b


def set_plain_title(btn, text):
    """Re-label a plain button while preserving its Archivo/green styling."""
    btn.setAttributedTitle_(_attr_title(text, font(13, "medium"), GREEN, center=True))


def link_button(title, on_click, x, y, w, h=18):
    b = NSButton.alloc().initWithFrame_(NSMakeRect(x, y, w, h))
    b.setBordered_(False)
    b.setAttributedTitle_(_attr_title(title, font(12, "medium"), ORANGE))
    _wire(b, on_click)
    return b


from AppKit import (
    NSSwitch, NSPopUpButton, NSControlStateValueOn, NSControlStateValueOff,
    NSBezierPath, NSTextAlignmentCenter,
)


def switch_row(title, subtitle, on, on_change, w, y, h=44):
    row = Flipped.alloc().initWithFrame_(NSMakeRect(0, y, w, h))
    ty = 8 if subtitle else (h - 18) / 2.0
    lbl = label(title, size=13.5, weight="medium", color=GREEN)
    lbl.setFrame_(NSMakeRect(15, ty, w - 80, 18))
    row.addSubview_(lbl)
    if subtitle:
        sub = label(subtitle, size=11.5, weight="regular", color=SUBTLE)
        sub.setFrame_(NSMakeRect(15, ty + 18, w - 80, 16))
        row.addSubview_(sub)
    sw = NSSwitch.alloc().initWithFrame_(NSMakeRect(w - 55, (h - 25) / 2.0, 40, 25))
    sw.setState_(NSControlStateValueOn if on else NSControlStateValueOff)
    t = _Target.alloc().initWithCb_(
        lambda: on_change(sw.state() == NSControlStateValueOn))
    sw.setTarget_(t)
    sw.setAction_("fire:")
    _retain(row, t)
    row.addSubview_(sw)
    return row, sw


def popup_row(title, w, y, *, trailing_w=0, h=44):
    row = Flipped.alloc().initWithFrame_(NSMakeRect(0, y, w, h))
    lbl = label(title, size=13.5, weight="medium", color=GREEN)
    lbl.setFrame_(NSMakeRect(15, (h - 18) / 2.0, 110, 18))
    row.addSubview_(lbl)
    px = 130
    pw = w - px - 15 - trailing_w
    popup = NSPopUpButton.alloc().initWithFrame_pullsDown_(
        NSMakeRect(px, (h - 26) / 2.0, pw, 26), False)
    row.addSubview_(popup)
    return row, popup


def segmented(titles, selected, on_select, x, y, w, h=26):
    """A themed NSSegmentedControl. `on_select` receives the selected index."""
    seg = NSSegmentedControl.alloc().initWithFrame_(NSMakeRect(x, y, w, h))
    seg.setSegmentStyle_(NSSegmentStyleRounded)
    seg.setSegmentCount_(len(titles))
    seg.setFont_(font(13, "medium"))
    for i, t in enumerate(titles):
        seg.setLabel_forSegment_(t, i)
        seg.setWidth_forSegment_(float(w) / len(titles), i)
    seg.setSelectedSegment_(selected)
    t = _Target.alloc().initWithCb_(lambda: on_select(int(seg.selectedSegment())))
    seg.setTarget_(t)
    seg.setAction_("fire:")
    _retain(seg, t)
    return seg


class StepRow(NSView):
    @objc.python_method
    @classmethod
    def make(cls, index1, title, subtitle, x, y, w, last=False):
        h = 92
        self = cls.alloc().initWithFrame_(NSMakeRect(x, y, w, h))
        self._index1 = index1
        if not last:
            line = NSView.alloc().initWithFrame_(NSMakeRect(11, 30, 2, h - 30))
            line.setWantsLayer_(True)
            line.layer().setBackgroundColor_(color("#0F3A28", 0.15).CGColor())
            self.addSubview_(line)
        self._circle = _StepCircle.alloc().initWithFrame_(NSMakeRect(0, 0, 24, 24))
        self.addSubview_(self._circle)
        self._title = label(title, size=14.5, weight="semibold", color=GREEN)
        self._title.setFrame_(NSMakeRect(38, 1, w - 42, 20))
        self.addSubview_(self._title)
        self._sub = label(subtitle, size=12.5, weight="regular", color=SUBTLE,
                          wrap=True)
        self._sub.setFrame_(NSMakeRect(38, 22, w - 42, 30))
        self.addSubview_(self._sub)
        self._body = Flipped.alloc().initWithFrame_(NSMakeRect(38, 54, w - 42, 32))
        self.addSubview_(self._body)
        self.set_state("pending")
        return self

    def isFlipped(self):
        return True

    @objc.python_method
    def body_area(self):
        return self._body

    @objc.python_method
    def set_subtitle(self, text):
        self._sub.setStringValue_(text)

    @objc.python_method
    def set_state(self, state):
        self._circle.set_state_index_(state, self._index1)
        self._title.setTextColor_(PENDING if state == "pending" else GREEN)


class _StepCircle(NSView):
    def initWithFrame_(self, frame):
        self = objc.super(_StepCircle, self).initWithFrame_(frame)
        if self is None:
            return None
        self._state = "pending"
        self._index1 = 1
        return self

    def isFlipped(self):
        return True

    @objc.python_method
    def set_state_index_(self, state, index1):
        self._state = state
        self._index1 = index1
        self.setNeedsDisplay_(True)

    def drawRect_(self, rect):
        b = self.bounds()
        inset = NSMakeRect(1.5, 1.5, b.size.width - 3, b.size.height - 3)
        ring = NSBezierPath.bezierPathWithOvalInRect_(inset)
        if self._state == "done":
            ORANGE.setFill(); ring.fill()
            _NSC.whiteColor().setStroke()
            chk = NSBezierPath.bezierPath(); chk.setLineWidth_(2.2)
            sx, sy = b.size.width, b.size.height
            chk.moveToPoint_((sx * 0.27, sy * 0.52))
            chk.lineToPoint_((sx * 0.43, sy * 0.68))
            chk.lineToPoint_((sx * 0.73, sy * 0.34))
            chk.stroke()
        elif self._state == "active":
            CARD.setFill(); ring.fill()
            ORANGE.setStroke(); ring.setLineWidth_(2.5); ring.stroke()
            dot = NSBezierPath.bezierPathWithOvalInRect_(
                NSMakeRect(b.size.width / 2 - 4, b.size.height / 2 - 4, 8, 8))
            ORANGE.setFill(); dot.fill()
        else:
            color("#0F3A28", 0.22).setStroke(); ring.setLineWidth_(2.0); ring.stroke()
            para = NSMutableParagraphStyle.alloc().init()
            para.setAlignment_(NSTextAlignmentCenter)
            attrs = {NSFontAttributeName: font(12, "semibold"),
                     NSForegroundColorAttributeName: PENDING,
                     NSParagraphStyleAttributeName: para}
            NSAttributedString.alloc().initWithString_attributes_(
                str(self._index1), attrs).drawInRect_(
                    NSMakeRect(0, 5, b.size.width, 16))
