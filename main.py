"""
Nightscout Blood Glucose Display for Pico 2 W
"""
import network
import time
import framebuf
import uasyncio as asyncio
from machine import Pin, SPI
from st7735 import ST7735
from config import *
import small_font
import arrows_font


class BGDisplay:
    def __init__(self):
        spi = SPI(1, baudrate=10000000, polarity=1, phase=1,
                  sck=Pin(PIN_SCK), mosi=Pin(PIN_MOSI))
        self.display = ST7735(
            spi=spi, width=DISPLAY_WIDTH, height=DISPLAY_HEIGHT,
            dc=Pin(PIN_DC), cs=Pin(PIN_CS), rst=Pin(PIN_RST), bl=Pin(PIN_BL)
        )

        self.BLACK  = 0x0000
        self.WHITE  = 0xFFFF
        self.RED    = 0xF800
        self.GREEN  = 0x07E0
        self.YELLOW = 0xFFE0
        self.ORANGE = 0xFD20
        self.BLUE   = 0x001F

        self.wlan = network.WLAN(network.STA_IF)

        self.last_bg     = None
        self.last_trend  = None
        self.last_action = None
        self.override    = None  # None or action string
        self.snooze_until = 0   # time.time() + 900 when active
        self.blink_state = False

        self.button = Pin(PIN_BUTTON, Pin.IN, Pin.PULL_UP)
        self._btn_last      = 1
        self._btn_last_time = 0

        self._img_water,    self._w_water,    self._h_water    = self._load_image('water.bin')
        self._img_jb,       self._w_jb,       self._h_jb       = self._load_image('jb.bin')
        self._img_juicebox, self._w_juicebox, self._h_juicebox = self._load_image('juicebox.bin')

    # ── Image loading ───────────────────────────────────────────────────────

    def _load_image(self, filename):
        """Load a raw RGB565 .bin with 4-byte header (W, H). Returns (FrameBuffer, w, h)."""
        try:
            with open(filename, 'rb') as f:
                header = f.read(4)
                data   = bytearray(f.read())
            w = (header[0] << 8) | header[1]
            h = (header[2] << 8) | header[3]
            return framebuf.FrameBuffer(data, w, h, framebuf.RGB565), w, h
        except Exception as e:
            print(f"Image load error ({filename}): {e}")
            return None, 0, 0

    # ── Button ──────────────────────────────────────────────────────────────

    def check_button(self):
        """Return True once on button press (falling edge), 500 ms debounce."""
        val = self.button.value()
        now = time.ticks_ms()
        pressed = (self._btn_last == 1 and val == 0 and
                   time.ticks_diff(now, self._btn_last_time) > 500)
        if val != self._btn_last:
            self._btn_last      = val
            self._btn_last_time = now
        return pressed

    # ── WiFi ────────────────────────────────────────────────────────────────

    def connect_wifi(self):
        self.wlan.active(True)
        if self.wlan.isconnected():
            return True
        self.show_message("Connecting\nto WiFi...", self.BLUE)
        self.wlan.connect(WIFI_SSID, WIFI_PASSWORD)
        for _ in range(20):
            if self.wlan.isconnected():
                break
            time.sleep(1)
        if self.wlan.isconnected():
            try:
                import ntptime
                ntptime.settime()
                print("NTP synced")
            except Exception as e:
                print(f"NTP sync failed: {e}")
            self.show_message("Connected!", self.GREEN)
            time.sleep(1)
            return True
        self.show_message("WiFi Failed!", self.RED)
        return False

    def ensure_wifi(self):
        """Silently reconnect if WiFi dropped. Returns True if connected."""
        if self.wlan.isconnected():
            return True
        print("WiFi lost, reconnecting...")
        self.wlan.disconnect()
        time.sleep(1)
        self.wlan.connect(WIFI_SSID, WIFI_PASSWORD)
        for _ in range(20):
            if self.wlan.isconnected():
                print("WiFi reconnected")
                return True
            time.sleep(1)
        print("WiFi reconnect failed")
        return False

    # ── Chart logic ─────────────────────────────────────────────────────────

    def get_bg_range(self, bg):
        if bg <= 4.0:    return 'very_low'
        elif bg <= 4.8:  return 'low'
        elif bg <= 7.0:  return 'target'
        elif bg <= 10.0: return 'high'
        elif bg <= 13.0: return 'very_high'
        else:            return 'critical'

    def get_trend_cat(self, trend):
        return {
            'DoubleUp':      'rising_rapidly',
            'SingleUp':      'rising',
            'FortyFiveUp':   'slow_rise',
            'Flat':          'stable',
            'FortyFiveDown': 'slow_fall',
            'SingleDown':    'falling_rapidly',
            'DoubleDown':    'falling_very_rapidly',
        }.get(trend, 'stable')

    def get_chart_action(self, bg, trend):
        """Return action string, or '' for blank (no action needed)."""
        key = (self.get_trend_cat(trend), self.get_bg_range(bg))
        return {
            # Rising rapidly (>1.7 mmol/L delta)
            ('rising_rapidly', 'very_low'):  '',
            ('rising_rapidly', 'low'):       '',
            ('rising_rapidly', 'target'):    '',
            ('rising_rapidly', 'high'):      '',
            ('rising_rapidly', 'very_high'): 'Water',
            ('rising_rapidly', 'critical'):  'Water',

            # Rising (1.0–1.7 mmol/L delta)
            ('rising', 'very_low'):  'Give 2 JB',
            ('rising', 'low'):       '',
            ('rising', 'target'):    '',
            ('rising', 'high'):      '',
            ('rising', 'very_high'): 'Water',
            ('rising', 'critical'):  'Water',

            # Slow rise (0.6–1.1 mmol/L delta)
            ('slow_rise', 'very_low'):  'Give 2 JB',
            ('slow_rise', 'low'):       '',
            ('slow_rise', 'target'):    '',
            ('slow_rise', 'high'):      '',
            ('slow_rise', 'very_high'): 'Water',
            ('slow_rise', 'critical'):  'Water',

            # Stable
            ('stable', 'very_low'):  'Give 3 JB',
            ('stable', 'low'):       'Give 2 JB',
            ('stable', 'target'):    '',
            ('stable', 'high'):      '',
            ('stable', 'very_high'): '',
            ('stable', 'critical'):  '',

            # Slow fall (0.6–1.1 mmol/L delta)
            ('slow_fall', 'very_low'):  'Give 4 JB',
            ('slow_fall', 'low'):       'Give 2 JB',
            ('slow_fall', 'target'):    '',
            ('slow_fall', 'high'):      '',
            ('slow_fall', 'very_high'): '',
            ('slow_fall', 'critical'):  '',

            # Falling rapidly (1.1–1.7 mmol/L delta)
            ('falling_rapidly', 'very_low'):  'Juicebox',
            ('falling_rapidly', 'low'):       'Give 4 JB',
            ('falling_rapidly', 'target'):    'Give 2 JB',
            ('falling_rapidly', 'high'):      '',
            ('falling_rapidly', 'very_high'): '',
            ('falling_rapidly', 'critical'):  '',

            # Falling very rapidly (>1.7 mmol/L delta)
            ('falling_very_rapidly', 'very_low'):  'Juicebox',
            ('falling_very_rapidly', 'low'):       'Give 5 JB',
            ('falling_very_rapidly', 'target'):    'Give 3 JB',
            ('falling_very_rapidly', 'high'):      '',
            ('falling_very_rapidly', 'very_high'): '',
            ('falling_very_rapidly', 'critical'):  '',
        }.get(key, '')

    # ── Nightscout write ────────────────────────────────────────────────────

    def post_note(self, note):
        """POST a Note treatment to Nightscout with the current UTC time."""
        try:
            t  = time.localtime()
            ts = (f"{t[0]:04d}-{t[1]:02d}-{t[2]:02d}T"
                  f"{t[3]:02d}:{t[4]:02d}:{t[5]:02d}.000Z")
            body = (f'{{"eventType":"Note","notes":"{note}",'
                    f'"created_at":"{ts}"}}')
            r = urequests.post(
                f"{NIGHTSCOUT_URL}/api/v1/treatments?token={NIGHTSCOUT_TOKEN}",
                headers={"Content-Type": "application/json"},
                data=body,
            )
            print(f"Note posted ({r.status_code}): {note}")
            r.close()
            return r.status_code in (200, 201)
        except Exception as e:
            print(f"Note post error: {e}")
            return False

    # ── HTTP helpers (ported from Iris Mini) ────────────────────────────────

    @staticmethod
    def _find_int_after(s, key, start=0):
        i = s.find(key, start)
        if i < 0: return None, -1
        i += len(key)
        while i < len(s) and s[i] in ' \t\r\n': i += 1
        j = i
        if j < len(s) and s[j] == '-': j += 1
        while j < len(s) and s[j].isdigit(): j += 1
        if j == i or (j == i + 1 and s[i] == '-'): return None, -1
        return int(s[i:j]), j

    @staticmethod
    def _find_str_after(s, key, start=0):
        i = s.find(key, start)
        if i < 0: return None, -1
        i += len(key)
        while i < len(s) and s[i] in ' \t\r\n': i += 1
        q1 = s.find('"', i)
        if q1 < 0: return None, -1
        q2 = s.find('"', q1 + 1)
        if q2 < 0: return None, -1
        return s[q1 + 1:q2], q2 + 1

    def _http_get(self, url, max_body=2048):
        """Raw socket HTTP/HTTPS GET. Returns body bytes or None."""
        import usocket, ssl, gc
        gc.collect()
        if url.startswith('https://'):
            scheme, rest, port = 'https', url[8:], 443
        elif url.startswith('http://'):
            scheme, rest, port = 'http', url[7:], 80
        else:
            return None
        slash = rest.find('/')
        if slash >= 0:
            hostport, path = rest[:slash], rest[slash:]
        else:
            hostport, path = rest, '/'
        if ':' in hostport:
            h, p = hostport.split(':', 1); port = int(p)
        else:
            h = hostport
        s = None
        try:
            addr = usocket.getaddrinfo(h, port)[0][-1]
            s = usocket.socket()
            s.settimeout(5)
            s.connect(addr)
            if scheme == 'https':
                s = ssl.wrap_socket(s, server_hostname=h)
            s.send(('GET {} HTTP/1.1\r\nHost: {}\r\nConnection: close\r\n\r\n'
                    .format(path, h)).encode('utf-8'))
            buf = bytearray()
            CAP = max_body + 512
            t0 = time.ticks_ms()
            while time.ticks_diff(time.ticks_ms(), t0) < 3000:
                try:
                    chunk = s.recv(256)
                except OSError:
                    break
                if not chunk: break
                take = min(len(chunk), CAP - len(buf))
                if take <= 0: break
                buf.extend(chunk[:take])
        except Exception as e:
            print(f'HTTP error: {e}')
            return None
        finally:
            try:
                if s: s.close()
            except: pass
        raw = bytes(buf)
        sep = raw.find(b'\r\n\r\n')
        if sep < 0: return None
        head = raw[:sep].decode('utf-8', 'ignore')
        body = raw[sep + 4: sep + 4 + max_body]
        try:
            status = int(head.split('\r\n', 1)[0].split(' ')[1])
        except: return None
        if status in (301, 302, 303, 307, 308):
            for line in head.split('\r\n'):
                if line.lower().startswith('location:'):
                    return self._http_get(line.split(':', 1)[1].strip(), max_body)
            return None
        return body if status == 200 else None

    # ── Nightscout read ──────────────────────────────────────────────────────

    def fetch_bg(self):
        """Fetch latest BG entry. Returns (bg_mmol, trend) or (None, None) on error."""
        if not self.ensure_wifi():
            return None, None
        body = self._http_get(
            '{}/api/v1/entries.json?count=1&token={}'.format(NIGHTSCOUT_URL, NIGHTSCOUT_TOKEN))
        if not body:
            return None, None
        try:
            txt = body.decode('utf-8', 'ignore')
            sgv, _ = self._find_int_after(txt, '"sgv":')
            if sgv is None:
                return None, None
            direction, _ = self._find_str_after(txt, '"direction":')
            return sgv / 18.0, direction or 'Flat'
        except Exception as e:
            print(f'BG parse error: {e}')
            return None, None

    def fetch_treatments(self):
        """Fetch latest ACTION: override from treatments. Updates self.override in place."""
        if not self.ensure_wifi():
            return
        body = self._http_get(
            '{}/api/v1/treatments.json?count=15&token={}'.format(NIGHTSCOUT_URL, NIGHTSCOUT_TOKEN),
            max_body=4096)
        if not body:
            return
        try:
            txt = body.decode('utf-8', 'ignore')
            pos = 0
            while True:
                notes, p1 = self._find_str_after(txt, '"notes":', pos)
                note,  p2 = self._find_str_after(txt, '"note":', pos)
                if notes is not None and (note is None or p1 <= p2):
                    val_str, pos = notes, p1
                elif note is not None:
                    val_str, pos = note, p2
                else:
                    break
                if val_str.upper().startswith('ACTION:'):
                    val = val_str[7:].strip()
                    self.override = None if val.upper() == 'OFF' else val
                    return
        except Exception as e:
            print(f'Treatment parse error: {e}')

    # ── Drawing ─────────────────────────────────────────────────────────────

    # ── Action image rendering ──────────────────────────────────────────────

    def _parse_action(self, action):
        """Return ('water', 0), ('jb', N), or ('none', 0)."""
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

    ACTION_H = 95  # pixels available above BG text row

    def _draw_action(self, action):
        """Render the action area (y=0..ACTION_H-1) with an image or nothing."""
        kind, count = self._parse_action(action)

        if kind == 'water' and self._img_water:
            x = (DISPLAY_WIDTH     - self._w_water)    // 2
            y = (self.ACTION_H     - self._h_water)    // 2
            self.display.fbuf.blit(self._img_water, x, y)

        elif kind == 'juicebox' and self._img_juicebox:
            x = (DISPLAY_WIDTH     - self._w_juicebox) // 2
            y = (self.ACTION_H     - self._h_juicebox) // 2
            self.display.fbuf.blit(self._img_juicebox, x, y)

        elif kind == 'jb' and self._img_jb:
            JB_GAP   = 8
            FONT_H   = 20
            count_str = f"{count}x"
            txt_w = sum(small_font.get_ch(c)[2] + 1 for c in count_str) - 1
            total_w = txt_w + JB_GAP + self._w_jb
            x0    = (DISPLAY_WIDTH - total_w) // 2
            img_y = (self.ACTION_H - self._h_jb) // 2
            txt_y = img_y + (self._h_jb - FONT_H) // 2
            self.draw_custom_text(small_font, count_str, x0, txt_y, self.WHITE)
            self.display.fbuf.blit(self._img_jb, x0 + txt_w + JB_GAP, img_y)

    def draw_text_2x(self, text, x, y, color):
        """
        Render built-in 8×8 font at 2× scale (each pixel becomes a 2×2 block).
        Result: 16 px tall, 16 px wide per character.
        """
        w   = len(text) * 8
        tmp = bytearray(w * 8 * 2)
        fb  = framebuf.FrameBuffer(tmp, w, 8, framebuf.RGB565)
        fb.fill(0)
        fb.text(text, 0, 0, 0xFFFF)
        for py in range(8):
            for px in range(w):
                if fb.pixel(px, py):
                    dx, dy = x + px * 2, y + py * 2
                    self.display.pixel(dx,   dy,   color)
                    self.display.pixel(dx+1, dy,   color)
                    self.display.pixel(dx,   dy+1, color)
                    self.display.pixel(dx+1, dy+1, color)

    def draw_custom_text(self, font_mod, text, x, y, color):
        """Render text with a font_to_py-generated font module."""
        cx = x
        for ch in text:
            glyph, h, w = font_mod.get_ch(ch)
            for row in range(h):
                for col in range(w):
                    bi = row * ((w - 1) // 8 + 1) + col // 8
                    if bi < len(glyph) and (glyph[bi] >> (7 - col % 8)) & 1:
                        self.display.pixel(cx + col, y + row, color)
            cx += w + 1
        return cx - x

    def show_message(self, msg, color=None):
        if color is None:
            color = self.WHITE
        self.display.fill(self.BLACK)
        lines = msg.split('\n')
        y0    = DISPLAY_HEIGHT // 2 - len(lines) * 6
        for i, ln in enumerate(lines):
            self.display.text(ln, max(0, DISPLAY_WIDTH // 2 - len(ln) * 4),
                              y0 + i * 12, color)
        self.display.show()

    def render(self, bg, trend, action, dot_color):
        """Full frame draw: action area + BG/arrow + blink dot."""
        self.display.fill(self.BLACK)

        # ── Action (upper area: y=0..88) ─────────────────────────────────────
        self._draw_action(action)

        # ── BG value + trend arrow (bottom strip) ────────────────────────────
        bg_text = f"{bg:.1f}"
        arrow   = TREND_ARROWS.get(trend, 'J')

        bg_w  = sum(small_font.get_ch(c)[2] + 1 for c in bg_text) - 1
        arr_w = 0
        for c in arrow:
            try:
                arr_w += arrows_font.get_ch(c)[2] + 1
            except Exception:
                pass
        if arr_w:
            arr_w -= 1

        total_w = bg_w + BG_ARROW_GAP + arr_w
        sx      = (DISPLAY_WIDTH - total_w) // 2
        self.draw_custom_text(small_font,  bg_text, sx,                          95, self.WHITE)
        self.draw_custom_text(arrows_font, arrow,   sx + bg_w + BG_ARROW_GAP,   95, self.WHITE)

        # ── Blink dot (top-right corner) ─────────────────────────────────────
        #   WHITE  = normal chart mode
        #   BLUE   = snoozed (teacher pressed button)
        #   ORANGE = remote override active
        if self.blink_state:
            self.display.fill_rect(DISPLAY_WIDTH - 5, 2, 3, 3, dot_color)

        self.display.show()

    # ── Render helper ────────────────────────────────────────────────────────

    def _do_render(self):
        if self.last_bg is None:
            self.show_message("Waiting for\ndata...", self.YELLOW)
        elif self.override:
            self.render(self.last_bg, self.last_trend, self.override, self.ORANGE)
        elif time.time() < self.snooze_until:
            self.render(self.last_bg, self.last_trend, '', self.BLUE)
        else:
            self.render(self.last_bg, self.last_trend, self.last_action, self.WHITE)

    # ── Async tasks ──────────────────────────────────────────────────────────

    async def _task_fetch_bg(self):
        """Fetch BG every 5 s (matches Iris Mini poll rate)."""
        while True:
            try:
                bg, trend = self.fetch_bg()
                if bg is not None:
                    self.last_bg     = bg
                    self.last_trend  = trend
                    self.last_action = self.get_chart_action(bg, trend)
                    self._do_render()
                    print(f"BG:{bg:.1f} Trend:{trend} "
                          f"Action:{self.last_action!r} Override:{self.override!r}")
            except Exception as e:
                print(f"BG task error: {e}")
            await asyncio.sleep_ms(5000)

    async def _task_fetch_treatments(self):
        """Fetch override treatments every 5 min."""
        while True:
            try:
                self.fetch_treatments()
            except Exception as e:
                print(f"Treatment task error: {e}")
            await asyncio.sleep_ms(300_000)

    async def _task_blink(self):
        """Toggle blink dot every 500 ms."""
        while True:
            self.blink_state = not self.blink_state
            self._do_render()
            await asyncio.sleep_ms(500)

    async def _task_button(self):
        """Poll action button every 50 ms."""
        while True:
            try:
                if self.check_button():
                    note = ("Actioned: " + self.last_action
                            if self.last_action else "Actioned")
                    self.show_message("Actioned!", self.GREEN)
                    self.post_note(note)
                    await asyncio.sleep_ms(1000)
                    self.snooze_until = time.time() + 900
                    self.override     = None
                    print(f"Snooze activated (15 min), note: {note!r}")
                    self._do_render()
            except Exception as e:
                print(f"Button task error: {e}")
            await asyncio.sleep_ms(50)

    async def _async_main(self):
        asyncio.create_task(self._task_fetch_bg())
        asyncio.create_task(self._task_fetch_treatments())
        asyncio.create_task(self._task_blink())
        asyncio.create_task(self._task_button())
        while True:
            await asyncio.sleep(60)

    # ── Entry point ──────────────────────────────────────────────────────────

    def run(self):
        self.show_message("BG Display\nStarting...", self.BLUE)
        time.sleep(1)
        if not self.connect_wifi():
            self.show_message("Check WiFi\nSettings", self.RED)
            return
        self.show_message("Waiting for\ndata...", self.YELLOW)
        asyncio.run(self._async_main())


if __name__ == "__main__":
    try:
        BGDisplay().run()
    except KeyboardInterrupt:
        print("Stopped")
    except Exception as e:
        print(f"Fatal: {e}")
