"""
Watermarker Pro v7.0 - Validation Module
"""
import os
import re
from pathlib import Path
from typing import Tuple, List
from PIL import Image
import config
from logger import get_logger

logger = get_logger(__name__)

class ValidationError(Exception): pass

def validate_file_path(file_path: str) -> bool:
    if not file_path: raise ValidationError("File path is empty")
    path = Path(file_path)
    if not path.exists(): raise ValidationError(f"File not found: {file_path}")
    if not path.is_file(): raise ValidationError(f"Not a file: {file_path}")
    return True

def validate_image_file(file_path: str) -> bool:
    validate_file_path(file_path)
    ext = Path(file_path).suffix.lower()
    
    if ext not in config.SUPPORTED_INPUT_FORMATS:
        raise ValidationError(f"Unsupported format: {ext}")
    
    file_size = os.path.getsize(file_path)
    if file_size > config.MAX_FILE_SIZE:
        raise ValidationError(f"File too large: {file_size/(1024*1024):.1f} MB")
    
    # Для PDF пропускаємо Pillow-перевірку
    if ext == '.pdf':
        return True
        
    try:
        with Image.open(file_path) as img:
            img.verify()
        with Image.open(file_path) as img:
            w, h = img.size
            if w < config.MIN_IMAGE_DIMENSION or h < config.MIN_IMAGE_DIMENSION:
                raise ValidationError("Image too small")
    except ValidationError: raise
    except Exception as e: raise ValidationError(f"Invalid image: {e}")
    
    return True

def sanitize_filename(filename: str) -> str:
    if not filename: return "unnamed"
    filename = Path(filename).name
    filename = re.sub(r'[<>:"|?*\x00-\x1f]', '', filename)
    filename = filename.replace(' ', '_')
    if len(filename) > config.MAX_FILENAME_LENGTH:
        name, ext = os.path.splitext(filename)
        filename = name[:config.MAX_FILENAME_LENGTH-len(ext)] + ext
    return filename

def validate_color_hex(color_hex: str) -> Tuple[int, int, int]:
    color = color_hex.lstrip('#')
    try:
        return tuple(int(color[i:i+2], 16) for i in (0, 2, 4))
    except Exception: raise ValidationError(f"Invalid color: {color_hex}")

def validate_dimensions(width: int, height: int) -> bool:
    if width <= 0 or height <= 0: raise ValidationError("Invalid dimensions")
    return True

def validate_scale_factor(scale: float) -> bool:
    if scale <= 0: raise ValidationError("Scale must be positive")
    return True

def safe_divide(n, d, default=1.0):
    return n / d if d != 0 else default
