#!/usr/bin/env python3
"""
Convert water.png, jb.png, and juicebox.png to raw RGB565 .bin files for the ST7735 display.

Usage:
    pip install Pillow
    python convert_images.py

Place water.png, jb.png, and juicebox.png in the same folder before running.
Then copy the .bin files to the Pico:
    mpremote cp water.bin    :water.bin
    mpremote cp jb.bin       :jb.bin
    mpremote cp juicebox.bin :juicebox.bin
"""
import struct
from PIL import Image


ACTION_W = 160   # display width
ACTION_H = 95    # pixels above the BG text row (y=0..94)


def to_rgb565_bin(input_path, output_path, max_w, max_h):
    img = Image.open(input_path).convert('RGB')
    img.thumbnail((max_w, max_h), Image.LANCZOS)   # preserves aspect ratio
    w, h = img.size
    out = bytearray()
    out += struct.pack('>HH', w, h)                 # 4-byte header: width, height
    for py in range(h):
        for px in range(w):
            r, g, b = img.getpixel((px, py))
            pixel = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
            out += struct.pack('>H', pixel)          # big-endian RGB565
    with open(output_path, 'wb') as f:
        f.write(out)
    print(f"  {output_path}: {w}x{h} px = {len(out)} bytes")


print("Converting images...")
to_rgb565_bin('water.png',    'water.bin',    ACTION_W, ACTION_H)
to_rgb565_bin('jb.png',       'jb.bin',       ACTION_W, ACTION_H)
to_rgb565_bin('juicebox.png', 'juicebox.bin', ACTION_W, ACTION_H)
print("Done. Copy water.bin, jb.bin, and juicebox.bin to the Pico.")
