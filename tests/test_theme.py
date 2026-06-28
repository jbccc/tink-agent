import pytest
AppKit = pytest.importorskip("AppKit")
from tink_agent import theme


def test_color_parses_hex():
    c = theme.color("#14543A").colorUsingColorSpace_(
        AppKit.NSColorSpace.sRGBColorSpace())
    assert round(c.redComponent() * 255) == 0x14
    assert round(c.greenComponent() * 255) == 0x54
    assert round(c.blueComponent() * 255) == 0x3A


def test_color_alpha():
    assert round(theme.color("#000000", 0.1).alphaComponent(), 2) == 0.1


def test_named_constants_are_colors():
    for c in (theme.BG, theme.CARD, theme.GREEN, theme.MUTED, theme.SUBTLE,
              theme.PENDING, theme.ORANGE, theme.HAIRLINE):
        assert isinstance(c, AppKit.NSColor)


def test_font_returns_archivo():
    f = theme.font(13.0, "semibold")
    assert isinstance(f, AppKit.NSFont)
    assert f.familyName() == "Archivo"
    assert round(f.pointSize(), 1) == 13.0


def test_font_falls_back_for_unknown_weight():
    f = theme.font(12.0, "no-such-weight")
    assert isinstance(f, AppKit.NSFont)
    assert round(f.pointSize(), 1) == 12.0


def test_label_sets_font_and_text():
    lbl = theme.label("Hi", size=14, weight="bold", color=theme.GREEN)
    assert lbl.stringValue() == "Hi"
    assert round(lbl.font().pointSize(), 1) == 14.0
    got = lbl.textColor().colorUsingColorSpace_(AppKit.NSColorSpace.sRGBColorSpace())
    want = theme.GREEN.colorUsingColorSpace_(AppKit.NSColorSpace.sRGBColorSpace())
    assert round(got.redComponent(), 3) == round(want.redComponent(), 3)
    assert round(got.greenComponent(), 3) == round(want.greenComponent(), 3)
    assert round(got.blueComponent(), 3) == round(want.blueComponent(), 3)
