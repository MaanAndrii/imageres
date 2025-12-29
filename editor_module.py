"""
Watermarker Pro v7.0 - Editor Module
=====================================
Image editing dialog with crop and rotate
"""

import streamlit as st
import os
from typing import Optional, Tuple
from PIL import Image, ImageOps
from streamlit_cropper_fix import st_cropper
import config
from logger import get_logger
from validators import validate_image_file, validate_dimensions

logger = get_logger(__name__)

def get_file_info_str(fpath: str, img: Image.Image) -> str:
    """Generate file info string for display"""
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
    """Create proxy (downscaled) image for editor performance"""
    if target_width is None:
        target_width = config.PROXY_IMAGE_WIDTH
    
    try:
        w, h = img.size
        
        if w <= target_width:
            return img, 1.0
        
        ratio = target_width / w
        new_h = max(1, int(h * ratio))
        
        validate_dimensions(target_width, new_h)
        
        proxy = img.resize((target_width, new_h), Image.Resampling.LANCZOS)
        
        scale = w / target_width
        logger.debug(f"Proxy created: {w}x{h} → {target_width}x{new_h} (scale: {scale:.2f})")
        
        return proxy, scale
    
    except Exception as e:
        logger.error(f"Proxy creation failed: {e}")
        return img, 1.0

