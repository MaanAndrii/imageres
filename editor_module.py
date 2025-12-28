"""
Watermarker Pro v7.0 - Editor Module
=====================================
Image editing dialog with crop and rotate
"""

import streamlit as st
import os
from typing import Optional, Tuple, Dict
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

def calculate_max_crop_box(
    img_w: int,
    img_h: int,
    aspect_ratio: Optional[Tuple[int, int]]
) -> Dict[str, int]:
    """
    Calculate maximum crop box for given aspect ratio
    Returns box in format compatible with st_cropper default_coords
    
    Args:
        img_w: Image width
        img_h: Image height
        aspect_ratio: Aspect ratio tuple (w, h) or None
        
    Returns:
        Dict with keys: left, top, width, height
    """
    try:
        if aspect_ratio is None:
            # Free aspect - максимальна область з відступом
            pad = 5
            return {
                'left': pad,
                'top': pad,
                'width': max(10, img_w - 2 * pad),
                'height': max(10, img_h - 2 * pad)
            }
        
        ratio_w, ratio_h = aspect_ratio
        if ratio_w == 0 or ratio_h == 0:
            logger.warning(f"Invalid aspect ratio: {aspect_ratio}")
            return {'left': 0, 'top': 0, 'width': img_w, 'height': img_h}
        
        ratio_val = ratio_w / ratio_h
        
        # Спочатку пробуємо вписати по ширині (використати ВСЮ ширину)
        crop_w = img_w
        crop_h = int(crop_w / ratio_val)
        
        if crop_h > img_h:
            # Не влізло по висоті - вписуємо по висоті (використати ВСЮ висоту)
            crop_h = img_h
            crop_w = int(crop_h * ratio_val)
        
        # Гарантуємо що розміри в межах зображення
        crop_w = max(10, min(crop_w, img_w))
        crop_h = max(10, min(crop_h, img_h))
        
        # Центруємо рамку
        left = (img_w - crop_w) // 2
        top = (img_h - crop_h) // 2
        
        # Гарантуємо що координати в межах
        left = max(0, min(left, img_w - crop_w))
        top = max(0, min(top, img_h - crop_h))
        
        result = {
            'left': left,
            'top': top,
            'width': crop_w,
            'height': crop_h
        }
        
        logger.debug(
            f"MAX box calculated: {crop_w}x{crop_h} at ({left}, {top}) "
            f"for image {img_w}x{img_h}, ratio {ratio_w}:{ratio_h}"
        )
        
        return result
    
    except Exception as e:
        logger.error(f"Max box calculation failed: {e}")
        return {'left': 0, 'top': 0, 'width': img_w, 'height': img_h}

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
        
        if f'crop_box_{file_id}' not in st.session_state:
            st.session_state[f'crop_box_{file_id}'] = None
        
        if f'history_{file_id}' not in st.session_state:
            st.session_state[f'history_{file_id}'] = []
        
        if f'history_index_{file_id}' not in st.session_state:
            st.session_state[f'history_index_{file_id}'] = -1
        
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
            
            # Rotation buttons with Undo/Redo
            c1, c2, c3, c4 = st.columns(4)
            
            with c1:
                if st.button(
                    "↺",
                    use_container_width=True,
                    key=f"rot_left_{file_id}",
                    help="Rotate -90°"
                ):
                    # Save to history
                    history = st.session_state[f'history_{file_id}']
                    history.append({
                        'type': 'rotate',
                        'angle': st.session_state[f'rot_{file_id}'],
                        'crop_box': st.session_state[f'crop_box_{file_id}']
                    })
                    st.session_state[f'history_index_{file_id}'] = len(history) - 1
                    
                    st.session_state[f'rot_{file_id}'] -= 90
                    st.session_state[f'reset_{file_id}'] += 1
                    st.session_state[f'crop_box_{file_id}'] = None
                    st.rerun()
            
            with c2:
                if st.button(
                    "↻",
                    use_container_width=True,
                    key=f"rot_right_{file_id}",
                    help="Rotate +90°"
                ):
                    # Save to history
                    history = st.session_state[f'history_{file_id}']
                    history.append({
                        'type': 'rotate',
                        'angle': st.session_state[f'rot_{file_id}'],
                        'crop_box': st.session_state[f'crop_box_{file_id}']
                    })
                    st.session_state[f'history_index_{file_id}'] = len(history) - 1
                    
                    st.session_state[f'rot_{file_id}'] += 90
                    st.session_state[f'reset_{file_id}'] += 1
                    st.session_state[f'crop_box_{file_id}'] = None
                    st.rerun()
            
            with c3:
                # Undo button
                history_idx = st.session_state[f'history_index_{file_id}']
                can_undo = history_idx >= 0
                if st.button(
                    "⎌",
                    use_container_width=True,
                    key=f"undo_{file_id}",
                    disabled=not can_undo,
                    help="Undo"
                ):
                    history = st.session_state[f'history_{file_id}']
                    if history_idx >= 0:
                        prev_state = history[history_idx]
                        st.session_state[f'rot_{file_id}'] = prev_state['angle']
                        st.session_state[f'crop_box_{file_id}'] = prev_state['crop_box']
                        st.session_state[f'history_index_{file_id}'] -= 1
                        st.session_state[f'reset_{file_id}'] += 1
                        st.rerun()
            
            with c4:
                # Reset button
                if st.button(
                    "⟲",
                    use_container_width=True,
                    key=f"reset_all_{file_id}",
                    help="Reset all"
                ):
                    st.session_state[f'rot_{file_id}'] = 0
                    st.session_state[f'crop_box_{file_id}'] = None
                    st.session_state[f'history_{file_id}'] = []
                    st.session_state[f'history_index_{file_id}'] = -1
                    st.session_state[f'reset_{file_id}'] += 1
                    st.toast("Reset completed")
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
            
            st.divider()
            
            # MAX button - fix emoji issue
            if st.button(
                "MAX",
                use_container_width=True,
                key=f"max_{file_id}",
                help="Максимальна область у вибраному співвідношенні"
            ):
                try:
                    # Calculate MAX box for PROXY image
                    max_box = calculate_max_crop_box(proxy_w, proxy_h, aspect_val)
                    
                    if max_box:
                        st.session_state[f'crop_box_{file_id}'] = max_box
                        st.session_state[f'reset_{file_id}'] += 1
                        
                        # Calculate real dimensions for display
                        real_w = int(max_box['width'] * scale_factor)
                        real_h = int(max_box['height'] * scale_factor)
                        
                        if aspect_val:
                            ratio_str = f"{aspect_val[0]}:{aspect_val[1]}"
                        else:
                            ratio_str = "free"
                        
                        st.toast(f"MAX: {real_w}x{real_h}px ({ratio_str})")
                        logger.info(f"MAX activated: {real_w}x{real_h} ({ratio_str})")
                        st.rerun()
                except Exception as e:
                    st.error(f"MAX error: {e}")
                    logger.error(f"MAX button failed: {e}", exc_info=True)
        
        # === CANVAS ===
        with col_canvas:
            cropper_id = f"crp_{file_id}_{st.session_state[f'reset_{file_id}']}_{aspect_choice}"
            default_box = st.session_state.get(f'crop_box_{file_id}', None)
            
            try:
                rect = st_cropper(
                    img_proxy,
                    realtime_update=True,
                    box_color='#FF0000',
                    aspect_ratio=aspect_val,
                    should_resize_image=False,
                    default_coords=default_box,
                    return_type='box',
                    key=cropper_id
                )
                
            except Exception as e:
                st.error(f"Cropper error: {e}")
                logger.error(f"Cropper failed: {e}", exc_info=True)
                rect = None
        
        # === CROP INFO & SAVE ===
        with col_controls:
            crop_box = None
            real_w, real_h = 0, 0
            
            if rect:
                try:
                    # rect містить координати PROXY зображення
                    left = int(rect['left'] * scale_factor)
                    top = int(rect['top'] * scale_factor)
                    width = int(rect['width'] * scale_factor)
                    height = int(rect['height'] * scale_factor)
                    
                    # Clamp до меж ОРИГІНАЛЬНОГО зображення
                    orig_w, orig_h = img_full.size
                    
                    left = max(0, min(left, orig_w))
                    top = max(0, min(top, orig_h))
                    
                    # Якщо рамка виходить за межі - обрізаємо розмір
                    if left + width > orig_w:
                        width = orig_w - left
                    if top + height > orig_h:
                        height = orig_h - top
                    
                    # Гарантуємо позитивні розміри
                    width = max(1, width)
                    height = max(1, height)
                    
                    # Crop box для PIL (left, top, right, bottom)
                    crop_box = (left, top, left + width, top + height)
                    real_w, real_h = width, height
                    
                    logger.debug(
                        f"Crop calculated: proxy ({rect['left']:.0f}, {rect['top']:.0f}, "
                        f"{rect['width']:.0f}x{rect['height']:.0f}) → "
                        f"original ({left}, {top}, {width}x{height})"
                    )
                
                except Exception as e:
                    logger.error(f"Crop calculation failed: {e}")
                    st.warning(f"⚠️ Помилка розрахунку: {e}")
            
            # Manual size input with current values
            st.markdown("**📐 Manual Size (px)**")
            
            # Use current rect dimensions or defaults
            if real_w > 0 and real_h > 0:
                default_w = real_w
                default_h = real_h
            else:
                default_w = min(1000, img_full.width)
                default_h = min(750, img_full.height)
            
            col_w, col_h = st.columns(2)
            
            with col_w:
                manual_width = st.number_input(
                    "Width",
                    min_value=10,
                    max_value=img_full.width,
                    value=default_w,
                    step=10,
                    key=f"manual_w_{file_id}_{st.session_state[f'reset_{file_id}']}",
                    label_visibility="collapsed"
                )
            
            with col_h:
                manual_height = st.number_input(
                    "Height",
                    min_value=10,
                    max_value=img_full.height,
                    value=default_h,
                    step=10,
                    key=f"manual_h_{file_id}_{st.session_state[f'reset_{file_id}']}",
                    label_visibility="collapsed"
                )
            
            # Apply manual size button
            if st.button(
                "✓ Apply",
                use_container_width=True,
                key=f"apply_manual_{file_id}",
                help="Set crop box to specified dimensions"
            ):
                try:
                    # Scale to proxy coordinates
                    proxy_width = int(manual_width / scale_factor)
                    proxy_height = int(manual_height / scale_factor)
                    
                    # Validate dimensions
                    if proxy_width <= 0 or proxy_height <= 0:
                        st.error("Invalid dimensions")
                    elif proxy_width > proxy_w or proxy_height > proxy_h:
                        st.error(f"Too large. Max: {img_full.width}×{img_full.height}")
                    else:
                        # Center the box
                        left = max(0, (proxy_w - proxy_width) // 2)
                        top = max(0, (proxy_h - proxy_height) // 2)
                        
                        # Ensure it fits
                        if left + proxy_width > proxy_w:
                            left = proxy_w - proxy_width
                        if top + proxy_height > proxy_h:
                            top = proxy_h - proxy_height
                        
                        st.session_state[f'crop_box_{file_id}'] = {
                            'left': left,
                            'top': top,
                            'width': proxy_width,
                            'height': proxy_height
                        }
                        st.session_state[f'reset_{file_id}'] += 1
                        st.toast(f"Set: {manual_width}x{manual_height}px")
                        st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")
                    logger.error(f"Apply manual size failed: {e}", exc_info=True)
            
            st.divider()
            
            # Display dimensions (оригінальні розміри!)
            if real_w > 0 and real_h > 0:
                st.info(f"📏 **{real_w} × {real_h}** px")
            else:
                st.info("📏 **Drag to select area**")
        
        # === CROP INFO & SAVE ===
        with col_controls:
            crop_box = None
            real_w, real_h = 0, 0
            
            if rect:
                try:
                    # rect містить координати PROXY зображення
                    # scale_factor = оригінал_width / proxy_width
                    # Множимо на scale_factor для отримання координат оригіналу
                    
                    left = int(rect['left'] * scale_factor)
                    top = int(rect['top'] * scale_factor)
                    width = int(rect['width'] * scale_factor)
                    height = int(rect['height'] * scale_factor)
                    
                    # Clamp до меж ОРИГІНАЛЬНОГО зображення
                    orig_w, orig_h = img_full.size
                    
                    left = max(0, min(left, orig_w))
                    top = max(0, min(top, orig_h))
                    
                    # Якщо рамка виходить за межі - обрізаємо розмір
                    if left + width > orig_w:
                        width = orig_w - left
                    if top + height > orig_h:
                        height = orig_h - top
                    
                    # Гарантуємо позитивні розміри
                    width = max(1, width)
                    height = max(1, height)
                    
                    # Crop box для PIL (left, top, right, bottom)
                    crop_box = (left, top, left + width, top + height)
                    real_w, real_h = width, height
                    
                    logger.debug(
                        f"Crop calculated: proxy ({rect['left']:.0f}, {rect['top']:.0f}, "
                        f"{rect['width']:.0f}x{rect['height']:.0f}) → "
                        f"original ({left}, {top}, {width}x{height})"
                    )
                
                except Exception as e:
                    logger.error(f"Crop calculation failed: {e}")
                    st.warning(f"⚠️ Помилка розрахунку: {e}")
            
            # Display dimensions (оригінальні розміри!)
            if real_w > 0 and real_h > 0:
                st.info(f"📏 **{real_w} × {real_h}** px")
            else:
                st.info("📏 **Оберіть область**")
            
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
                            f'crop_box_{file_id}',
                            f'history_{file_id}',
                            f'history_index_{file_id}'
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
