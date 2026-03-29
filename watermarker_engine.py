"""
Watermarker Pro v8.0 - Engine Module
=====================================
Core image processing with error handling and optimization.

Зміни v8.0:
- SVG як вотермарка (через resvg-py → PNG у пам'яті, без системних залежностей)
- LRU-кеш шрифтів з обмеженням розміру (cachetools)
- Токен скасування (CancellationToken) для batch-обробки
- HEIC/HEIF через pillow-heif
"""

import io
import os
import re
import base64
import threading
from typing import Optional, Tuple, Dict

from PIL import Image, ImageEnhance, ImageOps, ImageDraw, ImageFont
from translitua import translit
from cachetools import LRUCache

import config
from logger import get_logger
from validators import (
    validate_image_file, validate_dimensions,
    validate_scale_factor, safe_divide, validate_color_hex
)

logger = get_logger(__name__)

# === HEIC/HEIF SUPPORT ===
_heic_available = False
try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
    _heic_available = True
    logger.info("HEIC/HEIF support enabled via pillow-heif")
except ImportError:
    logger.warning("pillow-heif not installed — HEIC/HEIF files will not be supported")

# === SVG SUPPORT ===
# resvg-py — Rust-бібліотека з prebuilt wheels для всіх платформ.
# Не потребує libcairo, pkg-config або будь-яких системних залежностей.
# Сумісна зі Streamlit Cloud, Railway, Heroku тощо.
_svg_available = False
try:
    from resvg_py import svg_to_bytes as _resvg_svg_to_bytes
    _svg_available = True
    logger.info("SVG watermark support enabled via resvg-py")
except ImportError:
    logger.warning("resvg-py not installed — SVG watermarks will not be supported")

# === FONT CACHE (LRU, обмежений розмір) ===
_font_cache: LRUCache = LRUCache(maxsize=config.FONT_CACHE_MAX_SIZE)
_font_cache_lock = threading.Lock()


# === CANCELLATION TOKEN ===

class CancellationToken:
    """
    Простий токен скасування для batch-обробки.
    Передається в executor, кожен worker перевіряє is_cancelled().
    """
    def __init__(self):
        self._cancelled = threading.Event()

    def cancel(self):
        self._cancelled.set()

    def is_cancelled(self) -> bool:
        return self._cancelled.is_set()

    def reset(self):
        self._cancelled.clear()


# === HEIC AVAILABILITY ===

def is_heic_available() -> bool:
    """Повертає True якщо pillow-heif встановлено"""
    return _heic_available


def is_svg_available() -> bool:
    """Повертає True якщо resvg-py встановлено"""
    return _svg_available


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
    Generate output filename based on naming mode.
    HEIC/HEIF input always gets a standard image extension on output.
    """
    try:
        original_name = os.path.basename(original_path)

        clean_prefix = ""
        if prefix:
            clean_prefix = re.sub(r'[\s\W\_]+', '-', translit(prefix).lower()).strip('-')

        if naming_mode == "Prefix + Sequence":
            base_name = clean_prefix if clean_prefix else "image"
            return f"{base_name}_{index:03d}.{extension}"

        name_only = os.path.splitext(original_name)[0]
        slug = re.sub(r'[\s\W\_]+', '-', translit(name_only).lower()).strip('-')
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
    Get or create thumbnail with file-mtime caching.
    HEIC files decoded via pillow-heif.
    """
    if size is None:
        size = config.THUMBNAIL_SIZE

    thumb_path = f"{file_path}.thumb.jpg"

    try:
        if os.path.exists(thumb_path):
            if os.path.getmtime(thumb_path) > os.path.getmtime(file_path):
                return thumb_path

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
    """
    Rotate image file permanently.
    HEIC input: зберігає як JPEG поруч (HEIC write = платний кодек).
    """
    try:
        validate_image_file(file_path)

        ext = os.path.splitext(file_path)[1].lower()
        is_heic = ext in ('.heic', '.heif')

        with Image.open(file_path) as img_temp:
            img = ImageOps.exif_transpose(img_temp)
            exif_data = img.info.get('exif')
            rotated = img.rotate(-angle, expand=True, resample=Image.BICUBIC)

        if is_heic:
            out_path = os.path.splitext(file_path)[0] + "_rotated.jpg"
            rotated.convert('RGB').save(out_path, "JPEG", quality=95, subsampling=0)
            logger.info(f"HEIC rotated and saved as JPEG: {out_path}")
        else:
            save_kwargs = {"quality": 95, "subsampling": 0}
            if exif_data:
                save_kwargs['exif'] = exif_data
            rotated.save(file_path, **save_kwargs)

        remove_thumbnail(file_path)
        return True

    except Exception as e:
        logger.error(f"Rotation failed: {e}")
        return False


