"""
Watermarker Pro v7.0 - Editor Module
=====================================
Image editing dialog with crop and rotate (fixed)
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

# -------------------------
# Utilities
# -------------------------

def clamp_int(v: int, lo: int, hi: int) -> int:
    return max(lo, min(v, hi))

def clamp_box_to_canvas(box: Dict[str, int], canvas_w: int, canvas_h: int) -> Dict[str, int]:
    """
    Clamp box (left, top, width, height) to canvas bounds.
    Ensures width/height >= 10 and box within [0..canvas].
    """
    left = clamp_int(box.get('left', 0), 0, max(0, canvas_w - 10))
    top = clamp_int(box.get('top', 0), 0, max(0, canvas_h - 10))
    width = clamp_int(box.get('width', 10), 10, canvas_w)
    height = clamp_int(box.get('height', 10), 10, canvas_h)

    # Prevent overflow beyond canvas
    if left + width > canvas_w:
        width = max(10, canvas_w - left)
    if top + height > canvas_h:
        height = max(10, canvas_h - top)

    return {'left': left, 'top': top, 'width': width, 'height': height}

def sync_manual_size_from_rect(rect: Optional[Dict[str, int]], scale_factor: float, img_full_w: int, img_full_h: int, file_id: str):
    """
    Update manual width/height inputs to match current rect (original pixels).
    """
    if not rect:
        return
    w = clamp_int(int(rect['width'] * scale_factor), 10, img_full_w)
    h = clamp_int(int(rect['height'] * scale_factor), 10, img_full_h)
    st.session_state[f"manual_w_{file_id}"] = w
    st.session_state[f"manual_h_{file_id}"] = h

def get_file_info_str(fpath: str, img: Image.Image) -> str:
    """
    Generate file info string for display
    """
    try:
        size_bytes = os.path.getsize(fpath)
        size_mb = size_bytes / (1024 * 1024)
        size_str = f"{size_mb:.2f} MB" if size_mb >= 1 else f"{size_bytes/1024:.1f} KB"
        filename = os.path.basename(fpath)
        return f"📄 **{filename}** &nbsp;•&nbsp; 📏 **{img.width}x{img.height}** &nbsp;•&nbsp; 💾 **{size_str}**"
    except Exception as e:
        logger.error(f"Failed to generate file info: {e}")
        return "📄 File info unavailable"

def create_proxy_image(img: Image.Image, target_width: int = None) -> Tuple[Image.Image, float]:
    """
    Create proxy (downscaled) image for editor performance
    Returns (proxy_image, scale_factor) where scale_factor = original_w / proxy_w
    """
    if target_width is None:
        target_width = config.PROXY_IMAGE_WIDTH

    try:
        w, h = img.size
        if w <= target_width:
            return img, 1.0

        ratio = target_width / w
        new_h = max(1, int(round(h * ratio)))

        validate_dimensions(target_width, new_h)

        proxy = img.resize((target_width, new_h), Image.Resampling.LANCZOS)
        scale = w / target_width
        logger.debug(f"Proxy created: {w}x{h} → {target_width}x{new_h} (scale: {scale:.4f})")
        return proxy, scale

    except Exception as e:
        logger.error(f"Proxy creation failed: {e}")
        # Fall back to original (may be slower) but keep UX informative
        st.warning("⚠️ Proxy image could not be created. Editing large image directly may be slower.")
        return img, 1.0

def calculate_max_crop_box(img_w: int, img_h: int, aspect_ratio: Optional[Tuple[int, int]]) -> Dict[str, int]:
    """
    Calculate maximum crop box for given aspect ratio on the given canvas (proxy).
    Returns dict: left, top, width, height
    """
    try:
        if aspect_ratio is None:
            pad = 5
            return {
                'left': pad,
                'top': pad,
                'width': max(10, img_w - 2 * pad),
                'height': max(10, img_h - 2 * pad)
            }

        ratio_w, ratio_h = aspect_ratio
        if ratio_w <= 0 or ratio_h <= 0:
            logger.warning(f"Invalid aspect ratio: {aspect_ratio}")
            return {'left': 0, 'top': 0, 'width': img_w, 'height': img_h}

        ratio_val = ratio_w / ratio_h

        # Try full width first
        crop_w = img_w
        crop_h = int(round(crop_w / ratio_val))

        if crop_h > img_h:
            # Fit full height if full width exceeds height
            crop_h = img_h
            crop_w = int(round(crop_h * ratio_val))

        crop_w = clamp_int(crop_w, 10, img_w)
        crop_h = clamp_int(crop_h, 10, img_h)

        left = (img_w - crop_w) // 2
        top = (img_h - crop_h) // 2

        result = clamp_box_to_canvas(
            {'left': left, 'top': top, 'width': crop_w, 'height': crop_h},
            img_w, img_h
        )

        logger.debug(
            f"MAX box calculated: {result['width']}x{result['height']} at ({result['left']}, {result['top']}) "
            f"for image {img_w}x{img_h}, ratio {ratio_w}:{ratio_h}"
        )
        return result

    except Exception as e:
        logger.error(f"Max box calculation failed: {e}")
        return {'left': 0, 'top': 0, 'width': img_w, 'height': img_h}

def cleanup_editor_state(file_id: str):
    """
    Clear editor-related session state keys for a given file_id
    """
    for k in [f'rot_{file_id}', f'reset_{file_id}', f'crop_box_{file_id}']:
        if k in st.session_state:
            del st.session_state[k]

# -------------------------
# Dialog
# -------------------------

@st.dialog("🛠 Editor", width="large")
def open_editor_dialog(fpath: str, T: dict):
    """
    Open image editor dialog
    """
    try:
        # Validate file
        validate_image_file(fpath)

        file_id = os.path.basename(fpath)

        # Initialize state
        st.session_state.setdefault(f'rot_{file_id}', 0)
        st.session_state.setdefault(f'reset_{file_id}', 0)
        st.session_state.setdefault(f'crop_box_{file_id}', None)

        # Load original image
        try:
            with Image.open(fpath) as img_temp:
                img_full = ImageOps.exif_transpose(img_temp)
                img_full = img_full.convert('RGB')

            # Apply rotation if needed
            angle = st.session_state[f'rot_{file_id}']
            if angle % 360 != 0:
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
                    st.session_state[f'crop_box_{file_id}'] = None
                    st.rerun()

            with c2:
                if st.button("↻ +90°", use_container_width=True, key=f"rot_right_{file_id}"):
                    st.session_state[f'rot_{file_id}'] += 90
                    st.session_state[f'reset_{file_id}'] += 1
                    st.session_state[f'crop_box_{file_id}'] = None
                    st.rerun()

            # Reset button
            if st.button("Reset", use_container_width=True, key=f"reset_{file_id}"):
                st.session_state[f'rot_{file_id}'] = 0
                st.session_state[f'crop_box_{file_id}'] = None
                st.session_state[f'reset_{file_id}'] += 1
                st.toast("✅ Reset done", icon="♻️")
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

            # Manual size input (original pixels)
            st.markdown("**📐 Manual Size (px)**")
            col_w, col_h = st.columns(2)

            # Initialize manual fields if absent
            st.session_state.setdefault(f"manual_w_{file_id}", img_full.width // 2)
            st.session_state.setdefault(f"manual_h_{file_id}", img_full.height // 2)

            with col_w:
                manual_width = st.number_input(
                    "Width",
                    min_value=10,
                    max_value=img_full.width,
                    value=st.session_state[f"manual_w_{file_id}"],
                    step=10,
                    key=f"manual_w_{file_id}",
                    label_visibility="collapsed"
                )

            with col_h:
                manual_height = st.number_input(
                    "Height",
                    min_value=10,
                    max_value=img_full.height,
                    value=st.session_state[f"manual_h_{file_id}"],
                    step=10,
                    key=f"manual_h_{file_id}",
                    label_visibility="collapsed"
                )

            # Apply manual size button
            if st.button(
                "✓ Apply Size",
                use_container_width=True,
                key=f"apply_manual_{file_id}",
                help="Set crop box to specified dimensions"
            ):
                # Convert original size to proxy size
                proxy_width = max(10, int(round(manual_width / scale_factor)))
                proxy_height = max(10, int(round(manual_height / scale_factor)))

                # Center the box in proxy
                left = (proxy_w - proxy_width) // 2
                top = (proxy_h - proxy_height) // 2

                # Clamp to proxy bounds
                new_box = clamp_box_to_canvas(
                    {'left': left, 'top': top, 'width': proxy_width, 'height': proxy_height},
                    proxy_w, proxy_h
                )
                st.session_state[f'crop_box_{file_id}'] = new_box
                st.session_state[f'reset_{file_id}'] += 1

                # Use valid emoji (no shortcodes)
                st.toast(f"✅ Set: {manual_width}×{manual_height}px", icon="📐")
                logger.debug(f"Apply manual size → proxy box {new_box} (scale {scale_factor:.4f})")

                st.rerun()

            st.divider()

            # MAX button
            if st.button(
                "MAX",
                use_container_width=True,
                key=f"max_{file_id}",
                help="Максимальна область у вибраному співвідношенні"
            ):
                # Calculate MAX box for PROXY image
                max_box = calculate_max_crop_box(proxy_w, proxy_h, aspect_val)
                st.session_state[f'crop_box_{file_id}'] = max_box
                st.session_state[f'reset_{file_id}'] += 1

                # Calculate real (original) dimensions for display
                real_w = int(round(max_box['width'] * scale_factor))
                real_h = int(round(max_box['height'] * scale_factor))

                ratio_str = f"{aspect_val[0]}:{aspect_val[1]}" if aspect_val else "free"

                # Valid emoji (single Unicode char)
                st.toast(f"✅ MAX: {real_w}×{real_h}px ({ratio_str})", icon="📐")
                logger.info(
                    f"MAX activated: {real_w}x{real_h} ({ratio_str}) "
                    f"for proxy {proxy_w}x{proxy_h} (scale {scale_factor:.4f})"
                )
                # Sync manual inputs with MAX selection
                st.session_state[f"manual_w_{file_id}"] = real_w
                st.session_state[f"manual_h_{file_id}"] = real_h

                st.rerun()

        # === CANVAS ===
        with col_canvas:
            cropper_id = f"crp_{file_id}_{st.session_state[f'reset_{file_id}']}_{aspect_choice}"
            default_box = st.session_state.get(f'crop_box_{file_id}', None)

            # Ensure default_box is valid for st_cropper
            if default_box:
                default_box = clamp_box_to_canvas(default_box, proxy_w, proxy_h)

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
                    # Convert proxy rect to original coordinates
                    left = int(round(rect['left'] * scale_factor))
                    top = int(round(rect['top'] * scale_factor))
                    width = int(round(rect['width'] * scale_factor))
                    height = int(round(rect['height'] * scale_factor))

                    orig_w, orig_h = img_full.size

                    # Clamp within original
                    left = clamp_int(left, 0, orig_w - 1)
                    top = clamp_int(top, 0, orig_h - 1)

                    if left + width > orig_w:
                        width = orig_w - left
                    if top + height > orig_h:
                        height = orig_h - top

                    width = max(1, width)
                    height = max(1, height)

                    crop_box = (left, top, left + width, top + height)
                    real_w, real_h = width, height

                    logger.debug(
                        f"Crop calculated: proxy ({rect['left']:.0f}, {rect['top']:.0f}, "
                        f"{rect['width']:.0f}x{rect['height']:.0f}) → "
                        f"original ({left}, {top}, {width}x{height})"
                    )

                    # Sync manual size fields to current rect
                    sync_manual_size_from_rect(rect, scale_factor, orig_w, orig_h, file_id)

                except Exception as e:
                    logger.error(f"Crop calculation failed: {e}", exc_info=True)
                    st.warning(f"⚠️ Помилка розрахунку: {e}")

            # Display dimensions (оригінальні розміри)
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
                        cleanup_editor_state(file_id)

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
