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
    try:
        size_bytes = os.path.getsize(fpath)
        size_mb = size_bytes / (1024 * 1024)

        if size_mb >= 1:
            size_str = f"{size_mb:.2f} MB"
        else:
            size_str = f"{size_bytes/1024:.1f} KB"

        filename = os.path.basename(fpath)
        return f"📄 **{filename}** • 📏 **{img.width}x{img.height}** • 💾 **{size_str}**"
    except Exception as e:
        logger.error(f"Failed to generate file info: {e}")
        return "📄 File info unavailable"


def create_proxy_image(img: Image.Image, target_width: int = None) -> Tuple[Image.Image, float]:
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
        return proxy, scale
    except Exception as e:
        logger.error(f"Proxy creation failed: {e}")
        return img, 1.0


def calculate_max_crop_box(
    img_w: int,
    img_h: int,
    aspect_ratio: Optional[Tuple[int, int]]
) -> Dict[str, int]:
    try:
        if aspect_ratio is None:
            return {'left': 0, 'top': 0, 'width': img_w, 'height': img_h}

        rw, rh = aspect_ratio
        if rw == 0 or rh == 0:
            return {'left': 0, 'top': 0, 'width': img_w, 'height': img_h}

        ratio = rw / rh
        crop_w = img_w
        crop_h = int(crop_w / ratio)

        if crop_h > img_h:
            crop_h = img_h
            crop_w = int(crop_h * ratio)

        crop_w = max(10, min(crop_w, img_w))
        crop_h = max(10, min(crop_h, img_h))

        left = (img_w - crop_w) // 2
        top = (img_h - crop_h) // 2

        left = max(0, min(left, img_w - crop_w))
        top = max(0, min(top, img_h - crop_h))

        return {'left': left, 'top': top, 'width': crop_w, 'height': crop_h}
    except Exception as e:
        logger.error(f"Max box calculation failed: {e}")
        return {'left': 0, 'top': 0, 'width': img_w, 'height': img_h}


@st.dialog("Editor", width="large")
def open_editor_dialog(fpath: str, T: dict):
    try:
        validate_image_file(fpath)
        file_id = os.path.basename(fpath)

        st.session_state.setdefault(f'rot_{file_id}', 0)
        st.session_state.setdefault(f'reset_{file_id}', 0)
        st.session_state.setdefault(f'crop_box_{file_id}', None)
        st.session_state.setdefault(f'manual_w_{file_id}', None)
        st.session_state.setdefault(f'manual_h_{file_id}', None)

        with Image.open(fpath) as img_temp:
            img_full = ImageOps.exif_transpose(img_temp).convert("RGB")

        angle = st.session_state[f'rot_{file_id}']
        if angle:
            img_full = img_full.rotate(-angle, expand=True, resample=Image.BICUBIC)

        img_proxy, scale_factor = create_proxy_image(img_full)
        proxy_w, proxy_h = img_proxy.size

        if st.session_state[f'manual_w_{file_id}'] is None:
            st.session_state[f'manual_w_{file_id}'] = img_full.width
            st.session_state[f'manual_h_{file_id}'] = img_full.height

        st.caption(get_file_info_str(fpath, img_full))

        col_canvas, col_controls = st.columns([3, 1], gap="small")

        with col_controls:
            if st.button("↺ -90°", use_container_width=True):
                st.session_state[f'rot_{file_id}'] -= 90
                st.session_state[f'reset_{file_id}'] += 1
                st.session_state[f'crop_box_{file_id}'] = None
                st.rerun()

            if st.button("↻ +90°", use_container_width=True):
                st.session_state[f'rot_{file_id}'] += 90
                st.session_state[f'reset_{file_id}'] += 1
                st.session_state[f'crop_box_{file_id}'] = None
                st.rerun()

            aspect_choice = st.selectbox(
                T.get('lbl_aspect', 'Aspect Ratio'),
                list(config.ASPECT_RATIOS.keys()),
                key=f"asp_{file_id}"
            )
            aspect_val = config.ASPECT_RATIOS[aspect_choice]

            manual_width = st.number_input(
                "Width",
                min_value=10,
                max_value=img_full.width,
                step=10,
                key=f"manual_w_{file_id}"
            )

            manual_height = st.number_input(
                "Height",
                min_value=10,
                max_value=img_full.height,
                step=10,
                key=f"manual_h_{file_id}"
            )

            if st.button("Apply Size", use_container_width=True):
                pw = int(manual_width / scale_factor)
                ph = int(manual_height / scale_factor)

                pw = max(10, min(pw, proxy_w))
                ph = max(10, min(ph, proxy_h))

                left = (proxy_w - pw) // 2
                top = (proxy_h - ph) // 2

                left = max(0, min(left, proxy_w - pw))
                top = max(0, min(top, proxy_h - ph))

                st.session_state[f'crop_box_{file_id}'] = {
                    'left': left,
                    'top': top,
                    'width': pw,
                    'height': ph
                }
                st.session_state[f'reset_{file_id}'] += 1
                st.rerun()

            if st.button("MAX", use_container_width=True):
                max_box = calculate_max_crop_box(proxy_w, proxy_h, aspect_val)

                max_box['width'] = min(max_box['width'], proxy_w)
                max_box['height'] = min(max_box['height'], proxy_h)
                max_box['left'] = max(0, min(max_box['left'], proxy_w - max_box['width']))
                max_box['top'] = max(0, min(max_box['top'], proxy_h - max_box['height']))

                st.session_state[f'crop_box_{file_id}'] = max_box
                st.session_state[f'reset_{file_id}'] += 1
                st.rerun()

        with col_canvas:
            cropper_id = f"crp_{file_id}_{st.session_state[f'reset_{file_id}']}_{aspect_choice}"
            rect = st_cropper(
                img_proxy,
                realtime_update=True,
                aspect_ratio=aspect_val,
                should_resize_image=False,
                default_coords=st.session_state[f'crop_box_{file_id}'],
                return_type="box",
                key=cropper_id
            )

            if rect:
                st.session_state[f"manual_w_{file_id}"] = int(rect['width'] * scale_factor)
                st.session_state[f"manual_h_{file_id}"] = int(rect['height'] * scale_factor)

        if rect and st.button(T.get('btn_save_edit', 'Save'), type="primary", use_container_width=True):
            left = int(rect['left'] * scale_factor)
            top = int(rect['top'] * scale_factor)
            width = int(rect['width'] * scale_factor)
            height = int(rect['height'] * scale_factor)

            orig_w, orig_h = img_full.size
            left = max(0, min(left, orig_w - 1))
            top = max(0, min(top, orig_h - 1))
            width = max(1, min(width, orig_w - left))
            height = max(1, min(height, orig_h - top))

            crop_box = (left, top, left + width, top + height)
            img_full.crop(crop_box).save(fpath, quality=95, subsampling=0, optimize=True)

            for k in list(st.session_state.keys()):
                if k.endswith(file_id):
                    del st.session_state[k]

            st.toast(T.get('msg_edit_saved', 'Saved'))
            st.rerun()

    except Exception as e:
        st.error(f"Editor error: {e}")
        logger.error(e, exc_info=True)
