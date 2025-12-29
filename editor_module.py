"""
Watermarker Pro v7.0 - Editor Module
=====================================
Image editing dialog with crop and rotate
"""

import streamlit as st
import os
from typing import Optional, Tuple
from PIL import Image, ImageOps
from streamlit_cropper import st_cropper
import config
from logger import get_logger
from validators import validate_image_file, validate_dimensions

logger = get_logger(__name__)

def get_file_info_str(fpath: str, img: Image.Image) -> str:
    """
    Generate file info string for display
    
    Args:
        fpath: File path
        img: PIL Image
        
    Returns:
        Formatted info string
    """
    try:
        size_bytes = os.path.getsize(fpath)
        size_mb = size_bytes / (1024 * 1024)
        
        if size_mb >= 1:
            size_str = f"{size_mb:.2f} MB"
        else:
            size_str = f"{size_bytes/1024:.1f} KB"
        
        filename = os.path.basename(fpath)
        return f"📄 **{filename}** &nbsp;•&nbsp; 📏 **{img.width}x{img.height}** &nbsp;•&nbsp; 💾 **{size_str}**"
    
    except Exception as e:
        logger.error(f"Failed to generate file info: {e}")
        return "📄 File info unavailable"

def create_proxy_image(
    img: Image.Image,
    target_width: int = None
) -> Tuple[Image.Image, float]:
    """
    Create proxy (downscaled) image for editor performance
    
    Args:
        img: Original PIL Image
        target_width: Target width in pixels
        
    Returns:
        Tuple of (proxy_image, scale_factor)
    """
    if target_width is None:
        target_width = config.PROXY_IMAGE_WIDTH
    
    try:
        w, h = img.size
        
        if w <= target_width:
            return img, 1.0
        
        # Calculate scale
        ratio = target_width / w
        new_h = max(1, int(h * ratio))
        
        # Validate
        validate_dimensions(target_width, new_h)
        
        # Resize
        proxy = img.resize(
            (target_width, new_h),
            Image.Resampling.LANCZOS
        )
        
        scale = w / target_width
        logger.debug(f"Proxy created: {w}x{h} → {target_width}x{new_h} (scale: {scale:.2f})")
        
        return proxy, scale
    
    except Exception as e:
        logger.error(f"Proxy creation failed: {e}")
        return img, 1.0

def get_max_box(
    img_w: int,
    img_h: int,
    aspect_data: Optional[Tuple[int, int]]
) -> Tuple[int, int, int, int]:
    """
    Calculate maximum crop box for given aspect ratio
    
    Args:
        img_w: Image width
        img_h: Image height
        aspect_data: Aspect ratio tuple (w, h) or None
        
    Returns:
        Crop box tuple (left, top, width, height)
    """
    try:
        if aspect_data is None:
            pad = 10
            return (
                pad,
                pad,
                max(10, img_w - 2*pad),
                max(10, img_h - 2*pad)
            )
        
        # Calculate ratio
        ratio_w, ratio_h = aspect_data
        if ratio_w == 0 or ratio_h == 0:
            logger.warning(f"Invalid aspect ratio: {aspect_data}")
            return (0, 0, img_w, img_h)
        
        ratio_val = ratio_w / ratio_h
        
        # Try to fit by width
        try_w = img_w
        try_h = int(try_w / ratio_val)
        
        if try_h > img_h:
            # Doesn't fit, try by height
            try_h = img_h
            try_w = int(try_h * ratio_val)
        
        # Ensure positive dimensions
        try_w = max(10, min(try_w, img_w))
        try_h = max(10, min(try_h, img_h))
        
        # Center the box
        left = (img_w - try_w) // 2
        top = (img_h - try_h) // 2
        
        return (left, top, try_w, try_h)
    
    except Exception as e:
        logger.error(f"Max box calculation failed: {e}")
        return (0, 0, img_w, img_h)

