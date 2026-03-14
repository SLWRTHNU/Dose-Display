"""
MicroPython ST7735S display driver for Waveshare 19579 (160x128)
"""
from machine import Pin, SPI
import framebuf
import time

class ST7735:
    def __init__(self, spi, width, height, dc, cs, rst, bl=None):
        self.spi = spi
        self.width = width
        self.height = height
        self.dc = dc
        self.cs = cs
        self.rst = rst
        self.bl = bl
        
        # Display offsets (found through testing)
        self.colstart = 1
        self.rowstart = 2  # Back to 2 to fix colorful static at top
        
        # Initialize pins
        self.dc.init(Pin.OUT)
        self.cs.init(Pin.OUT)
        self.rst.init(Pin.OUT)
        if self.bl:
            self.bl.init(Pin.OUT)
            self.bl.value(1)  # Turn on backlight
        
        # Initialize display
        self.init_display()
        
        # Create framebuffer
        self.buffer = bytearray(self.width * self.height * 2)
        self.fbuf = framebuf.FrameBuffer(self.buffer, self.width, self.height, framebuf.RGB565)
        
    def write_cmd(self, cmd):
        self.cs.value(0)
        self.dc.value(0)
        self.spi.write(bytearray([cmd]))
        self.cs.value(1)
        
    def write_data(self, data):
        self.cs.value(0)
        self.dc.value(1)
        if isinstance(data, int):
            self.spi.write(bytearray([data]))
        else:
            self.spi.write(data)
        self.cs.value(1)
        
    def init_display(self):
        # Hardware reset
        self.rst.value(0)
        time.sleep_ms(100)
        self.rst.value(1)
        time.sleep_ms(100)
        
        # Software reset
        self.write_cmd(0x01)
        time.sleep_ms(150)
        
        # Sleep out
        self.write_cmd(0x11)
        time.sleep_ms(255)
        
        # Pixel format - 16 bit color
        self.write_cmd(0x3A)
        self.write_data(0x05)
        
        # Memory access control (MADCTL) - 0x60 flips vertically from 0xA0
        self.write_cmd(0x36)
        self.write_data(0x60)
        
        # Display on
        self.write_cmd(0x29)
        time.sleep_ms(100)
        
    def set_window(self, x0, y0, x1, y1):
        """Set drawing window"""
        # Add offsets for this specific ST7735S display
        x0 += self.colstart
        x1 += self.colstart
        y0 += self.rowstart
        y1 += self.rowstart
        
        self.write_cmd(0x2A)  # Column address set
        self.write_data(0x00)
        self.write_data(x0)
        self.write_data(0x00)
        self.write_data(x1)
        
        self.write_cmd(0x2B)  # Row address set
        self.write_data(0x00)
        self.write_data(y0)
        self.write_data(0x00)
        self.write_data(y1)
        
        self.write_cmd(0x2C)  # Memory write
    
    def show(self):
        self.set_window(0, 0, self.width - 1, self.height - 1)
        self.cs.value(0)
        self.dc.value(1)
        self.spi.write(self.buffer)
        self.cs.value(1)
        
    def fill(self, color):
        self.fbuf.fill(color)
        
    def pixel(self, x, y, color):
        self.fbuf.pixel(x, y, color)
        
    def text(self, string, x, y, color):
        self.fbuf.text(string, x, y, color)
        
    def line(self, x1, y1, x2, y2, color):
        self.fbuf.line(x1, y1, x2, y2, color)
        
    def rect(self, x, y, w, h, color):
        self.fbuf.rect(x, y, w, h, color)
        
    def fill_rect(self, x, y, w, h, color):
        self.fbuf.fill_rect(x, y, w, h, color)
