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
    """
    Validate that file exists and is accessible
    
    Raises:
        ValidationError: If file is invalid
    """
    if not file_path:
        raise ValidationError("File path is empty")
    
    path = Path(file_path)
    
    if not path.exists():
        raise ValidationError(f"File not found: {file_path}")
    
    if not path.is_file():
        raise ValidationError(f"Not a file: {file_path}")
    
    if not os.access(file_path, os.R_OK):
        raise ValidationError(f"File not readable: {file_path}")
    
    return True

def validate_image_file(file_path: str) -> bool:
    """
    Validate image file format and integrity
    
    Raises:
        ValidationError: If image is invalid
    """
    validate_file_path(file_path)
    
    # Check extension
    ext = Path(file_path).suffix.lower()
    if ext not in config.SUPPORTED_INPUT_FORMATS:
        raise ValidationError(
            f"Unsupported format: {ext}. "
            f"Supported: {', '.join(config.SUPPORTED_INPUT_FORMATS)}"
        )
    
    # Check file size
    file_size = os.path.getsize(file_path)
    if file_size > config.MAX_FILE_SIZE:
        size_mb = file_size / (1024 * 1024)
        max_mb = config.MAX_FILE_SIZE / (1024 * 1024)
        raise ValidationError(
            f"File too large: {size_mb:.1f} MB (max: {max_mb:.1f} MB)"
        )
    
    # Verify image integrity
    try:
        with Image.open(file_path) as img:
            img.verify()
        
        # Reopen after verify (verify() invalidates the image)
        with Image.open(file_path) as img:
            width, height = img.size
            
            if width < config.MIN_IMAGE_DIMENSION or height < config.MIN_IMAGE_DIMENSION:
                raise ValidationError(
                    f"Image too small: {width}x{height} "
                    f"(min: {config.MIN_IMAGE_DIMENSION}px)"
                )
            
            if width > config.MAX_IMAGE_DIMENSION or height > config.MAX_IMAGE_DIMENSION:
                raise ValidationError(
                    f"Image too large: {width}x{height} "
                    f"(max: {config.MAX_IMAGE_DIMENSION}px)"
                )
    
    except ValidationError:
        raise
    except Exception as e:
        raise ValidationError(f"Corrupted or invalid image: {e}")
    
    return True

def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename by removing dangerous characters
    
    Args:
        filename: Original filename
        
    Returns:
        Safe filename
    """
    if not filename:
        return "unnamed"
    
    # Keep only filename (remove path)
    filename = Path(filename).name
    
    # Remove dangerous characters
    filename = re.sub(r'[<>:"|?*\x00-\x1f]', '', filename)
    
    # Replace spaces with underscores
    filename = filename.replace(' ', '_')
    
    # Limit length
    if len(filename) > config.MAX_FILENAME_LENGTH:
        name, ext = os.path.splitext(filename)
        max_name_len = config.MAX_FILENAME_LENGTH - len(ext)
        filename = name[:max_name_len] + ext
    
    # Ensure not empty
    if not filename or filename == '.':
        filename = "unnamed.jpg"
    
    return filename

def validate_color_hex(color_hex: str) -> Tuple[int, int, int]:
    """
    Validate and parse hex color
    
    Args:
        color_hex: Hex color string (e.g., "#FFFFFF")
        
    Returns:
        RGB tuple
        
    Raises:
        ValidationError: If color is invalid
    """
    color = color_hex.lstrip('#')
    
    if len(color) != 6:
        raise ValidationError(f"Invalid color format: {color_hex}")
    
    try:
        rgb = tuple(int(color[i:i+2], 16) for i in (0, 2, 4))
        return rgb
    except ValueError:
        raise ValidationError(f"Invalid hex color: {color_hex}")

def validate_dimensions(width: int, height: int) -> bool:
    """
    Validate image dimensions
    
    Raises:
        ValidationError: If dimensions are invalid
    """
    if width <= 0 or height <= 0:
        raise ValidationError(f"Invalid dimensions: {width}x{height}")
    
    if width < config.MIN_IMAGE_DIMENSION or height < config.MIN_IMAGE_DIMENSION:
        raise ValidationError(
            f"Dimensions too small: {width}x{height} "
            f"(min: {config.MIN_IMAGE_DIMENSION}px)"
        )
    
    if width > config.MAX_IMAGE_DIMENSION or height > config.MAX_IMAGE_DIMENSION:
        raise ValidationError(
            f"Dimensions too large: {width}x{height} "
            f"(max: {config.MAX_IMAGE_DIMENSION}px)"
        )
    
    return True

def validate_scale_factor(scale: float, min_val: float = 0.01, max_val: float = 10.0) -> bool:
    """
    Validate scale factor
    
    Raises:
        ValidationError: If scale is invalid
    """
    if not isinstance(scale, (int, float)):
        raise ValidationError(f"Scale must be numeric, got: {type(scale)}")
    
    if scale <= 0:
        raise ValidationError(f"Scale must be positive, got: {scale}")
    
    if scale < min_val or scale > max_val:
        raise ValidationError(
            f"Scale out of range: {scale} (allowed: {min_val}-{max_val})"
        )
    
    return True

def safe_divide(numerator: float, denominator: float, default: float = 1.0) -> float:
    """
    Safely divide with zero check
    
    Args:
        numerator: Numerator
        denominator: Denominator
        default: Value to return if denominator is zero
        
    Returns:
        Result or default
    """
    if denominator == 0:
        logger.warning(f"Division by zero prevented: {numerator}/{denominator}")
        return default
    return numerator / denominator
