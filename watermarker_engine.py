"""
Watermarker Pro v7.0.1 - Engine Module
=====================================
Core image processing with PDF support and enhanced error reporting
"""

import io
import os
import re
import base64
from typing import Optional, Tuple, Dict, List
from PIL import Image, ImageEnhance, ImageOps, ImageDraw, ImageFont
from translitua import translit
import config
from logger import get_logger
from validators import (
    validate_image_file, validate_dimensions, 
    validate_scale_factor, safe_divide, validate_color_hex
)

# Спроба імпорту pdf2image та обробка відсутності бібліотеки
try:
    from pdf2image import convert_from_path
    from pdf2image.exceptions import PDFInfoNotInstalledError, PDFPageCountError
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False

logger = get_logger(__name__)
_font_cache: Dict[Tuple[str, int], ImageFont.FreeTypeFont] = {}

# === PDF CONVERSION ===
def convert_pdf_to_images(pdf_path: str, dpi: int = None) -> List[Image.Image]:
    """
    Конвертує сторінки PDF у список об'єктів PIL Image.
    Генерує виключення для відображення в UI.
    """
    if not PDF_SUPPORT:
        raise ImportError("Бібліотека 'pdf2image' не встановлена. Виконайте: pip install pdf2image")
    
    dpi = dpi or config.PDF_CONVERSION_DPI
    try:
        images = convert_from_path(pdf_path, dpi=dpi)
        if not images:
            raise ValueError("PDF файл порожній або не містить сторінок.")
        logger.info(f"PDF converted: {pdf_path} ({len(images)} pages)")
        return images
    
    except PDFInfoNotInstalledError:
        # Специфічна помилка відсутності Poppler
        error_msg = "Системна утиліта Poppler не знайдена. Перевірте встановлення Poppler та змінну PATH."
        logger.error(error_msg)
        raise RuntimeError(error_msg)
    
    except PDFPageCountError:
        error_msg = "Неможливо прочитати кількість сторінок PDF. Файл може бути пошкоджений або захищений паролем."
        logger.error(error_msg)
        raise ValueError(error_msg)
    
    except Exception as e:
        error_msg = f"Помилка конвертації PDF: {str(e)}"
        logger.error(error_msg)
        raise Exception(error_msg)

# === ENCODING ===
def image_to_base64(image_bytes: bytes) -> str:
    return base64.b64encode(image_bytes).decode('utf-8')

def base64_to_bytes(base64_string: str) -> bytes:
    return base64.b64decode(base64_string)

# === FILENAME GENERATION ===
def generate_filename(original_path: str, naming_mode: str, prefix: str = "", extension: str = "jpg", index: int = 1) -> str:
    try:
        original_name = os.path.basename(original_path)
        clean_prefix = re.sub(r'[\s\W_]+', '-', translit(prefix).lower()).strip('-') if prefix else ""
        
        if naming_mode == "Prefix + Sequence":
            base = clean_prefix if clean_prefix else "image"
            return f"{base}_{index:03d}.{extension}"
        
        name_only = os.path.splitext(original_name)[0]
        slug = re.sub(r'[\s\W_]+', '-', translit(name_only).lower()).strip('-') or "image"
        base = f"{clean_prefix}_{slug}" if clean_prefix else slug
        return f"{base}.{extension}"
    except Exception:
        return f"output_{index:03d}.{extension}"

# === THUMBNAIL ===
def get_thumbnail(file_path: str, size: Tuple[int, int] = None) -> Optional[str]:
    size = size or config.THUMBNAIL_SIZE
    thumb_path = f"{file_path}.thumb.jpg"
    try:
        if os.path.exists(thumb_path) and os.path.getmtime(thumb_path) > os.path.getmtime(file_path):
            return thumb_path
        with Image.open(file_path) as img:
            img = ImageOps.exif_transpose(img).convert('RGB')
            img.thumbnail(size, Image.Resampling.LANCZOS)
            img.save(thumb_path, "JPEG", quality=70, optimize=True)
        return thumb_path
    except Exception:
        return None

# === ROTATION ===
def rotate_image_file(file_path: str, angle: int) -> bool:
    try:
        validate_image_file(file_path)
        with Image.open(file_path) as img_temp:
            img = ImageOps.exif_transpose(img_temp)
            exif_data = img.info.get('exif')
            rotated = img.rotate(-angle, expand=True, resample=Image.BICUBIC)
            save_kwargs = {"quality": 95, "subsampling": 0}
            if exif_data: save_kwargs['exif'] = exif_data
            rotated.save(file_path, **save_kwargs)
        if os.path.exists(f"{file_path}.thumb.jpg"): os.remove(f"{file_path}.thumb.jpg")
        return True
    except Exception:
        return False

# === WATERMARK LOGIC ===
def load_watermark_from_bytes(wm_bytes: bytes) -> Image.Image:
    return Image.open(io.BytesIO(wm_bytes)).convert("RGBA")

def get_cached_font(font_path: str, size: int) -> ImageFont.FreeTypeFont:
    cache_key = (font_path, size)
    if cache_key not in _font_cache:
        try: _font_cache[cache_key] = ImageFont.truetype(font_path, size)
        except Exception: _font_cache[cache_key] = ImageFont.load_default()
    return _font_cache[cache_key]

