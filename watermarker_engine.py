"""
Watermarker Pro v7.0 - Engine Module
=====================================
Core image processing with error handling and optimization
"""

import io
import os
import re
import base64
from typing import Optional, Tuple, Dict
from PIL import Image, ImageEnhance, ImageOps, ImageDraw, ImageFont
from translitua import translit
import config
from logger import get_logger
from validators import (
    validate_image_file, validate_dimensions, 
    validate_scale_factor, safe_divide, validate_color_hex
)

logger = get_logger(__name__)

# Font cache for performance
_font_cache: Dict[Tuple[str, int], ImageFont.FreeTypeFont] = {}

# === ENCODING ===
def image_to_base64(image_bytes: bytes) -> str:
    """Convert image bytes to base64 string"""
    try:
        return base64.b64encode(image_bytes).decode('utf-8')
    except Exception as e:
        logger.error(f"Base64 encoding failed: {e}")
        raise

def base64_to_bytes(base64_string: str) -> bytes:
    """Convert base64 string to bytes"""
    try:
        return base64.b64decode(base64_string)
    except Exception as e:
        logger.error(f"Base64 decoding failed: {e}")
        raise

# === FILENAME GENERATION ===
def generate_filename(
    original_path: str,
    naming_mode: str,
    prefix: str = "",
    extension: str = "jpg",
    index: int = 1
) -> str:
    """
    Generate output filename based on naming mode
    
    Args:
        original_path: Path to original file
        naming_mode: "Keep Original" or "Prefix + Sequence"
        prefix: Optional prefix
        extension: File extension
        index: Sequential number
        
    Returns:
        Generated filename
    """
    try:
        original_name = os.path.basename(original_path)
        
        # Sanitize prefix
        clean_prefix = ""
        if prefix:
            clean_prefix = re.sub(r'[\s\W_]+', '-', translit(prefix).lower()).strip('-')
        
        if naming_mode == "Prefix + Sequence":
            base_name = clean_prefix if clean_prefix else "image"
            return f"{base_name}_{index:03d}.{extension}"
        
        # Keep Original mode
        name_only = os.path.splitext(original_name)[0]
        slug = re.sub(r'[\s\W_]+', '-', translit(name_only).lower()).strip('-')
        
        if not slug:
            slug = "image"
        
        base = f"{clean_prefix}_{slug}" if clean_prefix else slug
        return f"{base}.{extension}"
    
    except Exception as e:
        logger.error(f"Filename generation failed: {e}")
        return f"output_{index:03d}.{extension}"

# === THUMBNAIL ===
def get_thumbnail(file_path: str, size: Tuple[int, int] = None) -> Optional[str]:
    """
    Get or create thumbnail with caching
    
    Args:
        file_path: Path to original image
        size: Thumbnail size (default from config)
        
    Returns:
        Path to thumbnail or None on error
    """
    if size is None:
        size = config.THUMBNAIL_SIZE
    
    thumb_path = f"{file_path}.thumb.jpg"
    
    try:
        # Check if thumbnail is up-to-date
        if os.path.exists(thumb_path):
            thumb_mtime = os.path.getmtime(thumb_path)
            img_mtime = os.path.getmtime(file_path)
            if thumb_mtime > img_mtime:
                return thumb_path
        
        # Generate new thumbnail
        with Image.open(file_path) as img_temp:
            img = ImageOps.exif_transpose(img_temp)
            img = img.convert('RGB')
            img.thumbnail(size, Image.Resampling.LANCZOS)
            img.save(thumb_path, "JPEG", quality=70, optimize=True)
            
        logger.debug(f"Thumbnail created: {thumb_path}")
        return thumb_path
    
    except Exception as e:
        logger.error(f"Thumbnail generation failed for {file_path}: {e}")
        return None

def remove_thumbnail(file_path: str) -> bool:
    """
    Safely remove thumbnail file
    
    Args:
        file_path: Path to original image
        
    Returns:
        True if removed, False otherwise
    """
    thumb_path = f"{file_path}.thumb.jpg"
    
    try:
        if os.path.exists(thumb_path):
            os.remove(thumb_path)
            logger.debug(f"Thumbnail removed: {thumb_path}")
            return True
    except (PermissionError, OSError) as e:
        logger.warning(f"Could not remove thumbnail {thumb_path}: {e}")
    
    return False

