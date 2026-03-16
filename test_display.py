#!/usr/bin/env python3
"""
Shell preview of the three display states (160×128 px, upscaled for terminal).

Copy the .bin files off the Pico first:
    mpremote cp :water.bin    water.bin
    mpremote cp :jb.bin       jb.bin
    mpremote cp :juicebox.bin juicebox.bin

Then run:
    python3 test_display.py

Real images are used when the .bin files are present; coloured placeholders
are shown otherwise.
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

# ── image loading ─────────────────────────────────────────────────────────────

ACTION_H = 95  # pixels above BG text row (y=0..94)


def _load_bin(filename):
    """Load a .bin with 4-byte header (W, H big-endian) → (PIL Image, w, h), or (None, 0, 0)."""
    path = os.path.join(os.path.dirname(__file__), filename)
    if not os.path.exists(path):
        return None, 0, 0
    with open(path, 'rb') as f:
        header = f.read(4)
        data   = f.read()
    w = (header[0] << 8) | header[1]
    h = (header[2] << 8) | header[3]
    img = Image.new('RGB', (w, h))
    pixels = []
    for i in range(0, len(data), 2):
        word = (data[i] << 8) | data[i + 1]   # big-endian RGB565
        r = ((word >> 11) & 0x1F) << 3
        g = ((word >>  5) & 0x3F) << 2
        b = ( word        & 0x1F) << 3
        pixels.append((r, g, b))
    img.putdata(pixels)
    return img, w, h


def _placeholder(w, h, color, label):
    img = Image.new('RGB', (w, h), color)
    d   = ImageDraw.Draw(img)
    d.rectangle([0, 0, w - 1, h - 1], outline=WHITE)
    lw  = len(label) * 6
    d.text(((w - lw) // 2, h // 2 - 4), label, fill=WHITE)
    return img, w, h


def _image_or_placeholder(filename, fallback_w, fallback_h, placeholder_color, placeholder_label):
    img, w, h = _load_bin(filename)
    if img:
        print(f"  loaded {filename} ({w}x{h})")
        return img, w, h
    print(f"  {filename} not found — using placeholder")
    return _placeholder(fallback_w, fallback_h, placeholder_color, placeholder_label)

# ── scene renderer ────────────────────────────────────────────────────────────

def render_scene(action, bg, trend):
    img  = Image.new('RGB', (DISPLAY_WIDTH, DISPLAY_HEIGHT), BLACK)
    draw = ImageDraw.Draw(img)

    kind, count = _parse_action(action)

    if kind == 'water':
        ph, pw, ph_h = _image_or_placeholder('water.bin', 80, 80, (0, 90, 180), 'WATER')
        img.paste(ph, ((DISPLAY_WIDTH - pw) // 2, (ACTION_H - ph_h) // 2))

    elif kind == 'juicebox':
        ph, pw, ph_h = _image_or_placeholder('juicebox.bin', 80, 80, (200, 120, 0), 'JUICEBOX')
        img.paste(ph, ((DISPLAY_WIDTH - pw) // 2, (ACTION_H - ph_h) // 2))

    elif kind == 'jb':
        ph, pw, ph_h = _image_or_placeholder('jb.bin', 60, 60, (180, 40, 40), 'JB')
        img.paste(ph, ((DISPLAY_WIDTH - pw) // 2, (ACTION_H - ph_h) // 2))
        _draw_custom_text(draw, small_font, f"{count}x", 4, 4, WHITE)

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
