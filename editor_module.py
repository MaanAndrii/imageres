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


def create_proxy_image(img: Image.Image, target_width: int = None):
    if target_width is None:
        target_width = config.PROXY_IMAGE_WIDTH

    w, h = img.size
    if w <= target_width:
        return img, 1.0

    ratio = target_width / w
    new_h = int(h * ratio)
    validate_dimensions(target_width, new_h)

    proxy = img.resize((target_width, new_h), Image.Resampling.LANCZOS)
    return proxy, w / target_width


def calculate_max_crop(img_w, img_h, aspect):
    if aspect is None:
        return 0, 0, img_w, img_h

    rw, rh = aspect
    ratio = rw / rh

    w = img_w
    h = int(w / ratio)
    if h > img_h:
        h = img_h
        w = int(h * ratio)

    x = (img_w - w) // 2
    y = (img_h - h) // 2
    return x, y, w, h


@st.dialog("Editor", width="large")
def open_editor_dialog(fpath: str, T: dict):
    validate_image_file(fpath)
    file_id = os.path.basename(fpath)

    with Image.open(fpath) as img_temp:
        img_full = ImageOps.exif_transpose(img_temp).convert("RGB")

    img_proxy, scale = create_proxy_image(img_full)
    pw, ph = img_proxy.size

    state = st.session_state
    state.setdefault("rect", None)
    state.setdefault("aspect", None)

    col_canvas, col_controls = st.columns([3, 1], gap="small")

    with col_controls:
        aspect_name = st.selectbox(
            T.get("lbl_aspect", "Aspect"),
            list(config.ASPECT_RATIOS.keys())
        )
        aspect = config.ASPECT_RATIOS[aspect_name]
        state["aspect"] = aspect

        if state["rect"]:
            mw = int(state["rect"][2] * scale)
            mh = int(state["rect"][3] * scale)
        else:
            mw, mh = img_full.size

        manual_w = st.number_input("Width", 10, img_full.width, mw, step=1)
        manual_h = st.number_input("Height", 10, img_full.height, mh, step=1)

        if st.button("Apply Size"):
            rw = min(int(manual_w / scale), pw)
            rh = min(int(manual_h / scale), ph)
            rx = (pw - rw) // 2
            ry = (ph - rh) // 2
            state["rect"] = (rx, ry, rw, rh)

        if st.button("MAX"):
            state["rect"] = calculate_max_crop(pw, ph, aspect)

    with col_canvas:
        rect = st_cropper(
            img_proxy,
            aspect_ratio=state["aspect"],
            realtime_update=True,
            return_type="box",
            key="stable_cropper"
        )

        if rect:
            state["rect"] = (
                int(rect["left"]),
                int(rect["top"]),
                int(rect["width"]),
                int(rect["height"])
            )

    if state["rect"] and st.button(T.get("btn_save_edit", "Save"), type="primary"):
        x, y, w, h = state["rect"]
        crop = (
            int(x * scale),
            int(y * scale),
            int((x + w) * scale),
            int((y + h) * scale),
        )
        img_full.crop(crop).save(fpath, quality=95, subsampling=0, optimize=True)
        state.clear()
        st.toast(T.get("msg_edit_saved", "Saved"))
        st.rerun()
