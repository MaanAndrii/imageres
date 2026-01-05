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
    """Safely remove thumbnail file"""
    thumb_path = f"{file_path}.thumb.jpg"
    try:
        if os.path.exists(thumb_path):
            os.remove(thumb_path)
            return True
    except (PermissionError, OSError) as e:
        logger.warning(f"Could not remove thumbnail {thumb_path}: {e}")
    return False

# === ROTATION ===
def rotate_image_file(file_path: str, angle: int) -> bool:
    """Rotate image file permanently"""
    try:
        validate_image_file(file_path)
        with Image.open(file_path) as img_temp:
            img = ImageOps.exif_transpose(img_temp)
            exif_data = img.info.get('exif')
            rotated = img.rotate(-angle, expand=True, resample=Image.BICUBIC)
            save_kwargs = {"quality": 95, "subsampling": 0}
            if exif_data:
                save_kwargs['exif'] = exif_data
            rotated.save(file_path, **save_kwargs)
        remove_thumbnail(file_path)
        return True
    except Exception as e:
        logger.error(f"Rotation failed: {e}")
        return False

# === WATERMARK LOADING ===
def load_watermark_from_bytes(wm_bytes: bytes) -> Image.Image:
    """Load watermark from bytes with validation"""
    if not wm_bytes:
        raise ValueError("Watermark bytes are empty")
    try:
        wm = Image.open(io.BytesIO(wm_bytes))
        wm = wm.convert("RGBA")
        validate_dimensions(wm.width, wm.height)
        return wm
    except Exception as e:
        logger.error(f"Failed to load watermark: {e}")
        raise ValueError(f"Failed to load watermark: {str(e)}")

def get_cached_font(font_path: str, size: int) -> ImageFont.FreeTypeFont:
    """Get font with caching for performance"""
    cache_key = (font_path, size)
    if cache_key not in _font_cache:
        try:
            _font_cache[cache_key] = ImageFont.truetype(font_path, size)
        except Exception as e:
            logger.warning(f"Font loading failed: {e}")
            _font_cache[cache_key] = ImageFont.load_default()
    return _font_cache[cache_key]

def create_text_watermark(text: str, font_path: Optional[str], size_pt: int, color_hex: str) -> Optional[Image.Image]:
    """Create text watermark image"""
    if not text or not text.strip():
        return None
    try:
        font = get_cached_font(font_path, size_pt) if font_path else ImageFont.load_default()
        rgb = validate_color_hex(color_hex)
        dummy_img = Image.new('RGBA', (1, 1))
        draw = ImageDraw.Draw(dummy_img)
        bbox = draw.textbbox((0, 0), text, font=font)
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        padding = 20
        wm = Image.new('RGBA', (w + padding*2, h + padding*2), (0, 0, 0, 0))
        ImageDraw.Draw(wm).text((padding, padding), text, font=font, fill=rgb + (255,))
        return wm
    except Exception as e:
        logger.error(f"Text watermark creation failed: {e}")
        return None

def apply_opacity(image: Image.Image, opacity: float) -> Image.Image:
    """Apply opacity to image"""
    if opacity >= 1.0: return image
    try:
        alpha = image.split()[3]
        alpha = ImageEnhance.Brightness(alpha).enhance(max(0.0, min(1.0, opacity)))
        image.putalpha(alpha)
        return image
    except Exception as e:
        logger.error(f"Opacity failed: {e}"); return image

# === MAIN PROCESSING ===
def process_image(file_path: str, filename: str, wm_obj: Optional[Image.Image], resize_config: Dict, output_fmt: str, quality: int) -> Tuple[bytes, Dict]:
    """Process image with watermark and resize"""
    try:
        validate_image_file(file_path)
        with Image.open(file_path) as img_temp:
            img = ImageOps.exif_transpose(img_temp)
            exif_data = img.info.get('exif')
            orig_w, orig_h = img.size
            orig_size = os.path.getsize(file_path)
            img = img.convert("RGBA")
        
        new_w, new_h, scale_factor = _calculate_resize(orig_w, orig_h, resize_config)
        if scale_factor != 1.0:
            img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        
        if wm_obj:
            img = _apply_watermark(img, wm_obj, resize_config)
        
        result_bytes = _export_image(img, output_fmt, quality, exif_data)
        stats = {
            "filename": filename, "orig_res": f"{orig_w}x{orig_h}", "new_res": f"{new_w}x{new_h}",
            "orig_size": orig_size, "new_size": len(result_bytes), "scale_factor": f"{scale_factor:.2f}x"
        }
        return result_bytes, stats
    except Exception as e:
        logger.error(f"Processing failed for {file_path}: {e}", exc_info=True); raise

