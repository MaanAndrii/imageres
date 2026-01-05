"""
Watermarker Pro v7.0 - Validation Module
=========================================
Input validation and sanitization
"""

import os
import re
from pathlib import Path
from typing import Tuple
from PIL import Image
import config
from logger import get_logger

logger = get_logger(__name__)

class ValidationError(Exception):
    """Custom validation error"""
    pass

def validate_file_path(file_path: str) -> bool:
    """Validate that file exists and is accessible"""
    if not file_path:
        raise ValidationError("File path is empty")
    
    path = Path(file_path)
    if not path.exists():
        raise ValidationError(f"File not found: {file_path}")
    
    if not path.is_file():
        raise ValidationError(f"Not a file: {file_path}")
    
    return True

def validate_image_file(file_path: str) -> bool:
    """Validate file format and integrity"""
    validate_file_path(file_path)
    
    ext = Path(file_path).suffix.lower()
    if ext not in config.SUPPORTED_INPUT_FORMATS:
        raise ValidationError(f"Unsupported format: {ext}")
    
    file_size = os.path.getsize(file_path)
    if file_size > config.MAX_FILE_SIZE:
        raise ValidationError(f"File too large: {file_size/(1024*1024):.1f} MB")
    
    # PDF не потребує перевірки Pillow verify() на етапі завантаження
    if ext == '.pdf':
        return True
    
    try:
        with Image.open(file_path) as img:
            img.verify()
        
        with Image.open(file_path) as img:
            width, height = img.size
            if width < config.MIN_IMAGE_DIMENSION or height < config.MIN_IMAGE_DIMENSION:
                raise ValidationError("Image too small")
    except Exception as e:
        raise ValidationError(f"Invalid image file: {e}")
    
    return True

def sanitize_filename(filename: str) -> str:
    """Sanitize filename by removing dangerous characters"""
    if not filename:
        return "unnamed"
    
    filename = Path(filename).name
    filename = re.sub(r'[<>:"|?*\x00-\x1f]', '', filename)
    filename = filename.replace(' ', '_')
    
    if len(filename) > config.MAX_FILENAME_LENGTH:
        name, ext = os.path.splitext(filename)
        filename = name[:config.MAX_FILENAME_LENGTH - len(ext)] + ext
    
    return filename

def validate_color_hex(color_hex: str) -> Tuple[int, int, int]:
    """Validate and parse hex color"""
    color = color_hex.lstrip('#')
    if len(color) != 6:
        raise ValidationError(f"Invalid color format: {color_hex}")
    try:
        return tuple(int(color[i:i+2], 16) for i in (0, 2, 4))
    except ValueError:
        raise ValidationError(f"Invalid hex color: {color_hex}")

def validate_dimensions(width: int, height: int) -> bool:
    if width <= 0 or height <= 0:
        raise ValidationError("Invalid dimensions")
    return True

def validate_scale_factor(scale: float) -> bool:
    if scale <= 0:
        raise ValidationError("Scale must be positive")
    return True

def safe_divide(numerator: float, denominator: float, default: float = 1.0) -> float:
    if denominator == 0:
        return default
    return numerator / denominator