@st.dialog("🛠 Editor", width="large")
def open_editor_dialog(fpath: str, T: dict):
    """
    Open image editor dialog
    
    Args:
        fpath: Path to image file
        T: Translation dictionary
    """
    try:
        # Validate file
        validate_image_file(fpath)
        
        file_id = os.path.basename(fpath)
        
        # Initialize state
        if f'rot_{file_id}' not in st.session_state:
            st.session_state[f'rot_{file_id}'] = 0
        
        if f'reset_{file_id}' not in st.session_state:
            st.session_state[f'reset_{file_id}'] = 0
        
        if f'def_coords_{file_id}' not in st.session_state:
            st.session_state[f'def_coords_{file_id}'] = None
        
        # Load original image
        try:
            with Image.open(fpath) as img_temp:
                img_full = ImageOps.exif_transpose(img_temp)
                img_full = img_full.convert('RGB')
            
            # Apply rotation if needed
            angle = st.session_state[f'rot_{file_id}']
            if angle != 0:
                img_full = img_full.rotate(
                    -angle,
                    expand=True,
                    resample=Image.BICUBIC
                )
        
        except Exception as e:
            st.error(f"❌ Error loading image: {e}")
            logger.error(f"Image load failed: {e}")
            return
        
        # Create proxy for performance
        img_proxy, scale_factor = create_proxy_image(img_full)
        proxy_w, proxy_h = img_proxy.size
        
        # Display file info
        st.caption(get_file_info_str(fpath, img_full))
        
        # Layout
        col_canvas, col_controls = st.columns([3, 1], gap="small")
        
        # === CONTROLS ===
        with col_controls:
            st.markdown("**🔄 Rotate**")
            
            # Rotation buttons
            c1, c2 = st.columns(2)
            with c1:
                if st.button(
                    "↺ -90°",
                    use_container_width=True,
                    key=f"rot_left_{file_id}"
                ):
                    st.session_state[f'rot_{file_id}'] -= 90
                    st.session_state[f'reset_{file_id}'] += 1
                    # st.session_state[f'def_coords_{file_id}'] = None  <-- ЦЕ БІЛЬШЕ НЕ ПОТРІБНО
                    st.rerun()
            
            with c2:
                if st.button(
                    "↻ +90°",
                    use_container_width=True,
                    key=f"rot_right_{file_id}"
                ):
                    st.session_state[f'rot_{file_id}'] += 90
                    st.session_state[f'reset_{file_id}'] += 1
                    # st.session_state[f'def_coords_{file_id}'] = None  <-- ЦЕ БІЛЬШЕ НЕ ПОТРІБНО
                    st.rerun()
            
            st.divider()
            st.markdown("**✂️ Crop**")
            
            # Aspect ratio selection
            aspect_choice = st.selectbox(
                T.get('lbl_aspect', 'Aspect Ratio'),
                list(config.ASPECT_RATIOS.keys()),
                label_visibility="collapsed",
                key=f"asp_{file_id}"
            )
            aspect_val = config.ASPECT_RATIOS[aspect_choice]
            
            # --- ВИДАЛЕНО КНОПКУ MAX ---
            
            st.divider()
        
        # === CANVAS ===
        with col_canvas:
            cropper_id = f"crp_{file_id}_{st.session_state[f'reset_{file_id}']}_{aspect_choice}"
            
            # [ВИПРАВЛЕННЯ] Примусово розраховуємо MAX рамку для поточних умов
            # Ми передаємо це значення як default_coords. 
            # Кропер використає його ТІЛЬКИ при ініціалізації (коли змінюється cropper_id).
            # При звичайному редагуванні (коли id той самий) він ігнорує це і зберігає ручні зміни користувача.
            default_max_box = get_max_box(proxy_w, proxy_h, aspect_val)
            
            try:
                rect = st_cropper(
                    img_proxy,
                    realtime_update=True,
                    box_color='#FF0000',
                    aspect_ratio=aspect_val,
                    should_resize_image=False,
                    default_coords=default_max_box, # <-- ПЕРЕДАЄМО ЯВНО РОЗРАХОВАНУ РАМКУ
                    return_type='box',
                    key=cropper_id
                )
            except Exception as e:
                st.error(f"Cropper error: {e}")
                logger.error(f"Cropper failed: {e}")
                rect = None
        
        # === CROP INFO & SAVE ===
        with col_controls:
            crop_box = None
            real_w, real_h = 0, 0
            
            if rect:
                try:
                    # Scale coordinates back to original
                    left = int(rect['left'] * scale_factor)
                    top = int(rect['top'] * scale_factor)
                    width = int(rect['width'] * scale_factor)
                    height = int(rect['height'] * scale_factor)
                    
                    # Clamp to image bounds
                    orig_w, orig_h = img_full.size
                    left = max(0, left)
                    top = max(0, top)
                    
                    if left + width > orig_w:
                        width = orig_w - left
                    if top + height > orig_h:
                        height = orig_h - top
                    
                    # Ensure positive dimensions
                    width = max(1, width)
                    height = max(1, height)
                    
                    crop_box = (left, top, left + width, top + height)
                    real_w, real_h = width, height
                
                except Exception as e:
                    logger.error(f"Crop calculation failed: {e}")
            
            # Display dimensions
            st.info(f"📏 **{real_w} × {real_h}** px")
            
            # Save button
            if st.button(
                T.get('btn_save_edit', '💾 Save'),
                type="primary",
                use_container_width=True,
                key=f"save_{file_id}"
            ):
                try:
                    if crop_box:
                        # Crop image
                        final_image = img_full.crop(crop_box)
                        
                        # Save with high quality
                        final_image.save(
                            fpath,
                            quality=95,
                            subsampling=0,
                            optimize=True
                        )
                        
                        # Remove thumbnail cache
                        thumb_path = f"{fpath}.thumb.jpg"
                        if os.path.exists(thumb_path):
                            try:
                                os.remove(thumb_path)
                            except Exception:
                                pass
                        
                        # Clean up state
                        keys_to_delete = [
                            f'rot_{file_id}',
                            f'reset_{file_id}',
                            f'def_coords_{file_id}'
                        ]
                        for k in keys_to_delete:
                            if k in st.session_state:
                                del st.session_state[k]
                        
                        st.session_state['close_editor'] = True
                        st.toast(T.get('msg_edit_saved', '✅ Changes saved!'))
                        logger.info(f"Image edited and saved: {fpath}")
                        st.rerun()
                    else:
                        st.warning("No crop area selected")
                
                except Exception as e:
                    st.error(f"❌ Save failed: {e}")
                    logger.error(f"Save failed: {e}", exc_info=True)
    
    except Exception as e:
        st.error(f"❌ Editor error: {e}")
        logger.error(f"Editor dialog failed: {e}", exc_info=True)