def _calculate_resize(orig_w: int, orig_h: int, config_dict: Dict) -> Tuple[int, int, float]:
    """Calculate new dimensions"""
    if not config_dict.get('enabled', False): return orig_w, orig_h, 1.0
    val = config_dict.get('value', 1920); mode = config_dict.get('mode', 'Max Side')
    sf = 1.0
    if mode == "Max Side" and (orig_w > val or orig_h > val):
        sf = val / orig_w if orig_w >= orig_h else val / orig_h
    elif mode == "Exact Width": sf = val / orig_w
    elif mode == "Exact Height": sf = val / orig_h
    nw, nh = max(1, int(orig_w * sf)), max(1, int(orig_h * sf))
    return nw, nh, sf

def _apply_watermark(img: Image.Image, wm_obj: Image.Image, config_dict: Dict) -> Image.Image:
    """Scale and apply watermark"""
    try:
        nw, nh = img.size
        scale = max(0.01, min(0.9, config_dict.get('wm_scale', 0.15)))
        pos = config_dict.get('wm_position', 'bottom-right')
        angle = config_dict.get('wm_angle', 0)
        
        wm_w_target = max(10, int(nw * scale))
        w_ratio = wm_w_target / wm_obj.width
        wm_h_target = max(10, int(wm_obj.height * w_ratio))
        
        wm_res = wm_obj.resize((wm_w_target, wm_h_target), Image.Resampling.LANCZOS)
        if angle != 0:
            wm_res = wm_res.rotate(angle, expand=True, resample=Image.BICUBIC)
        
        return _apply_tiled_watermark(img, wm_res, config_dict) if pos == 'tiled' else _apply_corner_watermark(img, wm_res, pos, config_dict)
    except Exception as e:
        logger.error(f"WM apply failed: {e}"); return img

def _apply_tiled_watermark(img: Image.Image, wm: Image.Image, config_dict: Dict) -> Image.Image:
    """Apply tiled pattern with fix for vertical images"""
    gap = config_dict.get('wm_gap', 30)
    nw, nh = img.size
    wm_w, wm_h = wm.size
    overlay = Image.new('RGBA', (nw, nh), (0, 0, 0, 0))
    
    step_x, step_y = max(10, wm_w + gap), max(10, wm_h + gap)
    
    # Розрахунок базової сітки
    base_rows = (nh // step_y) + 2
    base_cols = (nw // step_x) + 2
    
    # КЛЮЧОВЕ ВИПРАВЛЕННЯ: У вертикальних фото діагональний зсув на нижніх рядках 
    # вимагає значно більшого від'ємного діапазону колонок, щоб заповнити лівий кут.
    # col_shift_offset компенсує (row * step_x // 2) при великих значеннях row.
    col_shift_offset = (base_rows // 2) + 3
    
    start_row, end_row = -2, base_rows + 2
    start_col, end_col = -col_shift_offset, base_cols + col_shift_offset
    
    for row in range(start_row, end_row):
        for col in range(start_col, end_col):
            x = col * step_x + (row * step_x // 2)
            y = row * step_y
            # Малюємо тільки якщо в межах видимості
            if (x + wm_w > 0 and x < nw and y + wm_h > 0 and y < nh):
                overlay.paste(wm, (x, y), wm)
                
    return Image.alpha_composite(img, overlay)

def _apply_corner_watermark(img: Image.Image, wm: Image.Image, pos: str, config_dict: Dict) -> Image.Image:
    """Apply watermark to specific position"""
    margin = config_dict.get('wm_margin', 15)
    nw, nh = img.size; ww, wh = wm.size
    if pos == 'bottom-right': px, py = nw - ww - margin, nh - wh - margin
    elif pos == 'bottom-left': px, py = margin, nh - wh - margin
    elif pos == 'top-right': px, py = nw - ww - margin, margin
    elif pos == 'top-left': px, py = margin, margin
    elif pos == 'center': px, py = (nw - ww) // 2, (nh - wh) // 2
    else: px, py = margin, margin
    img.paste(wm, (max(0, min(px, nw-ww)), max(0, min(py, nh-wh))), wm)
    return img

def _export_image(img: Image.Image, fmt: str, qual: int, exif: Optional[bytes]) -> bytes:
    """Export to bytes"""
    if fmt == "JPEG":
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[3]); img = bg
    elif fmt == "RGB": img = img.convert("RGB")
    buf = io.BytesIO(); sk = {"format": fmt}
    if exif and fmt in ["JPEG", "WEBP"]: sk['exif'] = exif
    if fmt == "JPEG": sk.update({"quality": qual, "optimize": True, "subsampling": 0})
    elif fmt == "WEBP": sk.update({"quality": qual, "method": 6})
    elif fmt == "PNG": sk.update({"optimize": True})
    img.save(buf, **sk); return buf.getvalue()
