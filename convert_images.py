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


def to_rgb565_bin(input_path, output_path, size):
    img = Image.open(input_path).convert('RGB').resize(size, Image.LANCZOS)
    out = bytearray()
    for y in range(size[1]):
        for x in range(size[0]):
            r, g, b = img.getpixel((x, y))
            pixel = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
            out += struct.pack('>H', pixel)  # big-endian, matches framebuf.RGB565
    with open(output_path, 'wb') as f:
        f.write(out)
    print(f"  {output_path}: {size[0]}x{size[1]} px = {len(out)} bytes")


print("Converting images...")
to_rgb565_bin('water.png',    'water.bin',    (80, 80))
to_rgb565_bin('jb.png',       'jb.bin',       (40, 40))
to_rgb565_bin('juicebox.png', 'juicebox.bin', (80, 80))
print("Done. Copy water.bin, jb.bin, and juicebox.bin to the Pico.")
