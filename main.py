"""
Nightscout Blood Glucose Display for Pico 2 W
Displays BG value, trend, and recommended action based on management chart
"""
import network
import urequests
import time
import machine
from machine import Pin, SPI
from st7735 import ST7735
from config import *
import framebuf

# Import custom fonts
import small_font
import arrows_font

# Import unicorn image
try:
    from unicorn_image import UNICORN_WIDTH, UNICORN_HEIGHT, UNICORN_DATA
    UNICORN_IMAGE_AVAILABLE = True
except ImportError:
    UNICORN_IMAGE_AVAILABLE = False
    print("Warning: unicorn_image.py not found, will use text fallback")

class BGDisplay:
    def __init__(self):
        # Initialize display
        print("Initializing display...")
        spi = SPI(1, baudrate=10000000, polarity=1, phase=1,
                  sck=Pin(PIN_SCK), mosi=Pin(PIN_MOSI))
        
        self.display = ST7735(
            spi=spi,
            width=DISPLAY_WIDTH,
            height=DISPLAY_HEIGHT,
            dc=Pin(PIN_DC),
            cs=Pin(PIN_CS),
            rst=Pin(PIN_RST),
            bl=Pin(PIN_BL)
        )
        
        # Colors (RGB565)
        self.BLACK = 0x0000
        self.WHITE = 0xFFFF
        self.RED = 0xF800
        self.GREEN = 0x07E0
        self.BLUE = 0x001F
        self.YELLOW = 0xFFE0
        self.ORANGE = 0xFD20
        
        # WiFi
        self.wlan = network.WLAN(network.STA_IF)
        
        # State
        self.last_bg = None
        self.last_trend = None
        self.last_action = None
        self.blink_state = False  # For "sign of life" indicator
        self.blink_state = False  # For "sign of life" indicator
        
    def draw_custom_char(self, font_module, char, x, y, color):
        """Draw a single character using custom font"""
        glyph, height, width = font_module.get_ch(char)
        
        # Draw the glyph
        for row in range(height):
            for col in range(width):
                byte_index = row * ((width - 1) // 8 + 1) + col // 8
                bit_index = 7 - (col % 8)
                if byte_index < len(glyph) and (glyph[byte_index] >> bit_index) & 1:
                    self.display.pixel(x + col, y + row, color)
    
    def draw_custom_text(self, font_module, text, x, y, color):
        """Draw text using custom font"""
        cursor_x = x
        for char in text:
            glyph, height, width = font_module.get_ch(char)
            self.draw_custom_char(font_module, char, cursor_x, y, color)
            cursor_x += width + 1  # Add 1 pixel spacing between characters
        return cursor_x - x  # Return total width
    
    def draw_unicorn_image(self):
        """Draw the unicorn image in the action area"""
        if not UNICORN_IMAGE_AVAILABLE:
            # Fallback to text
            self.display.text("Unicorn", 50, 40, self.GREEN)
            return
        
        # Center the image horizontally
        x_offset = (DISPLAY_WIDTH - UNICORN_WIDTH) // 2
        y_offset = 5  # Small margin from top
        
        # Create a framebuffer from the image data
        import framebuf
        img_fb = framebuf.FrameBuffer(bytearray(UNICORN_DATA), UNICORN_WIDTH, UNICORN_HEIGHT, framebuf.RGB565)
        
        # Blit the image to the display framebuffer
        self.display.fbuf.blit(img_fb, x_offset, y_offset)
    
    def connect_wifi(self):
        """Connect to WiFi"""
        self.wlan.active(True)
        
        if not self.wlan.isconnected():
            print(f"Connecting to WiFi: {WIFI_SSID}...")
            self.show_message("Connecting\nto WiFi...", self.BLUE)
            
            self.wlan.connect(WIFI_SSID, WIFI_PASSWORD)
            
            # Wait for connection
            max_wait = 10
            while max_wait > 0:
                if self.wlan.isconnected():
                    break
                max_wait -= 1
                print("Waiting for connection...")
                time.sleep(1)
            
            if self.wlan.isconnected():
                print(f"Connected! IP: {self.wlan.ifconfig()[0]}")
                self.show_message(f"Connected!\n{self.wlan.ifconfig()[0]}", self.GREEN)
                time.sleep(2)
                return True
            else:
                print("Connection failed!")
                self.show_message("WiFi Failed!", self.RED)
                return False
        return True
    
    def get_bg_range(self, bg_value):
        """Determine which BG range the value falls into"""
        if bg_value <= 4.0:
            return 'very_low'
        elif bg_value <= 4.8:
            return 'low'
        elif bg_value <= 7.0:
            return 'target'
        elif bg_value <= 10.0:
            return 'high'
        elif bg_value <= 13.0:
            return 'very_high'
        else:
            return 'critical'
    
    def get_trend_category(self, trend_direction):
        """Categorize trend into rate of change categories"""
        trend_map = {
            'DoubleUp': 'rising_rapidly',      # >1.7 mmol
            'SingleUp': 'rising',              # 1-1.7 mmol
            'FortyFiveUp': 'slow_rise',        # 0.6-1.1 mmol
            'Flat': 'stable',
            'FortyFiveDown': 'slow_fall',      # 0.6-1.1 mmol
            'SingleDown': 'falling_rapidly',   # 1.1-1.7 mmol
            'DoubleDown': 'falling_very_rapidly'  # >1.7 mmol
        }
        return trend_map.get(trend_direction, 'stable')
    
    def get_action(self, bg_value, trend_direction):
        """Determine action based on BG value and trend from the chart"""
        bg_range = self.get_bg_range(bg_value)
        trend_cat = self.get_trend_category(trend_direction)
        
        # Decision matrix from the chart
        actions = {
            ('rising_rapidly', 'very_low'): 'Monitor',
            ('rising_rapidly', 'low'): '',
            ('rising_rapidly', 'target'): '',
            ('rising_rapidly', 'high'): 'Monitor',
            ('rising_rapidly', 'very_high'): 'Monitor\nWater ++',
            ('rising_rapidly', 'critical'): 'Monitor\nBolus >16\nWater ++',
            
            ('rising', 'very_low'): 'Give 2g\nMonitor',
            ('rising', 'low'): '',
            ('rising', 'target'): '',
            ('rising', 'high'): 'Monitor',
            ('rising', 'very_high'): 'Monitor\nWater +',
            ('rising', 'critical'): 'Monitor\nBolus >16\nWater ++',
            
            ('slow_rise', 'very_low'): 'Give 2g\nMonitor',
            ('slow_rise', 'low'): 'Monitor',
            ('slow_rise', 'target'): '',
            ('slow_rise', 'high'): '',
            ('slow_rise', 'very_high'): 'Monitor\nWater +',
            ('slow_rise', 'critical'): 'Monitor\nBolus >16\nWater +',
            
            ('stable', 'very_low'): 'Give 3g\nMonitor',
            ('stable', 'low'): 'Give 2g\nMonitor',
            ('stable', 'target'): 'Unicorn',
            ('stable', 'high'): 'Unicorn',
            ('stable', 'very_high'): 'Monitor',
            ('stable', 'critical'): 'Monitor',
            
            ('slow_fall', 'very_low'): 'Give 4g\nMonitor',
            ('slow_fall', 'low'): 'Give 2g\nMonitor',
            ('slow_fall', 'target'): 'Monitor',
            ('slow_fall', 'high'): '',
            ('slow_fall', 'very_high'): '',
            ('slow_fall', 'critical'): '',
            
            ('falling_rapidly', 'very_low'): 'Fast snack 8g+\n(applesauce,\nhoney, juice)',
            ('falling_rapidly', 'low'): 'Give 4g\nMonitor',
            ('falling_rapidly', 'target'): 'Give 2g\nMonitor',
            ('falling_rapidly', 'high'): '',
            ('falling_rapidly', 'very_high'): '',
            ('falling_rapidly', 'critical'): '',
            
            ('falling_very_rapidly', 'very_low'): 'Fast snack 8g+\n(applesauce,\nhoney, juice)',
            ('falling_very_rapidly', 'low'): 'Give 4-6g\nMonitor',
            ('falling_very_rapidly', 'target'): 'Give 2-4g\nMonitor',
            ('falling_very_rapidly', 'high'): 'Monitor',
            ('falling_very_rapidly', 'very_high'): 'Monitor',
            ('falling_very_rapidly', 'critical'): '',
        }
        
        key = (trend_cat, bg_range)
        return actions.get(key, 'Monitor')
    
    def get_action_color(self, action):
        """Get color based on action urgency"""
        if not action or action == 'Unicorn':
            return self.GREEN
        elif 'Fast snack' in action:
            return self.RED
        elif 'Give 4' in action or 'Give 3' in action:
            return self.ORANGE
        elif 'Bolus' in action:
            return self.RED
        elif 'Give 2' in action:
            return self.YELLOW
        else:
            return self.WHITE
    
    def fetch_nightscout_data(self):
        """Fetch latest BG data from Nightscout"""
        try:
            url = f"{NIGHTSCOUT_URL}/api/v1/entries.json?count=1&token={NIGHTSCOUT_TOKEN}"
            print(f"Fetching from: {url}")
            
            response = urequests.get(url)
            data = response.json()
            response.close()
            
            if data and len(data) > 0:
                entry = data[0]
                bg_value = entry['sgv'] / 18.0  # Convert mg/dL to mmol/L
                trend = entry.get('direction', 'Flat')
                
                print(f"BG: {bg_value:.1f} mmol/L, Trend: {trend}")
                return bg_value, trend
            else:
                print("No data received")
                return None, None
                
        except Exception as e:
            print(f"Error fetching data: {e}")
            return None, None
    
    def show_message(self, message, color=None):
        """Display a simple centered message"""
        if color is None:
            color = self.WHITE
            
        self.display.fill(self.BLACK)
        
        # Split message into lines
        lines = message.split('\n')
        y_start = (DISPLAY_HEIGHT // 2) - (len(lines) * 6)
        
        for i, line in enumerate(lines):
            x = (DISPLAY_WIDTH // 2) - (len(line) * 4)
            y = y_start + (i * 12)
            self.display.text(line, x, y, color)
        
        self.display.show()
    
    def draw_text_centered(self, text, y, color, scale=1):
        """Draw text centered horizontally at given y position"""
        x = (DISPLAY_WIDTH // 2) - (len(text) * 4 * scale)
        self.display.text(text, max(0, x), y, color)
    
    def show_bg_data(self, bg_value, trend, action):
        """Display BG value, trend, and action"""
        self.display.fill(self.BLACK)
        
        # Determine action color
        action_color = self.get_action_color(action)
        
        # Display action in center (large area)
        if action == 'Unicorn':
            # Draw unicorn image
            self.draw_unicorn_image()
        elif action:
            # Draw text for other actions
            action_lines = action.split('\n')
            y_start = 15  # Move up slightly
            
            for i, line in enumerate(action_lines):
                # Center each line
                x = (DISPLAY_WIDTH // 2) - (len(line) * 4)
                y = y_start + (i * 12)
                self.display.text(line, max(2, x), y, action_color)
        
        # Display BG value and arrow side-by-side at bottom
        bg_text = f"{bg_value:.1f}"
        trend_arrow = TREND_ARROWS.get(trend, 'J')  # Default to Flat if unknown
        
        # Calculate width of BG text
        bg_width = 0
        for char in bg_text:
            _, _, width = small_font.get_ch(char)
            bg_width += width + 1
        bg_width -= 1  # Remove trailing spacing
        
        # Calculate width of arrow text
        arrow_width = 0
        for char in trend_arrow:
            try:
                _, _, width = arrows_font.get_ch(char)
                arrow_width += width + 1
            except Exception as e:
                print(f"Error getting arrow char '{char}': {e}")
        arrow_width -= 1  # Remove trailing spacing
        
        # Gap between BG and arrow (adjustable in config.py)
        gap = BG_ARROW_GAP
        
        # Calculate total width and center position
        total_width = bg_width + gap + arrow_width
        start_x = (DISPLAY_WIDTH // 2) - (total_width // 2)
        
        # Y position for both (aligned on same line)
        y_position = 95  # Moved up from 102
        
        # Draw BG value
        self.draw_custom_text(small_font, bg_text, start_x, y_position, self.WHITE)
        
        # Draw arrow to the right of BG
        arrow_x = start_x + bg_width + gap
        print(f"BG: {bg_text} at x={start_x}, Arrow: {trend_arrow} at x={arrow_x}, y={y_position}")
        self.draw_custom_text(arrows_font, trend_arrow, arrow_x, y_position, self.WHITE)
        
        # Draw "sign of life" indicator - small blinking dot in top right corner
        if self.blink_state:
            self.display.fill_rect(DISPLAY_WIDTH - 5, 2, 3, 3, self.WHITE)
        
        self.display.show()
    
    def run(self):
        """Main loop"""
        print("Starting BG Display...")
        self.show_message("BG Display\nStarting...", self.BLUE)
        time.sleep(1)
        
        # Connect to WiFi
        if not self.connect_wifi():
            self.show_message("Check WiFi\nSettings", self.RED)
            return
        
        # Initialize blink state
        self.blink_state = False
        
        # Counter for timing - start at 149 so first loop iteration triggers fetch
        loop_counter = 149
        
        # Main loop
        while True:
            try:
                need_redraw = False
                loop_counter += 1
                
                # Fetch data every 150 iterations (150 * 0.1s = 15 seconds)
                if loop_counter % 150 == 0:
                    bg_value, trend = self.fetch_nightscout_data()
                    
                    if bg_value is not None and trend is not None:
                        # Get recommended action
                        action = self.get_action(bg_value, trend)
                        
                        # Store state
                        self.last_bg = bg_value
                        self.last_trend = trend
                        self.last_action = action
                        need_redraw = True
                    else:
                        print("No data available")
                        if self.last_bg is None:
                            self.show_message("Waiting for\ndata...", self.YELLOW)
                            time.sleep(1)
                            continue
                
                # Toggle blink state every 5 iterations (5 * 0.1s = 0.5 second)
                if loop_counter % 5 == 0:
                    self.blink_state = not self.blink_state
                    need_redraw = True
                    print(f"Blink: {self.blink_state}")
                
                # Update display only when needed
                if need_redraw and self.last_bg is not None:
                    self.show_bg_data(self.last_bg, self.last_trend, self.last_action)
                
            except Exception as e:
                print(f"Error in main loop: {e}")
                self.show_message("Error!", self.RED)
            
            # Wait before next loop iteration
            time.sleep(0.1)

# Main entry point
if __name__ == "__main__":
    try:
        display = BGDisplay()
        display.run()
    except KeyboardInterrupt:
        print("\nStopped by user")
    except Exception as e:
        print(f"Fatal error: {e}")
