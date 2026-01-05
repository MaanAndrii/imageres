"""
Watermarker Pro v7.0.1 - Configuration Module
============================================
Centralized configuration and constants
"""

import os
from pathlib import Path

# === APPLICATION INFO ===
APP_VERSION = "7.0.1"
APP_NAME = "Watermarker Pro"
APP_AUTHOR = "Marynyuk Andriy"
APP_LICENSE = "Proprietary"
APP_REPO = "https://github.com/MaanAndrii"

# === FILE SETTINGS ===
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MB
MAX_FILENAME_LENGTH = 255
# Додано .pdf до списку підтримуваних форматів
SUPPORTED_INPUT_FORMATS = ['.jpg', '.jpeg', '.png', '.webp', '.pdf']
SUPPORTED_OUTPUT_FORMATS = ['JPEG', 'WEBP', 'PNG']

# === PDF SETTINGS ===
PDF_CONVERSION_DPI = 200  # Якість рендеру сторінок PDF у зображення

# === IMAGE PROCESSING ===
MAX_IMAGE_DIMENSION = 10000  # Maximum width or height
MIN_IMAGE_DIMENSION = 10
THUMBNAIL_SIZE = (300, 300)
PROXY_IMAGE_WIDTH = 700

# === WATERMARK ===
MIN_WATERMARK_SCALE = 5
MAX_WATERMARK_SCALE = 100
MIN_OPACITY = 0.1
MAX_OPACITY = 1.0
DEFAULT_TEXT_SIZE_PT = 100

# === ASPECT RATIOS ===
ASPECT_RATIOS = {
    "Free / Вільний": None,
    "1:1 (Square)": (1, 1),
    "3:2": (3, 2),
    "4:3": (4, 3),
    "5:4": (5, 4),
    "16:9": (16, 9),
    "9:16": (9, 16)
}

# === DEFAULT SETTINGS ===
DEFAULT_SETTINGS = {
    'resize_val': 1920,
    'wm_pos': 'bottom-right',
    'wm_scale': 15,
    'wm_opacity': 1.0,
    'wm_margin': 15,
    'wm_gap': 30,
    'wm_angle': 0,
    'wm_text': '',
    'wm_text_color': '#FFFFFF',
    'out_fmt': 'JPEG',
    'out_quality': 80,
    'naming_mode': 'Keep Original',
    'naming_prefix': '',
    'font_name': None,
    'preset_wm_bytes': None
}

# === POSITION PRESETS ===
TILED_SETTINGS = {
    'wm_scale': 15,
    'wm_opacity': 0.3,
    'wm_gap': 30,
    'wm_angle': 45
}

CORNER_SETTINGS = {
    'wm_scale': 15,
    'wm_opacity': 1.0,
    'wm_margin': 15,
    'wm_angle': 0
}

# === PERFORMANCE ===
MIN_THREADS = 1
MAX_THREADS = 8
DEFAULT_THREADS = 2
CACHE_TTL = 300  # seconds

# === PATHS ===
def get_project_root() -> Path:
    """Get project root directory"""
    return Path(__file__).parent

def get_assets_dir() -> Path:
    """Get assets directory"""
    return get_project_root() / 'assets'

def get_fonts_dir() -> Path:
    """Get fonts directory"""
    return get_assets_dir() / 'fonts'

# === LOGGING ===
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
LOG_LEVEL = 'INFO'
LOG_FILE = 'watermarker.log'

# === RESIZE PRESETS ===
RESIZE_PRESETS = {
    'HD': 1280,
    'FHD': 1920,
    '2K': 2560,
    '4K': 3840
}