# === ROTATION ===
def rotate_image_file(file_path: str, angle: int) -> bool:
    """
    Rotate image file permanently
    
    Args:
        file_path: Path to image
        angle: Rotation angle (90, -90, 180, etc.)
        
    Returns:
        True on success, False on failure
    """
    try:
        validate_image_file(file_path)
        
        with Image.open(file_path) as img_temp:
            # Fix orientation first
            img = ImageOps.exif_transpose(img_temp)
            
            # Preserve EXIF data
            exif_data = img.info.get('exif')
            
            # Rotate with expansion
            rotated = img.rotate(-angle, expand=True, resample=Image.BICUBIC)
            
            # Save with EXIF
            save_kwargs = {"quality": 95, "subsampling": 0}
            if exif_data:
                save_kwargs['exif'] = exif_data
            
            rotated.save(file_path, **save_kwargs)
        
        # Invalidate thumbnail cache
        remove_thumbnail(file_path)
        
        logger.info(f"Image rotated {angle}°: {file_path}")
        return True
    
    except Exception as e:
        logger.error(f"Rotation failed for {file_path}: {e}")
        return False

# === WATERMARK LOADING ===
def load_watermark_from_bytes(wm_bytes: bytes) -> Image.Image:
    """
    Load watermark from bytes with validation
    
    Args:
        wm_bytes: Image bytes
        
    Returns:
        PIL Image in RGBA mode
        
    Raises:
        ValueError: If watermark is invalid
    """
    if not wm_bytes:
        raise ValueError("Watermark bytes are empty")
    
    try:
        wm = Image.open(io.BytesIO(wm_bytes))
        wm = wm.convert("RGBA")
        
        # Validate dimensions
        if wm.width == 0 or wm.height == 0:
            raise ValueError(f"Invalid watermark dimensions: {wm.width}x{wm.height}")
        
        validate_dimensions(wm.width, wm.height)
        
        logger.debug(f"Watermark loaded: {wm.width}x{wm.height}")
        return wm
    
    except Exception as e:
        logger.error(f"Failed to load watermark: {e}")
        raise ValueError(f"Failed to load watermark: {str(e)}")

def get_cached_font(font_path: str, size: int) -> ImageFont.FreeTypeFont:
    """
    Get font with caching for performance
    
    Args:
        font_path: Path to font file
        size: Font size in points
        
    Returns:
        Font object
    """
    cache_key = (font_path, size)
    
    if cache_key not in _font_cache:
        try:
            _font_cache[cache_key] = ImageFont.truetype(font_path, size)
            logger.debug(f"Font cached: {font_path} @ {size}pt")
        except Exception as e:
            logger.warning(f"Font loading failed, using default: {e}")
            _font_cache[cache_key] = ImageFont.load_default()
    
    return _font_cache[cache_key]

def create_text_watermark(
    text: str,
    font_path: Optional[str],
    size_pt: int,
    color_hex: str
) -> Optional[Image.Image]:
    """
    Create text watermark image
    
    Args:
        text: Watermark text
        font_path: Path to font file (optional)
        size_pt: Font size in points
        color_hex: Hex color (e.g., "#FFFFFF")
        
    Returns:
        PIL Image or None
    """
    if not text or not text.strip():
        return None
    
    try:
        # Load font
        if font_path and os.path.exists(font_path):
            font = get_cached_font(font_path, size_pt)
        else:
            font = ImageFont.load_default()
        
        # Parse color
        rgb = validate_color_hex(color_hex)
        
        # Calculate text size
        dummy_img = Image.new('RGBA', (1, 1))
        dummy_draw = ImageDraw.Draw(dummy_img)
        bbox = dummy_draw.textbbox((0, 0), text, font=font)
        
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        
        # Create watermark with padding
        padding = 20
        wm = Image.new('RGBA', (w + padding*2, h + padding*2), (0, 0, 0, 0))
        draw = ImageDraw.Draw(wm)
        
        # Draw text
        draw.text((padding, padding), text, font=font, fill=rgb + (255,))
        
        logger.debug(f"Text watermark created: {w}x{h}")
        return wm
    
    except Exception as e:
        logger.error(f"Text watermark creation failed: {e}")
        return None

def apply_opacity(image: Image.Image, opacity: float) -> Image.Image:
    """
    Apply opacity to image
    
    Args:
        image: PIL Image (RGBA mode)
        opacity: Opacity value (0.0 to 1.0)
        
    Returns:
        Image with applied opacity
    """
    if opacity >= 1.0:
        return image
    
    try:
        opacity = max(0.0, min(1.0, opacity))  # Clamp
        
        alpha = image.split()[3]
        alpha = ImageEnhance.Brightness(alpha).enhance(opacity)
        image.putalpha(alpha)
        
        return image
    
    except Exception as e:
        logger.error(f"Opacity application failed: {e}")
        return image

