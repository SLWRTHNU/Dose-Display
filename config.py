"""
Configuration file for Nightscout BG Display
"""

# WiFi credentials
WIFI_SSID = "2.4G"
WIFI_PASSWORD = "JohnBerry"

# Nightscout configuration
NIGHTSCOUT_URL = "https://sennaloop-673ad2782247.herokuapp.com"
NIGHTSCOUT_TOKEN = "picodispla-8ec1ec6023f4f936"

# Update interval (seconds)
UPDATE_INTERVAL = 15

# Display layout
BG_ARROW_GAP = 8  # Gap in pixels between BG value and arrow (adjustable)

# Display pins for Waveshare 19579 (ST7735S)
DISPLAY_WIDTH = 160
DISPLAY_HEIGHT = 128
PIN_DC = 8
PIN_CS = 9
PIN_RST = 12
PIN_BL = 13
PIN_SCK = 10
PIN_MOSI = 11

# Blood glucose ranges (mmol/L)
BG_RANGES = {
    'very_low': (0, 4.0),
    'low': (4.1, 4.8),
    'target': (4.9, 7.0),
    'high': (8.0, 10.0),
    'very_high': (11.0, 13.0),
    'critical': (13.1, 30.0)
}

# Trend arrow mappings for custom font
TREND_ARROWS = {
    'DoubleUp': 'OO',
    'SingleUp': 'O',
    'FortyFiveUp': 'L',
    'Flat': 'J',
    'FortyFiveDown': 'N',
    'SingleDown': 'P',
    'DoubleDown': 'PP'
}
