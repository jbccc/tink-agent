"""Generate the menu-bar template icon for tink-agent.

Draws a simple monochrome contour of the EP-2350 Ting handheld mic: a
rounded-square body outline with the circular grille and a button hint.
Output is a black-on-transparent PNG suitable for a macOS template image
(rumps `template=True`), which the system recolors for light/dark menu bars.

Run: python assets/make_icon.py
"""
from pathlib import Path
from PIL import Image, ImageDraw

OUT = Path(__file__).parent / "tink_icon.png"
OUT_ACTIVE = Path(__file__).parent / "tink_icon_active.png"
SIZE = 44          # final px (~22 pt @2x)
SCALE = 4          # supersample for crisp antialiased edges
INK = (0, 0, 0, 255)


def rounded_outline(draw, box, radius, width):
    draw.rounded_rectangle(box, radius=radius, outline=INK, width=width)


def render(active: bool):
    """Render the Ting contour. active=True fills the grille (capturing state)."""
    s = SIZE * SCALE
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    w = 3 * SCALE  # stroke width

    # Body: rounded-square handheld contour, centered with margin.
    m = 6 * SCALE
    body = [m, m, s - m, s - m]
    rounded_outline(d, body, radius=9 * SCALE, width=w)

    # Grille: circle in the upper portion (the mic/speaker).
    cx = s / 2
    gy = s * 0.40
    gr = s * 0.17
    grille = [cx - gr, gy - gr, cx + gr, gy + gr]
    if active:
        d.ellipse(grille, fill=INK)          # filled = capturing voice
    else:
        d.ellipse(grille, outline=INK, width=w)

    # Button hint: a short rounded bar low on the body (the PTT/handle row).
    bw, bh = s * 0.26, 3 * SCALE
    by = s * 0.70
    d.rounded_rectangle(
        [cx - bw / 2, by - bh / 2, cx + bw / 2, by + bh / 2],
        radius=bh, fill=INK,
    )
    return img.resize((SIZE, SIZE), Image.LANCZOS)


def main():
    render(False).save(OUT)
    render(True).save(OUT_ACTIVE)
    print(f"wrote {OUT}")
    print(f"wrote {OUT_ACTIVE}")


if __name__ == "__main__":
    main()