def create_text_watermark(text: str, font_path: Optional[str], size_pt: int, color_hex: str) -> Optional[Image.Image]:
    if not text or not text.strip(): return None
    font = get_cached_font(font_path, size_pt) if font_path else ImageFont.load_default()
    rgb = validate_color_hex(color_hex)
    dummy = Image.new('RGBA', (1, 1))
    bbox = ImageDraw.Draw(dummy).textbbox((0, 0), text, font=font)
    w, h = bbox[2]-bbox[0], bbox[3]-bbox[1]
    padding = 20
    wm = Image.new('RGBA', (w + padding*2, h + padding*2), (0, 0, 0, 0))
    ImageDraw.Draw(wm).text((padding, padding), text, font=font, fill=rgb + (255,))
    return wm

def apply_opacity(image: Image.Image, opacity: float) -> Image.Image:
    if opacity >= 1.0: return image
    alpha = image.split()[3]
    alpha = ImageEnhance.Brightness(alpha).enhance(max(0.0, min(1.0, opacity)))
    image.putalpha(alpha)
    return image

# === PROCESSING ===
def process_image(file_path: str, filename: str, wm_obj: Optional[Image.Image], resize_cfg: Dict, out_fmt: str, quality: int) -> Tuple[bytes, Dict]:
    with Image.open(file_path) as img_temp:
        img = ImageOps.exif_transpose(img_temp)
        exif_data = img.info.get('exif')
        orig_w, orig_h = img.size
        orig_size = os.path.getsize(file_path)
        img = img.convert("RGBA")
    
    new_w, new_h, sf = _calculate_resize(orig_w, orig_h, resize_cfg)
    if sf != 1.0:
        img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
    
    if wm_obj:
        img = _apply_watermark(img, wm_obj, resize_cfg)
    
    result_bytes = _export_image(img, out_fmt, quality, exif_data)
    stats = {
        "filename": filename, "orig_res": f"{orig_w}x{orig_h}", "new_res": f"{new_w}x{new_h}",
        "orig_size": orig_size, "new_size": len(result_bytes), "scale_factor": f"{sf:.2f}x"
    }
    return result_bytes, stats

def _calculate_resize(orig_w, orig_h, cfg):
    if not cfg.get('enabled', False): return orig_w, orig_h, 1.0
    val = cfg.get('value', 1920); mode = cfg.get('mode', 'Max Side')
    sf = 1.0
    if mode == "Max Side" and (orig_w > val or orig_h > val):
        sf = val / orig_w if orig_w >= orig_h else val / orig_h
    elif mode == "Exact Width": sf = val / orig_w
    elif mode == "Exact Height": sf = val / orig_h
    return max(1, int(orig_w * sf)), max(1, int(orig_h * sf)), sf

def _apply_watermark(img, wm_obj, cfg):
    nw, nh = img.size
    scale = max(0.01, min(0.9, cfg.get('wm_scale', 0.15)))
    pos, angle = cfg.get('wm_position', 'bottom-right'), cfg.get('wm_angle', 0)
    
    target_w = max(10, int(nw * scale))
    target_h = max(10, int(wm_obj.height * (target_w / wm_obj.width)))
    
    wm_res = wm_obj.resize((target_w, target_h), Image.Resampling.LANCZOS)
    if angle != 0:
        wm_res = wm_res.rotate(angle, expand=True, resample=Image.BICUBIC)
    
    if pos == 'tiled': return _apply_tiled_watermark(img, wm_res, cfg)
    return _apply_corner_watermark(img, wm_res, pos, cfg)

def _apply_tiled_watermark(img: Image.Image, wm: Image.Image, cfg: Dict) -> Image.Image:
    gap = cfg.get('wm_gap', 30)
    nw, nh = img.size; wm_w, wm_h = wm.size
    overlay = Image.new('RGBA', (nw, nh), (0, 0, 0, 0))
    sx, sy = max(10, wm_w + gap), max(10, wm_h + gap)
    
    rows, cols = (nh // sy) + 2, (nw // sx) + 2
    shift_buffer = (rows // 2) + 3
    
    for r in range(-2, rows + 2):
        for c in range(-shift_buffer, cols + shift_buffer):
            x, y = c * sx + (r * sx // 2), r * sy
            if (x + wm_w > 0 and x < nw and y + wm_h > 0 and y < nh):
                overlay.paste(wm, (x, y), wm)
    return Image.alpha_composite(img, overlay)

def _apply_corner_watermark(img, wm, pos, cfg):
    margin = cfg.get('wm_margin', 15)
    nw, nh = img.size; ww, wh = wm.size
    if pos == 'bottom-right': px, py = nw-ww-margin, nh-wh-margin
    elif pos == 'bottom-left': px, py = margin, nh-wh-margin
    elif pos == 'top-right': px, py = nw-ww-margin, margin
    elif pos == 'top-left': px, py = margin, margin
    elif pos == 'center': px, py = (nw-ww)//2, (nh-wh)//2
    else: px, py = margin, margin
    img.paste(wm, (max(0, min(px, nw-ww)), max(0, min(py, nh-wh))), wm)
    return img

def _export_image(img, fmt, qual, exif):
    if fmt == "JPEG":
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[3]); img = bg
    buf = io.BytesIO()
    sk = {"format": fmt}
    if exif and fmt in ["JPEG", "WEBP"]: sk['exif'] = exif
    if fmt == "JPEG": sk.update({"quality": qual, "optimize": True, "subsampling": 0})
    elif fmt == "WEBP": sk.update({"quality": qual, "method": 6})
    elif fmt == "PNG": sk.update({"optimize": True})
    img.save(buf, **sk)
    return buf.getvalue()