# === SVG WATERMARK ===

def load_svg_watermark(svg_bytes: bytes, target_width: int = 500) -> Optional[Image.Image]:
    """
    Конвертує SVG у RGBA PIL Image через resvg-py.

    resvg-py — Rust-бібліотека з prebuilt wheels. Не потребує libcairo,
    pkg-config або будь-яких системних залежностей. Повністю сумісна зі
    Streamlit Cloud.

    Args:
        svg_bytes:    Вміст SVG файлу (bytes або str)
        target_width: Ширина растеризації (px). resvg масштабує пропорційно.

    Returns:
        PIL Image у RGBA

    Raises:
        ValueError: якщо resvg-py не встановлено або SVG не вдалося растеризувати
    """
    if not _svg_available:
        raise ValueError(
            "resvg-py не встановлено. Встановіть: pip install resvg-py"
        )
    if not svg_bytes:
        raise ValueError("SVG bytes are empty")

    try:
        svg_string = svg_bytes.decode('utf-8') if isinstance(svg_bytes, bytes) else svg_bytes

        png_bytes = _resvg_svg_to_bytes(
            svg_string=svg_string,
            width=target_width         # resvg масштабує висоту пропорційно автоматично
        )

        img = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
        validate_dimensions(img.width, img.height)
        logger.debug(f"SVG watermark rasterized: {img.width}x{img.height}")
        return img

    except Exception as e:
        logger.error(f"SVG watermark load failed: {e}")
        raise ValueError(f"Failed to load SVG watermark: {e}")


# === PNG WATERMARK ===

def load_watermark_from_bytes(wm_bytes: bytes) -> Image.Image:
    """Load PNG watermark from bytes with validation"""
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


# === FONT CACHE ===

def get_cached_font(font_path: str, size: int) -> ImageFont.FreeTypeFont:
    """
    Get font with LRU caching (обмежений розмір через cachetools.LRUCache).
    Thread-safe.
    """
    cache_key = (font_path, size)
    with _font_cache_lock:
        if cache_key in _font_cache:
            return _font_cache[cache_key]

    try:
        font = ImageFont.truetype(font_path, size)
    except Exception as e:
        logger.warning(f"Font loading failed ({font_path}, {size}px): {e}")
        font = ImageFont.load_default()

    with _font_cache_lock:
        _font_cache[cache_key] = font

    return font


def get_font_cache_info() -> Dict:
    """Повертає статистику кешу шрифтів"""
    with _font_cache_lock:
        return {
            "size": len(_font_cache),
            "maxsize": _font_cache.maxsize,
            "hits": getattr(_font_cache, 'hits', 'n/a'),
            "misses": getattr(_font_cache, 'misses', 'n/a'),
        }


# === TEXT WATERMARK ===

def create_text_watermark(
    text: str,
    font_path: Optional[str],
    size_pt: int,
    color_hex: str
) -> Optional[Image.Image]:
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
        wm = Image.new('RGBA', (w + padding * 2, h + padding * 2), (0, 0, 0, 0))
        ImageDraw.Draw(wm).text((padding, padding), text, font=font, fill=rgb + (255,))
        return wm
    except Exception as e:
        logger.error(f"Text watermark creation failed: {e}")
        return None


def apply_opacity(image: Image.Image, opacity: float) -> Image.Image:
    """Apply opacity to image"""
    if opacity >= 1.0:
        return image
    try:
        alpha = image.split()[3]
        alpha = ImageEnhance.Brightness(alpha).enhance(max(0.0, min(1.0, opacity)))
        image.putalpha(alpha)
        return image
    except Exception as e:
        logger.error(f"Opacity failed: {e}")
        return image


# === MAIN PROCESSING ===