@st.dialog("🛠 Editor", width="large")
def open_editor_dialog(fpath: str, T: dict):
    """Open image editor dialog"""
    try:
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
            
            angle = st.session_state[f'rot_{file_id}']
            if angle != 0:
                img_full = img_full.rotate(-angle, expand=True, resample=Image.BICUBIC)
        
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
                if st.button("↺ -90°", use_container_width=True, key=f"rot_left_{file_id}"):
                    st.session_state[f'rot_{file_id}'] -= 90
                    st.session_state[f'reset_{file_id}'] += 1
                    st.session_state[f'def_coords_{file_id}'] = None
                    st.rerun()
            
            with c2:
                if st.button("↻ +90°", use_container_width=True, key=f"rot_right_{file_id}"):
                    st.session_state[f'rot_{file_id}'] += 90
                    st.session_state[f'reset_{file_id}'] += 1
                    st.session_state[f'def_coords_{file_id}'] = None
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
            
            # MAX button
            if st.button("MAX", use_container_width=True, key=f"max_{file_id}", help="Maximum crop area"):
                if aspect_val is None:
                    # Free aspect - full image with small padding
                    pad = 5
                    max_box = (pad, pad, proxy_w - 2*pad, proxy_h - 2*pad)
                else:
                    # Calculate max for aspect ratio
                    ratio = aspect_val[0] / aspect_val[1]
                    
                    # Try full width
                    max_w = proxy_w
                    max_h = int(max_w / ratio)
                    
                    if max_h > proxy_h:
                        # Use full height instead
                        max_h = proxy_h
                        max_w = int(max_h * ratio)
                    
                    # Center
                    left = (proxy_w - max_w) // 2
                    top = (proxy_h - max_h) // 2
                    
                    max_box = (left, top, max_w, max_h)
                
                st.session_state[f'def_coords_{file_id}'] = max_box
                st.session_state[f'reset_{file_id}'] += 1
                
                # Calculate real dimensions
                real_w = int(max_box[2] * scale_factor)
                real_h = int(max_box[3] * scale_factor)
                
                ratio_str = f"{aspect_val[0]}:{aspect_val[1]}" if aspect_val else "free"
                st.toast(f"MAX: {real_w}×{real_h}px ({ratio_str})")
                logger.info(f"MAX: {real_w}x{real_h} ({ratio_str})")
                st.rerun()
            
            st.divider()
        
        # === CANVAS ===
        with col_canvas:
            cropper_id = f"crp_{file_id}_{st.session_state[f'reset_{file_id}']}_{aspect_choice}"
            def_coords = st.session_state.get(f'def_coords_{file_id}', None)
            
            try:
                rect = st_cropper(
                    img_proxy,
                    realtime_update=True,
                    box_color='#FF0000',
                    aspect_ratio=aspect_val,
                    should_resize_image=False,
                    default_coords=def_coords,
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
                    left = int(rect['left'] * scale_factor)
                    top = int(rect['top'] * scale_factor)
                    width = int(rect['width'] * scale_factor)
                    height = int(rect['height'] * scale_factor)
                    
                    orig_w, orig_h = img_full.size
                    left = max(0, left)
                    top = max(0, top)
                    
                    if left + width > orig_w:
                        width = orig_w - left
                    if top + height > orig_h:
                        height = orig_h - top
                    
                    width = max(1, width)
                    height = max(1, height)
                    
                    crop_box = (left, top, left + width, top + height)
                    real_w, real_h = width, height
                
                except Exception as e:
                    logger.error(f"Crop calculation failed: {e}")
            
            st.info(f"📏 **{real_w} × {real_h}** px")
            
            if st.button(T.get('btn_save_edit', '💾 Save'), type="primary", use_container_width=True, key=f"sv_{file_id}"):
                try:
                    if crop_box:
                        final_image = img_full.crop(crop_box)
                        final_image.save(fpath, quality=95, subsampling=0)
                        
                        if os.path.exists(f"{fpath}.thumb.jpg"): 
                            os.remove(f"{fpath}.thumb.jpg")
                        
                        keys = [f'rot_{file_id}', f'reset_{file_id}', f'def_coords_{file_id}']
                        for k in keys:
                            if k in st.session_state: del st.session_state[k]
                        
                        st.session_state['close_editor'] = True
                        st.toast(T.get('msg_edit_saved', '✅ Saved!'))
                        st.rerun()
                except Exception as e:
                    st.error(f"Save Failed: {e}")
    
    except Exception as e:
        st.error(f"❌ Editor error: {e}")
        logger.error(f"Editor dialog failed: {e}", exc_info=True)

def get_file_info_str(fpath: str, img: Image.Image) -> str:
    """Generate file info string"""
    try:
        size_bytes = os.path.getsize(fpath)
        size_mb = size_bytes / (1024 * 1024)
        size_str = f"{size_mb:.2f} MB" if size_mb >= 1 else f"{size_bytes/1024:.1f} KB"
        filename = os.path.basename(fpath)
        return f"📄 **{filename}** • 📏 **{img.width}×{img.height}** • 💾 **{size_str}**"
    except Exception as e:
        logger.error(f"Failed to get file info: {e}")
        return "📄 File info unavailable"

def create_preview_with_box(img: Image.Image, left: int, top: int, width: int, height: int, max_width: int = 700) -> Image.Image:
    """Create preview image with crop box overlay"""
    try:
        # Scale image for preview
        scale = 1.0
        if img.width > max_width:
            scale = max_width / img.width
            new_h = int(img.height * scale)
            preview = img.resize((max_width, new_h), Image.Resampling.LANCZOS)
        else:
            preview = img.copy()
        
        # Draw crop box
        draw = ImageDraw.Draw(preview)
        
        # Scale coordinates
        box_left = int(left * scale)
        box_top = int(top * scale)
        box_right = int((left + width) * scale)
        box_bottom = int((top + height) * scale)
        
        # Draw rectangle
        draw.rectangle([box_left, box_top, box_right, box_bottom], outline='red', width=3)
        
        # Draw corners
        corner_size = 20
        for x, y in [(box_left, box_top), (box_right, box_top), (box_left, box_bottom), (box_right, box_bottom)]:
            draw.line([x-corner_size, y, x+corner_size, y], fill='red', width=3)
            draw.line([x, y-corner_size, x, y+corner_size], fill='red', width=3)
        
        return preview
    except Exception as e:
        logger.error(f"Preview creation failed: {e}")
        return img

@st.dialog("🛠 Editor", width="large")
def open_editor_dialog(fpath: str, T: dict):
    """Simple image editor with rotation and manual crop"""
    try:
        validate_image_file(fpath)
        file_id = os.path.basename(fpath)
        
        # Initialize state
        if f'rot_{file_id}' not in st.session_state:
            st.session_state[f'rot_{file_id}'] = 0
        if f'crop_left_{file_id}' not in st.session_state:
            st.session_state[f'crop_left_{file_id}'] = 0
        if f'crop_top_{file_id}' not in st.session_state:
            st.session_state[f'crop_top_{file_id}'] = 0
        if f'crop_width_{file_id}' not in st.session_state:
            st.session_state[f'crop_width_{file_id}'] = None
        if f'crop_height_{file_id}' not in st.session_state:
            st.session_state[f'crop_height_{file_id}'] = None
        
        # Load image
        try:
            with Image.open(fpath) as img_temp:
                img_full = ImageOps.exif_transpose(img_temp)
                img_full = img_full.convert('RGB')
            
            angle = st.session_state[f'rot_{file_id}']
            if angle != 0:
                img_full = img_full.rotate(-angle, expand=True, resample=Image.BICUBIC)
        except Exception as e:
            st.error(f"❌ Error loading image: {e}")
            return
        
        orig_w, orig_h = img_full.size
        
        # Initialize crop dimensions if not set
        if st.session_state[f'crop_width_{file_id}'] is None:
            st.session_state[f'crop_width_{file_id}'] = orig_w
        if st.session_state[f'crop_height_{file_id}'] is None:
            st.session_state[f'crop_height_{file_id}'] = orig_h
        
        st.caption(get_file_info_str(fpath, img_full))
        
        # Layout
        col_canvas, col_controls = st.columns([2.5, 1], gap="medium")
        
        # === CONTROLS ===
        with col_controls:
            st.markdown("### 🔄 Rotate")
            c1, c2, c3 = st.columns(3)
            
            with c1:
                if st.button("↺", use_container_width=True, help="Rotate -90°"):
                    st.session_state[f'rot_{file_id}'] -= 90
                    st.rerun()
            with c2:
                if st.button("↻", use_container_width=True, help="Rotate +90°"):
                    st.session_state[f'rot_{file_id}'] += 90
                    st.rerun()
            with c3:
                if st.button("⟲", use_container_width=True, help="Reset"):
                    st.session_state[f'rot_{file_id}'] = 0
                    st.rerun()
            
            st.divider()
            st.markdown("### ✂️ Crop")
            
            # Aspect ratio
            aspect_choice = st.selectbox(
                "Aspect Ratio",
                list(config.ASPECT_RATIOS.keys()),
                key=f"aspect_{file_id}"
            )
            aspect_val = config.ASPECT_RATIOS[aspect_choice]
            
            # MAX button
            if st.button("⛶ MAX", use_container_width=True):
                if aspect_val is None:
                    max_w, max_h = orig_w, orig_h
                else:
                    ratio = aspect_val[0] / aspect_val[1]
                    max_w = orig_w
                    max_h = int(max_w / ratio)
                    if max_h > orig_h:
                        max_h = orig_h
                        max_w = int(max_h * ratio)
                
                st.session_state[f'crop_width_{file_id}'] = max_w
                st.session_state[f'crop_height_{file_id}'] = max_h
                st.session_state[f'crop_left_{file_id}'] = (orig_w - max_w) // 2
                st.session_state[f'crop_top_{file_id}'] = (orig_h - max_h) // 2
                st.rerun()
            
            st.divider()
            st.markdown("### 📐 Crop Area")
            
            # Position
            col_x, col_y = st.columns(2)
            with col_x:
                crop_left = st.number_input(
                    "Left (px)",
                    0, orig_w - 10,
                    st.session_state[f'crop_left_{file_id}'],
                    10,
                    key=f"left_{file_id}"
                )
            with col_y:
                crop_top = st.number_input(
                    "Top (px)",
                    0, orig_h - 10,
                    st.session_state[f'crop_top_{file_id}'],
                    10,
                    key=f"top_{file_id}"
                )
            
            # Size
            col_w, col_h = st.columns(2)
            with col_w:
                crop_width = st.number_input(
                    "Width (px)",
                    10, orig_w,
                    st.session_state[f'crop_width_{file_id}'],
                    10,
                    key=f"width_{file_id}"
                )
            with col_h:
                crop_height = st.number_input(
                    "Height (px)",
                    10, orig_h,
                    st.session_state[f'crop_height_{file_id}'],
                    10,
                    key=f"height_{file_id}"
                )
            
            # Update state
            st.session_state[f'crop_left_{file_id}'] = crop_left
            st.session_state[f'crop_top_{file_id}'] = crop_top
            st.session_state[f'crop_width_{file_id}'] = crop_width
            st.session_state[f'crop_height_{file_id}'] = crop_height
            
            # Validate and clamp
            if crop_left + crop_width > orig_w:
                crop_width = orig_w - crop_left
            if crop_top + crop_height > orig_h:
                crop_height = orig_h - crop_top
            
            st.info(f"📏 **{crop_width} × {crop_height}** px")
            
            # Center button
            if st.button("⊙ Center", use_container_width=True):
                st.session_state[f'crop_left_{file_id}'] = (orig_w - crop_width) // 2
                st.session_state[f'crop_top_{file_id}'] = (orig_h - crop_height) // 2
                st.rerun()
            
            st.divider()
            
            # Save button
            if st.button("💾 Save Changes", type="primary", use_container_width=True):
                try:
                    crop_box = (crop_left, crop_top, crop_left + crop_width, crop_top + crop_height)
                    final_image = img_full.crop(crop_box)
                    final_image.save(fpath, quality=95, subsampling=0, optimize=True)
                    
                    # Remove thumbnail
                    thumb_path = f"{fpath}.thumb.jpg"
                    if os.path.exists(thumb_path):
                        try:
                            os.remove(thumb_path)
                        except:
                            pass
                    
                    # Clean state
                    for k in list(st.session_state.keys()):
                        if file_id in k:
                            del st.session_state[k]
                    
                    st.session_state['close_editor'] = True
                    st.toast("✅ Changes saved!")
                    logger.info(f"Image saved: {crop_width}×{crop_height} to {fpath}")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Save failed: {e}")
                    logger.error(f"Save failed: {e}", exc_info=True)
        
        # === CANVAS ===
        with col_canvas:
            st.markdown("### 👁️ Preview")
            preview = create_preview_with_box(img_full, crop_left, crop_top, crop_width, crop_height)
            st.image(preview, use_container_width=True)
    
    except Exception as e:
        st.error(f"❌ Editor error: {e}")
        logger.error(f"Editor failed: {e}", exc_info=True)

def get_file_info_str(fpath: str, img: Image.Image) -> str:
    """Generate file info string"""
    try:
        size_bytes = os.path.getsize(fpath)
        size_mb = size_bytes / (1024 * 1024)
        size_str = f"{size_mb:.2f} MB" if size_mb >= 1 else f"{size_bytes/1024:.1f} KB"
        filename = os.path.basename(fpath)
        return f"📄 **{filename}** • 📏 **{img.width}×{img.height}** • 💾 **{size_str}**"
    except Exception as e:
        logger.error(f"Failed to get file info: {e}")
        return "📄 File info unavailable"

def create_preview_with_box(img: Image.Image, left: int, top: int, width: int, height: int, max_width: int = 700) -> Image.Image:
    """Create preview image with crop box overlay"""
    try:
        # Scale image for preview
        scale = 1.0
        if img.width > max_width:
            scale = max_width / img.width
            new_h = int(img.height * scale)
            preview = img.resize((max_width, new_h), Image.Resampling.LANCZOS)
        else:
            preview = img.copy()
        
        # Draw crop box
        draw = ImageDraw.Draw(preview)
        
        # Scale coordinates
        box_left = int(left * scale)
        box_top = int(top * scale)
        box_right = int((left + width) * scale)
        box_bottom = int((top + height) * scale)
        
        # Draw rectangle
        draw.rectangle([box_left, box_top, box_right, box_bottom], outline='red', width=3)
        
        # Draw corners
        corner_size = 20
        for x, y in [(box_left, box_top), (box_right, box_top), (box_left, box_bottom), (box_right, box_bottom)]:
            draw.line([x-corner_size, y, x+corner_size, y], fill='red', width=3)
            draw.line([x, y-corner_size, x, y+corner_size], fill='red', width=3)
        
        return preview
    except Exception as e:
        logger.error(f"Preview creation failed: {e}")
        return img

@st.dialog("🛠 Editor", width="large")
def open_editor_dialog(fpath: str, T: dict):
    """Simple image editor with rotation and manual crop"""
    try:
        validate_image_file(fpath)
        file_id = os.path.basename(fpath)
        
        # Initialize state
        if f'rot_{file_id}' not in st.session_state:
            st.session_state[f'rot_{file_id}'] = 0
        if f'crop_left_{file_id}' not in st.session_state:
            st.session_state[f'crop_left_{file_id}'] = 0
        if f'crop_top_{file_id}' not in st.session_state:
            st.session_state[f'crop_top_{file_id}'] = 0
        if f'crop_width_{file_id}' not in st.session_state:
            st.session_state[f'crop_width_{file_id}'] = None
        if f'crop_height_{file_id}' not in st.session_state:
            st.session_state[f'crop_height_{file_id}'] = None
        
        # Load image
        try:
            with Image.open(fpath) as img_temp:
                img_full = ImageOps.exif_transpose(img_temp)
                img_full = img_full.convert('RGB')
            
            angle = st.session_state[f'rot_{file_id}']
            if angle != 0:
                img_full = img_full.rotate(-angle, expand=True, resample=Image.BICUBIC)
        except Exception as e:
            st.error(f"❌ Error loading image: {e}")
            return
        
        orig_w, orig_h = img_full.size
        
        # Initialize crop dimensions if not set
        if st.session_state[f'crop_width_{file_id}'] is None:
            st.session_state[f'crop_width_{file_id}'] = orig_w
        if st.session_state[f'crop_height_{file_id}'] is None:
            st.session_state[f'crop_height_{file_id}'] = orig_h
        
        st.caption(get_file_info_str(fpath, img_full))
        
        # Layout
        col_canvas, col_controls = st.columns([2.5, 1], gap="medium")
        
        # === CONTROLS ===
        with col_controls:
            st.markdown("### 🔄 Rotate")
            c1, c2, c3 = st.columns(3)
            
            with c1:
                if st.button("↺", use_container_width=True, help="Rotate -90°"):
                    st.session_state[f'rot_{file_id}'] -= 90
                    st.rerun()
            with c2:
                if st.button("↻", use_container_width=True, help="Rotate +90°"):
                    st.session_state[f'rot_{file_id}'] += 90
                    st.rerun()
            with c3:
                if st.button("⟲", use_container_width=True, help="Reset"):
                    st.session_state[f'rot_{file_id}'] = 0
                    st.rerun()
            
            st.divider()
            st.markdown("### ✂️ Crop")
            
            # Aspect ratio
            aspect_choice = st.selectbox(
                "Aspect Ratio",
                list(config.ASPECT_RATIOS.keys()),
                key=f"aspect_{file_id}"
            )
            aspect_val = config.ASPECT_RATIOS[aspect_choice]
            
            # MAX button
            if st.button("⛶ MAX", use_container_width=True):
                if aspect_val is None:
                    max_w, max_h = orig_w, orig_h
                else:
                    ratio = aspect_val[0] / aspect_val[1]
                    max_w = orig_w
                    max_h = int(max_w / ratio)
                    if max_h > orig_h:
                        max_h = orig_h
                        max_w = int(max_h * ratio)
                
                st.session_state[f'crop_width_{file_id}'] = max_w
                st.session_state[f'crop_height_{file_id}'] = max_h
                st.session_state[f'crop_left_{file_id}'] = (orig_w - max_w) // 2
                st.session_state[f'crop_top_{file_id}'] = (orig_h - max_h) // 2
                st.rerun()
            
            st.divider()
            st.markdown("### 📐 Crop Area")
            
            # Position
            col_x, col_y = st.columns(2)
            with col_x:
                crop_left = st.number_input(
                    "Left (px)",
                    0, orig_w - 10,
                    st.session_state[f'crop_left_{file_id}'],
                    10,
                    key=f"left_{file_id}"
                )
            with col_y:
                crop_top = st.number_input(
                    "Top (px)",
                    0, orig_h - 10,
                    st.session_state[f'crop_top_{file_id}'],
                    10,
                    key=f"top_{file_id}"
                )
            
            # Size
            col_w, col_h = st.columns(2)
            with col_w:
                crop_width = st.number_input(
                    "Width (px)",
                    10, orig_w,
                    st.session_state[f'crop_width_{file_id}'],
                    10,
                    key=f"width_{file_id}"
                )
            with col_h:
                crop_height = st.number_input(
                    "Height (px)",
                    10, orig_h,
                    st.session_state[f'crop_height_{file_id}'],
                    10,
                    key=f"height_{file_id}"
                )
            
            # Update state
            st.session_state[f'crop_left_{file_id}'] = crop_left
            st.session_state[f'crop_top_{file_id}'] = crop_top
            st.session_state[f'crop_width_{file_id}'] = crop_width
            st.session_state[f'crop_height_{file_id}'] = crop_height
            
            # Validate and clamp
            if crop_left + crop_width > orig_w:
                crop_width = orig_w - crop_left
            if crop_top + crop_height > orig_h:
                crop_height = orig_h - crop_top
            
            st.info(f"📏 **{crop_width} × {crop_height}** px")
            
            # Center button
            if st.button("⊙ Center", use_container_width=True):
                st.session_state[f'crop_left_{file_id}'] = (orig_w - crop_width) // 2
                st.session_state[f'crop_top_{file_id}'] = (orig_h - crop_height) // 2
                st.rerun()
            
            st.divider()
            
            # Save button
            if st.button("💾 Save Changes", type="primary", use_container_width=True):
                try:
                    crop_box = (crop_left, crop_top, crop_left + crop_width, crop_top + crop_height)
                    final_image = img_full.crop(crop_box)
                    final_image.save(fpath, quality=95, subsampling=0, optimize=True)
                    
                    # Remove thumbnail
                    thumb_path = f"{fpath}.thumb.jpg"
                    if os.path.exists(thumb_path):
                        try:
                            os.remove(thumb_path)
                        except:
                            pass
                    
                    # Clean state
                    for k in list(st.session_state.keys()):
                        if file_id in k:
                            del st.session_state[k]
                    
                    st.session_state['close_editor'] = True
                    st.toast("✅ Changes saved!")
                    logger.info(f"Image saved: {crop_width}×{crop_height} to {fpath}")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Save failed: {e}")
                    logger.error(f"Save failed: {e}", exc_info=True)
        
        # === CANVAS ===
        with col_canvas:
            st.markdown("### 👁️ Preview")
            preview = create_preview_with_box(img_full, crop_left, crop_top, crop_width, crop_height)
            st.image(preview, use_container_width=True)
    
    except Exception as e:
        st.error(f"❌ Editor error: {e}")
        logger.error(f"Editor failed: {e}", exc_info=True)

def get_file_info_str(fpath: str, img: Image.Image) -> str:
    """Generate file info string for display"""
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
    """Create proxy (downscaled) image for editor performance"""
    if target_width is None:
        target_width = config.PROXY_IMAGE_WIDTH
    
    try:
        w, h = img.size
        
        if w <= target_width:
            return img, 1.0
        
        ratio = target_width / w
        new_h = max(1, int(h * ratio))
        
        validate_dimensions(target_width, new_h)
        
        proxy = img.resize((target_width, new_h), Image.Resampling.LANCZOS)
        
        scale = w / target_width
        logger.debug(f"Proxy created: {w}x{h} → {target_width}x{new_h} (scale: {scale:.2f})")
        
        return proxy, scale
    
    except Exception as e:
        logger.error(f"Proxy creation failed: {e}")
        return img, 1.0

def calculate_max_crop_dimensions(
    img_w: int,
    img_h: int,
    aspect_ratio: Optional[Tuple[int, int]]
) -> Tuple[int, int]:
    """
    Calculate maximum crop dimensions for given aspect ratio
    
    Args:
        img_w: Image width
        img_h: Image height
        aspect_ratio: Aspect ratio tuple (w, h) or None
        
    Returns:
        Tuple of (width, height)
    """
    try:
        if aspect_ratio is None:
            # Free aspect - use almost full image
            return img_w - 10, img_h - 10
        
        ratio_w, ratio_h = aspect_ratio
        if ratio_w == 0 or ratio_h == 0:
            logger.warning(f"Invalid aspect ratio: {aspect_ratio}")
            return img_w, img_h
        
        ratio = ratio_w / ratio_h
        
        # Try to fit by width (use FULL width)
        crop_w = img_w
        crop_h = int(crop_w / ratio)
        
        if crop_h > img_h:
            # Doesn't fit by width, fit by height (use FULL height)
            crop_h = img_h
            crop_w = int(crop_h * ratio)
        
        # Ensure within bounds
        crop_w = max(10, min(crop_w, img_w))
        crop_h = max(10, min(crop_h, img_h))
        
        logger.debug(f"MAX dimensions: {crop_w}x{crop_h} for ratio {ratio_w}:{ratio_h}")
        
        return crop_w, crop_h
    
    except Exception as e:
        logger.error(f"Max dimensions calculation failed: {e}")
        return img_w, img_h

@st.dialog("🛠 Editor", width="large")
def open_editor_dialog(fpath: str, T: dict):
    """
    Open image editor dialog
    
    Args:
        fpath: Path to image file
        T: Translation dictionary
    """
    try:
        validate_image_file(fpath)
        
        file_id = os.path.basename(fpath)
        
        # Initialize state
        if f'rot_{file_id}' not in st.session_state:
            st.session_state[f'rot_{file_id}'] = 0
        
        if f'reset_{file_id}' not in st.session_state:
            st.session_state[f'reset_{file_id}'] = 0
        
        # Load original image
        try:
            with Image.open(fpath) as img_temp:
                img_full = ImageOps.exif_transpose(img_temp)
                img_full = img_full.convert('RGB')
            
            # Apply rotation if needed
            angle = st.session_state[f'rot_{file_id}']
            if angle != 0:
                img_full = img_full.rotate(-angle, expand=True, resample=Image.BICUBIC)
        
        except Exception as e:
            st.error(f"❌ Error loading image: {e}")
            logger.error(f"Image load failed: {e}")
            return
        
        # Create proxy for performance
        img_proxy, scale_factor = create_proxy_image(img_full)
        proxy_w, proxy_h = img_proxy.size
        orig_w, orig_h = img_full.size
        
        # Display file info
        st.caption(get_file_info_str(fpath, img_full))
        
        # Layout
        col_canvas, col_controls = st.columns([3, 1], gap="small")
        
        # === CONTROLS ===
        with col_controls:
            st.markdown("**🔄 Rotate**")
            
            # Rotation buttons
            c1, c2, c3 = st.columns(3)
            
            with c1:
                if st.button("↺ -90°", use_container_width=True, key=f"rot_left_{file_id}"):
                    st.session_state[f'rot_{file_id}'] -= 90
                    st.session_state[f'reset_{file_id}'] += 1
                    st.rerun()
            
            with c2:
                if st.button("↻ +90°", use_container_width=True, key=f"rot_right_{file_id}"):
                    st.session_state[f'rot_{file_id}'] += 90
                    st.session_state[f'reset_{file_id}'] += 1
                    st.rerun()
            
            with c3:
                if st.button("⟲", use_container_width=True, key=f"reset_rot_{file_id}", help="Reset rotation"):
                    st.session_state[f'rot_{file_id}'] = 0
                    st.session_state[f'reset_{file_id}'] += 1
                    st.rerun()
            
            st.divider()
            st.markdown("**✂️ Crop**")
            
            # Aspect ratio selection
            aspect_choice = st.selectbox(
                T.get('lbl_aspect', 'Aspect Ratio'),
                list(config.ASPECT_RATIOS.keys()),
                key=f"asp_{file_id}"
            )
            aspect_val = config.ASPECT_RATIOS[aspect_choice]
            
            # MAX button - calculate maximum crop area
            if st.button("⛶ MAX", use_container_width=True, key=f"max_{file_id}"):
                try:
                    max_w, max_h = calculate_max_crop_dimensions(orig_w, orig_h, aspect_val)
                    
                    # Store for manual input
                    st.session_state[f'manual_w_{file_id}'] = max_w
                    st.session_state[f'manual_h_{file_id}'] = max_h
                    
                    ratio_str = f"{aspect_val[0]}:{aspect_val[1]}" if aspect_val else "free"
                    st.toast(f"MAX: {max_w}×{max_h}px ({ratio_str})")
                    st.rerun()
                    
                except Exception as e:
                    st.error(f"MAX error: {e}")
                    logger.error(f"MAX failed: {e}", exc_info=True)
            
            st.divider()
            st.markdown("**📐 Manual Size**")
            
            # Manual dimensions input
            col_w, col_h = st.columns(2)
            
            with col_w:
                manual_w = st.number_input(
                    "Width (px)",
                    min_value=10,
                    max_value=orig_w,
                    value=st.session_state.get(f'manual_w_{file_id}', orig_w // 2),
                    step=10,
                    key=f"input_w_{file_id}"
                )
            
            with col_h:
                manual_h = st.number_input(
                    "Height (px)",
                    min_value=10,
                    max_value=orig_h,
                    value=st.session_state.get(f'manual_h_{file_id}', orig_h // 2),
                    step=10,
                    key=f"input_h_{file_id}"
                )
            
            # Update session state
            st.session_state[f'manual_w_{file_id}'] = manual_w
            st.session_state[f'manual_h_{file_id}'] = manual_h
        
        # === CANVAS ===
        with col_canvas:
            if st_cropper is None:
                st.error("❌ Cropper library not installed. Please install: pip install streamlit-cropper-fix")
                rect = None
            else:
                try:
                    # Create unique key for cropper
                    cropper_key = f"crop_{file_id}_{st.session_state[f'reset_{file_id}']}"
                    
                    # Use streamlit-cropper (fix or original)
                    rect = st_cropper(
                        img_proxy,
                        realtime_update=True,
                        box_color='#FF0000',
                        aspect_ratio=aspect_val,
                        return_type='box',
                        key=cropper_key
                    )
                    
                except Exception as e:
                    st.error(f"Cropper error: {e}")
                    logger.error(f"Cropper failed: {e}", exc_info=True)
                    rect = None
        
        # === SAVE SECTION ===
        with col_controls:
            st.divider()
            
            # Calculate crop dimensions from rect or manual input
            if rect and 'width' in rect and 'height' in rect:
                # Use cropper rect
                crop_w = int(rect['width'] * scale_factor)
                crop_h = int(rect['height'] * scale_factor)
                crop_left = int(rect['left'] * scale_factor)
                crop_top = int(rect['top'] * scale_factor)
                
                st.info(f"📏 **{crop_w} × {crop_h}** px")
            else:
                # Use manual input
                crop_w = manual_w
                crop_h = manual_h
                crop_left = (orig_w - crop_w) // 2
                crop_top = (orig_h - crop_h) // 2
                
                st.info(f"📏 **{crop_w} × {crop_h}** px (manual)")
            
            # Clamp to image bounds
            crop_left = max(0, min(crop_left, orig_w - crop_w))
            crop_top = max(0, min(crop_top, orig_h - crop_h))
            crop_w = min(crop_w, orig_w - crop_left)
            crop_h = min(crop_h, orig_h - crop_top)
            
            crop_box = (crop_left, crop_top, crop_left + crop_w, crop_top + crop_h)
            
            # Save button
            if st.button(
                T.get('btn_save_edit', '💾 Save Changes'),
                type="primary",
                use_container_width=True,
                key=f"save_{file_id}"
            ):
                try:
                    # Crop image
                    final_image = img_full.crop(crop_box)
                    
                    # Save with high quality
                    final_image.save(fpath, quality=95, subsampling=0, optimize=True)
                    
                    # Remove thumbnail cache
                    thumb_path = f"{fpath}.thumb.jpg"
                    if os.path.exists(thumb_path):
                        try:
                            os.remove(thumb_path)
                        except:
                            pass
                    
                    # Clean state
                    keys_to_clean = [
                        f'rot_{file_id}',
                        f'reset_{file_id}',
                        f'manual_w_{file_id}',
                        f'manual_h_{file_id}'
                    ]
                    for k in keys_to_clean:
                        if k in st.session_state:
                            del st.session_state[k]
                    
                    st.session_state['close_editor'] = True
                    st.toast(T.get('msg_edit_saved', '✅ Changes saved!'))
                    logger.info(f"Image edited: {crop_w}×{crop_h} saved to {fpath}")
                    st.rerun()
                
                except Exception as e:
                    st.error(f"❌ Save failed: {e}")
                    logger.error(f"Save failed: {e}", exc_info=True)
    
    except Exception as e:
        st.error(f"❌ Editor error: {e}")
        logger.error(f"Editor failed: {e}", exc_info=True)

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
        
        # === CANVAS (FIRST - to get rect) ===
        with col_canvas:
            cropper_id = f"crp_{file_id}_{st.session_state[f'reset_{file_id}']}"
            default_box = st.session_state.get(f'crop_box_{file_id}', None)
            
            # Get aspect ratio first
            aspect_choice_state = st.session_state.get(f"asp_{file_id}", "Free / Вільний")
            aspect_val = config.ASPECT_RATIOS.get(aspect_choice_state)
            
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
        
        # Calculate current dimensions from rect
        real_w, real_h = 0, 0
        if rect:
            try:
                real_w = int(rect['width'] * scale_factor)
                real_h = int(rect['height'] * scale_factor)
            except:
                pass
        
        # Default values for manual input
        if real_w > 0 and real_h > 0:
            default_w = real_w
            default_h = real_h
        else:
            default_w = min(1000, img_full.width)
            default_h = min(750, img_full.height)
        
        # === CONTROLS ===
        with col_controls:
            st.markdown("**🔄 Rotate**")
            
            # Rotation buttons
            c1, c2, c3 = st.columns(3)
            
            with c1:
                if st.button(
                    "↺ -90°",
                    use_container_width=True,
                    key=f"rot_left_{file_id}",
                    help="Rotate left"
                ):
                    st.session_state[f'rot_{file_id}'] -= 90
                    st.session_state[f'reset_{file_id}'] += 1
                    st.session_state[f'crop_box_{file_id}'] = None
                    st.rerun()
            
            with c2:
                if st.button(
                    "↻ +90°",
                    use_container_width=True,
                    key=f"rot_right_{file_id}",
                    help="Rotate right"
                ):
                    st.session_state[f'rot_{file_id}'] += 90
                    st.session_state[f'reset_{file_id}'] += 1
                    st.session_state[f'crop_box_{file_id}'] = None
                    st.rerun()
            
            with c3:
                # Reset button
                if st.button(
                    "⟲ Reset",
                    use_container_width=True,
                    key=f"reset_all_{file_id}",
                    help="Reset rotation"
                ):
                    st.session_state[f'rot_{file_id}'] = 0
                    st.session_state[f'crop_box_{file_id}'] = None
                    st.session_state[f'reset_{file_id}'] += 1
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
            
            # MAX button
            col_max, col_reset = st.columns(2)
            with col_max:
                if st.button(
                    "⛶ MAX",
                    use_container_width=True,
                    key=f"max_{file_id}",
                    help="Maximum crop area"
                ):
                    try:
                        aspect_val_max = config.ASPECT_RATIOS[aspect_choice]
                        max_box = calculate_max_crop_box(proxy_w, proxy_h, aspect_val_max)
                        
                        if max_box:
                            st.session_state[f'crop_box_{file_id}'] = max_box
                            st.session_state[f'reset_{file_id}'] += 1
                            
                            real_w_max = int(max_box['width'] * scale_factor)
                            real_h_max = int(max_box['height'] * scale_factor)
                            
                            st.toast(f"MAX: {real_w_max}×{real_h_max}px")
                            logger.info(f"MAX: {real_w_max}x{real_h_max}")
                            st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")
                        logger.error(f"MAX failed: {e}", exc_info=True)
            
            with col_reset:
                if st.button(
                    "↺ Reset",
                    use_container_width=True,
                    key=f"reset_crop_{file_id}",
                    help="Reset crop"
                ):
                    st.session_state[f'crop_box_{file_id}'] = None
                    st.session_state[f'reset_{file_id}'] += 1
                    st.rerun()
            
            st.divider()
            
            # Manual size input
            st.markdown("**📐 Manual Size (px)**")
            
            col_w, col_h = st.columns(2)
            
            with col_w:
                manual_width = st.number_input(
                    "Width",
                    min_value=10,
                    max_value=img_full.width,
                    value=default_w,
                    step=10,
                    key=f"manual_w_{cropper_id}",
                    label_visibility="collapsed"
                )
            
            with col_h:
                manual_height = st.number_input(
                    "Height",
                    min_value=10,
                    max_value=img_full.height,
                    value=default_h,
                    step=10,
                    key=f"manual_h_{cropper_id}",
                    label_visibility="collapsed"
                )
            
            # Apply manual size button
            if st.button(
                "✓ Apply Size",
                use_container_width=True,
                key=f"apply_manual_{file_id}",
                help="Apply manual dimensions"
            ):
                try:
                    # Validate
                    if manual_width > img_full.width or manual_height > img_full.height:
                        st.error(f"Too large! Max: {img_full.width}×{img_full.height}")
                    else:
                        # Scale to proxy
                        proxy_width = int(manual_width / scale_factor)
                        proxy_height = int(manual_height / scale_factor)
                        
                        # Center
                        left = max(0, (proxy_w - proxy_width) // 2)
                        top = max(0, (proxy_h - proxy_height) // 2)
                        
                        st.session_state[f'crop_box_{file_id}'] = {
                            'left': left,
                            'top': top,
                            'width': proxy_width,
                            'height': proxy_height
                        }
                        st.session_state[f'reset_{file_id}'] += 1
                        st.toast(f"Applied: {manual_width}×{manual_height}px")
                        st.rerun()
                        
                except Exception as e:
                    st.error(f"Error: {e}")
                    logger.error(f"Apply size failed: {e}", exc_info=True)
            
            st.divider()
            
            # Display current dimensions
            if real_w > 0 and real_h > 0:
                st.info(f"📏 **{real_w} × {real_h}** px")
            else:
                st.info("📏 **Select crop area**")
            
            # Save button
            crop_box = None
            if rect:
                try:
                    left = int(rect['left'] * scale_factor)
                    top = int(rect['top'] * scale_factor)
                    width = int(rect['width'] * scale_factor)
                    height = int(rect['height'] * scale_factor)
                    
                    orig_w, orig_h = img_full.size
                    
                    left = max(0, min(left, orig_w))
                    top = max(0, min(top, orig_h))
                    
                    if left + width > orig_w:
                        width = orig_w - left
                    if top + height > orig_h:
                        height = orig_h - top
                    
                    width = max(1, width)
                    height = max(1, height)
                    
                    crop_box = (left, top, left + width, top + height)
                except Exception as e:
                    logger.error(f"Crop box calc failed: {e}")
            
            if st.button(
                T.get('btn_save_edit', '💾 Save'),
                type="primary",
                use_container_width=True,
                key=f"save_{file_id}"
            ):
                try:
                    if crop_box:
                        final_image = img_full.crop(crop_box)
                        final_image.save(fpath, quality=95, subsampling=0, optimize=True)
                        
                        # Remove thumbnail
                        thumb_path = f"{fpath}.thumb.jpg"
                        if os.path.exists(thumb_path):
                            try:
                                os.remove(thumb_path)
                            except:
                                pass
                        
                        # Clean state
                        for k in [f'rot_{file_id}', f'reset_{file_id}', f'crop_box_{file_id}']:
                            if k in st.session_state:
                                del st.session_state[k]
                        
                        st.session_state['close_editor'] = True
                        st.toast(T.get('msg_edit_saved', '✅ Saved!'))
                        logger.info(f"Image saved: {fpath}")
                        st.rerun()
                    else:
                        st.warning("No crop area selected")
                
                except Exception as e:
                    st.error(f"❌ Save failed: {e}")
                    logger.error(f"Save failed: {e}", exc_info=True)
    
    except Exception as e:
        st.error(f"❌ Editor error: {e}")
        logger.error(f"Editor failed: {e}", exc_info=True)
        
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