# === MAIN PROCESSING ===
def process_image(
    file_path: str,
    filename: str,
    wm_obj: Optional[Image.Image],
    resize_config: Dict,
    output_fmt: str,
    quality: int
) -> Tuple[bytes, Dict]:
    """
    Process image with watermark and resize
    
    Args:
        file_path: Path to source image
        filename: Output filename
        wm_obj: Watermark PIL Image (optional)
        resize_config: Resize configuration dict
        output_fmt: Output format (JPEG/PNG/WEBP)
        quality: JPEG/WEBP quality (1-100)
        
    Returns:
        Tuple of (image_bytes, stats_dict)
    """
    try:
        validate_image_file(file_path)
        
        # Open image safely
        with Image.open(file_path) as img_temp:
            img = ImageOps.exif_transpose(img_temp)
            exif_data = img.info.get('exif')
            
            orig_w, orig_h = img.size
            orig_size = os.path.getsize(file_path)
            
            img = img.convert("RGBA")
        
        # Resize logic
        new_w, new_h, scale_factor = _calculate_resize(
            orig_w, orig_h, resize_config
        )
        
        if scale_factor != 1.0:
            img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            logger.debug(f"Resized: {orig_w}x{orig_h} → {new_w}x{new_h}")
        
        # Apply watermark
        if wm_obj:
            img = _apply_watermark(img, wm_obj, resize_config)
        
        # Export
        result_bytes = _export_image(img, output_fmt, quality, exif_data)
        
        # Statistics
        stats = {
            "filename": filename,
            "orig_res": f"{orig_w}x{orig_h}",
            "new_res": f"{new_w}x{new_h}",
            "orig_size": orig_size,
            "new_size": len(result_bytes),
            "scale_factor": f"{scale_factor:.2f}x"
        }
        
        logger.info(f"Processed: {filename} ({stats['orig_res']} → {stats['new_res']})")
        return result_bytes, stats
    
    except Exception as e:
        logger.error(f"Processing failed for {file_path}: {e}", exc_info=True)
        raise

def _calculate_resize(
    orig_w: int,
    orig_h: int,
    config: Dict
) -> Tuple[int, int, float]:
    """Calculate new dimensions and scale factor"""
    
    if not config.get('enabled', False):
        return orig_w, orig_h, 1.0
    
    target_value = config.get('value', 1920)
    mode = config.get('mode', 'Max Side')
    
    scale_factor = 1.0
    new_w, new_h = orig_w, orig_h
    
    try:
        if mode == "Max Side" and (orig_w > target_value or orig_h > target_value):
            if orig_w >= orig_h:
                scale_factor = safe_divide(target_value, orig_w, 1.0)
            else:
                scale_factor = safe_divide(target_value, orig_h, 1.0)
            
            new_w = max(1, int(orig_w * scale_factor))
            new_h = max(1, int(orig_h * scale_factor))
        
        elif mode == "Exact Width":
            scale_factor = safe_divide(target_value, orig_w, 1.0)
            new_w = target_value
            new_h = max(1, int(orig_h * scale_factor))
        
        elif mode == "Exact Height":
            scale_factor = safe_divide(target_value, orig_h, 1.0)
            new_w = max(1, int(orig_w * scale_factor))
            new_h = target_value
        
        # Validate result
        validate_dimensions(new_w, new_h)
        
        return new_w, new_h, scale_factor
    
    except Exception as e:
        logger.error(f"Resize calculation failed: {e}")
        return orig_w, orig_h, 1.0

def _apply_watermark(
    img: Image.Image,
    wm_obj: Image.Image,
    config: Dict
) -> Image.Image:
    """Apply watermark to image"""
    
    try:
        new_w, new_h = img.size
        scale = config.get('wm_scale', 0.15)
        position = config.get('wm_position', 'bottom-right')
        angle = config.get('wm_angle', 0)
        
        # Clamp scale
        scale = max(0.01, min(0.9, scale))
        validate_scale_factor(scale)
        
        # Calculate watermark size
        wm_w_target = max(10, int(new_w * scale))
        w_ratio = safe_divide(wm_w_target, wm_obj.width, 1.0)
        wm_h_target = max(10, int(wm_obj.height * w_ratio))
        
        # Resize watermark
        wm_resized = wm_obj.resize(
            (wm_w_target, wm_h_target),
            Image.Resampling.LANCZOS
        )
        
        # Rotate if needed
        if angle != 0:
            wm_resized = wm_resized.rotate(
                angle,
                expand=True,
                resample=Image.BICUBIC
            )
        
        wm_w_final, wm_h_final = wm_resized.size
        
        # Apply based on position
        if position == 'tiled':
            img = _apply_tiled_watermark(img, wm_resized, config)
        else:
            img = _apply_corner_watermark(img, wm_resized, position, config)
        
        return img
    
    except Exception as e:
        logger.error(f"Watermark application failed: {e}")
        return img

