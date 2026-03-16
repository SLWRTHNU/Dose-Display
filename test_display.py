#!/usr/bin/env python3
"""
Shell preview of the three display states (160×128 px, upscaled for terminal).

Images not yet on device are shown as coloured placeholder rectangles.

Usage:
    python3 test_display.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from PIL import Image, ImageDraw
import small_font
import arrows_font

# ── constants from config ─────────────────────────────────────────────────────
DISPLAY_WIDTH  = 160
DISPLAY_HEIGHT = 128
BG_ARROW_GAP   = 8
TREND_ARROWS   = {
    'DoubleUp':      'OO',
    'SingleUp':      'O',
    'FortyFiveUp':   'L',
    'Flat':          'J',
    'FortyFiveDown': 'N',
    'SingleDown':    'P',
    'DoubleDown':    'PP',
}

BLACK = (0,   0,   0)
WHITE = (255, 255, 255)

# ── font helpers ──────────────────────────────────────────────────────────────

def _draw_custom_text(draw, font_mod, text, x, y, color):
    cx = x
    for ch in text:
        glyph, h, w = font_mod.get_ch(ch)
        bpr = (w - 1) // 8 + 1          # bytes per row
        for row in range(h):
            for col in range(w):
                bi = row * bpr + col // 8
                if bi < len(glyph) and (glyph[bi] >> (7 - col % 8)) & 1:
                    draw.point((cx + col, y + row), fill=color)
        cx += w + 1
    return cx - x


def _text_width(font_mod, text):
    if not text:
        return 0
    total = sum(font_mod.get_ch(c)[2] + 1 for c in text)
    return total - 1


def _draw_text_2x(draw, text, x, y, color):
    """Render text as a 16-pixel-tall block using a temp PIL image."""
    tmp = Image.new('1', (len(text) * 8, 8), 0)
    ImageDraw.Draw(tmp).text((0, 0), text, fill=1)
    for py in range(8):
        for px in range(len(text) * 8):
            if tmp.getpixel((px, py)):
                dx, dy = x + px * 2, y + py * 2
                draw.point((dx,     dy    ), fill=color)
                draw.point((dx + 1, dy    ), fill=color)
                draw.point((dx,     dy + 1), fill=color)
                draw.point((dx + 1, dy + 1), fill=color)

# ── action parser (mirrors main.py) ──────────────────────────────────────────

def _parse_action(action):
    if not action:
        return 'none', 0
    if action == 'Water':
        return 'water', 0
    if action == 'Juicebox':
        return 'juicebox', 0
    if action.startswith('Give ') and 'JB' in action:
        try:
            return 'jb', int(action.split()[1])
        except Exception:
            return 'jb', 2
    return 'none', 0

# ── placeholder image (replaces a missing .bin) ───────────────────────────────

def _placeholder(w, h, color, label):
    img = Image.new('RGB', (w, h), color)
    d   = ImageDraw.Draw(img)
    d.rectangle([0, 0, w - 1, h - 1], outline=WHITE)
    lw  = len(label) * 6
    d.text(((w - lw) // 2, h // 2 - 4), label, fill=WHITE)
    return img

# ── scene renderer ────────────────────────────────────────────────────────────

def render_scene(action, bg, trend):
    img  = Image.new('RGB', (DISPLAY_WIDTH, DISPLAY_HEIGHT), BLACK)
    draw = ImageDraw.Draw(img)

    kind, count = _parse_action(action)

    if kind == 'water':
        ph = _placeholder(80, 80, (0, 90, 180), 'WATER')
        img.paste(ph, (40, 4))

    elif kind == 'juicebox':
        ph = _placeholder(80, 80, (200, 120, 0), 'JUICEBOX')
        img.paste(ph, (40, 4))

    elif kind == 'jb':
        x0 = (DISPLAY_WIDTH - 80) // 2   # = 40
        ph = _placeholder(40, 40, (180, 40, 40), 'JB')
        _draw_text_2x(draw, f"{count}x", x0, 36, WHITE)
        img.paste(ph, (x0 + 40, 24))

    # ── BG value + trend arrow ────────────────────────────────────────────────
    bg_text = f"{bg:.1f}"
    arrow   = TREND_ARROWS.get(trend, 'J')

    bg_w   = _text_width(small_font,  bg_text)
    arr_w  = _text_width(arrows_font, arrow)
    total  = bg_w + BG_ARROW_GAP + arr_w
    sx     = (DISPLAY_WIDTH - total) // 2

    _draw_custom_text(draw, small_font,  bg_text, sx,                       95, WHITE)
    _draw_custom_text(draw, arrows_font, arrow,   sx + bg_w + BG_ARROW_GAP, 95, WHITE)

    return img

# ── ANSI half-block terminal renderer ────────────────────────────────────────

def print_ansi(img, tw=80):
    """Print a PIL Image to the terminal using ▀ half-block chars."""
    ratio = img.height / img.width
    th    = int(tw * ratio / 2)          # /2 because each char row = 2 pixel rows
    img   = img.resize((tw, th * 2), Image.NEAREST)
    px    = img.load()
    w, h  = img.size
    for y in range(0, h, 2):
        for x in range(w):
            r1, g1, b1 = px[x, y]
            r2, g2, b2 = px[x, min(y + 1, h - 1)]
            sys.stdout.write(
                f"\x1b[38;2;{r1};{g1};{b1}m"
                f"\x1b[48;2;{r2};{g2};{b2}m▀"
            )
        sys.stdout.write("\x1b[0m\n")

# ── scenes ────────────────────────────────────────────────────────────────────

SCENES = [
    ("1 — Water",    "Water",     5.6, "Flat"),
    ("2 — 2× JB",    "Give 2 JB", 5.6, "Flat"),
    ("3 — Juicebox", "Juicebox",  5.6, "Flat"),
]

for title, action, bg, trend in SCENES:
    print(f"\n\x1b[1;7m  {title}  \x1b[0m")
    print_ansi(render_scene(action, bg, trend))