def process_image(
    file_path: str,
    filename: str,
    wm_obj: Optional[Image.Image],
    resize_config: Dict,
    output_fmt: str,
    quality: int,
    cancel_token: Optional[CancellationToken] = None
) -> Tuple[bytes, Dict]:
    """
    Process image with watermark and resize.

    Args:
        file_path:      Шлях до вхідного файлу
        filename:       Ім'я вихідного файлу
        wm_obj:         Готовий PIL Image вотермарки (або None)
        resize_config:  Словник налаштувань resize/watermark
        output_fmt:     'JPEG' | 'WEBP' | 'PNG'
        quality:        Якість 50–100
        cancel_token:   Токен скасування (перевіряється до початку важкої роботи)

    Raises:
        InterruptedError: якщо обробку скасовано через cancel_token
    """
    if cancel_token and cancel_token.is_cancelled():
        raise InterruptedError(f"Processing cancelled before: {filename}")

    try:
        validate_image_file(file_path)

        with Image.open(file_path) as img_temp:
            img = ImageOps.exif_transpose(img_temp)
            exif_data = img.info.get('exif')
            orig_w, orig_h = img.size
            orig_size = os.path.getsize(file_path)
            img = img.convert("RGBA")

        # Перевірка скасування після відкриття файлу
        if cancel_token and cancel_token.is_cancelled():
            raise InterruptedError(f"Processing cancelled: {filename}")

        new_w, new_h, scale_factor = _calculate_resize(orig_w, orig_h, resize_config)

        if scale_factor != 1.0:
            img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

        if wm_obj:
            img = _apply_watermark(img, wm_obj, resize_config)

        result_bytes = _export_image(img, output_fmt, quality, exif_data)

        stats = {
            "filename": filename,
            "orig_res": f"{orig_w}x{orig_h}",
            "new_res": f"{new_w}x{new_h}",
            "orig_size": orig_size,
            "new_size": len(result_bytes),
            "scale_factor": f"{scale_factor:.2f}x"
        }

        return result_bytes, stats

    except InterruptedError:
        raise
    except Exception as e:
        logger.error(f"Processing failed for {file_path}: {e}", exc_info=True)
        raise


def _calculate_resize(orig_w: int, orig_h: int, config_dict: Dict) -> Tuple[int, int, float]:
    """Calculate new dimensions"""
    if not config_dict.get('enabled', False):
        return orig_w, orig_h, 1.0

    val = config_dict.get('value', 1920)
    mode = config_dict.get('mode', 'Max Side')
    sf = 1.0

    if mode == "Max Side" and (orig_w > val or orig_h > val):
        sf = val / orig_w if orig_w >= orig_h else val / orig_h
    elif mode == "Exact Width":
        sf = val / orig_w
    elif mode == "Exact Height":
        sf = val / orig_h

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

        if pos == 'tiled':
            return _apply_tiled_watermark(img, wm_res, config_dict)
        else:
            return _apply_corner_watermark(img, wm_res, pos, config_dict)

    except Exception as e:
        logger.error(f"WM apply failed: {e}")
        return img


def _apply_tiled_watermark(img: Image.Image, wm: Image.Image, config_dict: Dict) -> Image.Image:
    """Apply tiled pattern with fix for vertical images"""
    gap = config_dict.get('wm_gap', 30)
    nw, nh = img.size
    wm_w, wm_h = wm.size

    overlay = Image.new('RGBA', (nw, nh), (0, 0, 0, 0))
    step_x = max(10, wm_w + gap)
    step_y = max(10, wm_h + gap)

    base_rows = (nh // step_y) + 2
    base_cols = (nw // step_x) + 2

    col_shift_offset = (base_rows // 2) + 3
    start_row, end_row = -2, base_rows + 2
    start_col, end_col = -col_shift_offset, base_cols + col_shift_offset

    for row in range(start_row, end_row):
        for col in range(start_col, end_col):
            x = col * step_x + (row * step_x // 2)
            y = row * step_y
            if x + wm_w > 0 and x < nw and y + wm_h > 0 and y < nh:
                overlay.paste(wm, (x, y), wm)

    return Image.alpha_composite(img, overlay)


def _apply_corner_watermark(
    img: Image.Image,
    wm: Image.Image,
    pos: str,
    config_dict: Dict
) -> Image.Image:
    """Apply watermark to specific position"""
    margin = config_dict.get('wm_margin', 15)
    nw, nh = img.size
    ww, wh = wm.size

    positions = {
        'bottom-right': (nw - ww - margin, nh - wh - margin),
        'bottom-left':  (margin,            nh - wh - margin),
        'top-right':    (nw - ww - margin,  margin),
        'top-left':     (margin,            margin),
        'center':       ((nw - ww) // 2,    (nh - wh) // 2),
    }
    px, py = positions.get(pos, (margin, margin))
    img.paste(wm, (max(0, min(px, nw - ww)), max(0, min(py, nh - wh))), wm)
    return img


def _export_image(
    img: Image.Image,
    fmt: str,
    qual: int,
    exif: Optional[bytes]
) -> bytes:
    """Export PIL image to bytes in chosen format"""
    if fmt == "JPEG":
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[3])
        img = bg
    elif fmt == "RGB":
        img = img.convert("RGB")

    buf = io.BytesIO()
    sk: Dict = {"format": fmt}

    if exif and fmt in ("JPEG", "WEBP"):
        sk['exif'] = exif

    if fmt == "JPEG":
        sk.update({"quality": qual, "optimize": True, "subsampling": 0})
    elif fmt == "WEBP":
        sk.update({"quality": qual, "method": 6})
    elif fmt == "PNG":
        sk.update({"optimize": True})

    img.save(buf, **sk)
    return buf.getvalue()