def _apply_tiled_watermark(
    img: Image.Image,
    wm: Image.Image,
    config: Dict
) -> Image.Image:
    """Apply tiled watermark pattern"""
    
    gap = config.get('wm_gap', 30)
    new_w, new_h = img.size
    wm_w, wm_h = wm.size
    
    overlay = Image.new('RGBA', (new_w, new_h), (0, 0, 0, 0))
    
    step_x = max(10, wm_w + gap)
    step_y = max(10, wm_h + gap)
    
    # Розрахунок базової кількості рядків та колонок, необхідних для покриття зображення
    base_rows = (new_h // step_y) + 2
    base_cols = (new_w // step_x) + 2
    
    # Значно збільшуємо буфер ітерацій в обидва боки (від'ємний і додатний).
    # Це необхідно для компенсації діагонального зсуву `(row * step_x // 2)`,
    # який може призвести до пропусків у кутах при стандартному діапазоні.
    row_buffer = base_rows
    col_buffer = base_cols
    
    start_row = -row_buffer
    end_row = base_rows + row_buffer
    
    start_col = -col_buffer
    end_col = base_cols + col_buffer
    
    logger.debug(f"Tiling approach: rows[{start_row}:{end_row}], cols[{start_col}:{end_col}], step_x={step_x}, step_y={step_y}")
    
    count_pasted = 0
    for row in range(start_row, end_row):
        for col in range(start_col, end_col):
            # Розрахунок позиції з діагональним зсувом
            x = col * step_x + (row * step_x // 2)
            y = row * step_y
            
            # Перевірка, чи перетинається водяний знак з видимою областю зображення
            if (x + wm_w > 0 and x < new_w and
                y + wm_h > 0 and y < new_h):
                overlay.paste(wm, (x, y), wm)
                count_pasted += 1
                
    logger.debug(f"Tiled watermark finished: {count_pasted} tiles pasted")
    
    return Image.alpha_composite(img, overlay)

def _apply_corner_watermark(
    img: Image.Image,
    wm: Image.Image,
    position: str,
    config: Dict
) -> Image.Image:
    """Apply watermark at corner position"""
    
    margin = config.get('wm_margin', 15)
    new_w, new_h = img.size
    wm_w, wm_h = wm.size
    
    # Calculate position
    if position == 'bottom-right':
        pos_x = new_w - wm_w - margin
        pos_y = new_h - wm_h - margin
    elif position == 'bottom-left':
        pos_x = margin
        pos_y = new_h - wm_h - margin
    elif position == 'top-right':
        pos_x = new_w - wm_w - margin
        pos_y = margin
    elif position == 'top-left':
        pos_x = margin
        pos_y = margin
    elif position == 'center':
        pos_x = (new_w - wm_w) // 2
        pos_y = (new_h - wm_h) // 2
    else:
        pos_x = margin
        pos_y = margin
    
    # Clamp to image bounds
    pos_x = max(0, min(pos_x, new_w - wm_w))
    pos_y = max(0, min(pos_y, new_h - wm_h))
    
    img.paste(wm, (pos_x, pos_y), wm)
    return img

def _export_image(
    img: Image.Image,
    output_fmt: str,
    quality: int,
    exif_data: Optional[bytes]
) -> bytes:
    """Export image to bytes"""
    
    # Convert for JPEG
    if output_fmt == "JPEG":
        background = Image.new("RGB", img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[3])
        img = background
    elif output_fmt == "RGB":
        img = img.convert("RGB")
    
    output_buffer = io.BytesIO()
    save_kwargs = {}
    
    if exif_data and output_fmt in ["JPEG", "WEBP"]:
        save_kwargs['exif'] = exif_data
    
    if output_fmt == "JPEG":
        save_kwargs.update({
            "format": "JPEG",
            "quality": quality,
            "optimize": True,
            "subsampling": 0
        })
    elif output_fmt == "WEBP":
        save_kwargs.update({
            "format": "WEBP",
            "quality": quality,
            "method": 6
        })
    elif output_fmt == "PNG":
        save_kwargs.update({
            "format": "PNG",
            "optimize": True
        })
    
    img.save(output_buffer, **save_kwargs)
    return output_buffer.getvalue()
