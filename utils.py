"""
Watermarker Pro v7.0 - Utils Module
====================================
File handling with PDF splitting support
"""

import streamlit as st
import os
import json
import tempfile
import shutil
import threading
from typing import Dict, List, Tuple, Optional
from datetime import datetime
import config
import watermarker_engine as engine
from logger import get_logger
from validators import sanitize_filename

logger = get_logger(__name__)
_session_lock = threading.Lock()

def inject_css():
    st.markdown("""
    <style>
        div[data-testid="column"] { background-color: #f8f9fa; border-radius: 8px; padding: 10px; border: 1px solid #eee; }
        .preview-placeholder { border: 2px dashed #e0e0e0; border-radius: 10px; padding: 40px; text-align: center; color: #888; }
    </style>
    """, unsafe_allow_html=True)

def init_session_state():
    """Initializes all state variables"""
    if 'temp_dir' not in st.session_state:
        st.session_state['temp_dir'] = tempfile.mkdtemp(prefix="wm_pro_v7_")
    if 'file_cache' not in st.session_state: st.session_state['file_cache'] = {}
    if 'selected_files' not in st.session_state: st.session_state['selected_files'] = set()
    if 'uploader_key' not in st.session_state: st.session_state['uploader_key'] = 0
    if 'lang_code' not in st.session_state: st.session_state['lang_code'] = 'ua'
    if 'editing_file' not in st.session_state: st.session_state['editing_file'] = None
    if 'close_editor' not in st.session_state: st.session_state['close_editor'] = False
    if 'results' not in st.session_state: st.session_state['results'] = None
    
    for key, value in config.DEFAULT_SETTINGS.items():
        kn = f'{key}_key' if not key.endswith('_val') else f'{key}_state'
        if kn not in st.session_state: st.session_state[kn] = value

def process_uploaded_file(uploaded_file) -> List[Tuple[str, str]]:
    """
    Обробляє завантажений файл. PDF розбивається на окремі зображення.
    """
    try:
        temp_dir = st.session_state['temp_dir']
        safe_name = sanitize_filename(uploaded_file.name)
        ext = os.path.splitext(safe_name)[1].lower()
        
        raw_path = os.path.join(temp_dir, f"raw_{datetime.now().strftime('%H%M%S')}_{safe_name}")
        with open(raw_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        
        output_items = []
        if ext == '.pdf':
            # Розбиття PDF на сторінки
            pages = engine.convert_pdf_to_images(raw_path)
            base = os.path.splitext(safe_name)[0]
            for i, page_img in enumerate(pages):
                p_name = f"{base}_p{i+1}.jpg"
                p_path = os.path.join(temp_dir, p_name)
                page_img.save(p_path, "JPEG", quality=90)
                output_items.append((p_path, p_name))
            os.remove(raw_path)
        else:
            final_path = os.path.join(temp_dir, safe_name)
            if os.path.exists(final_path):
                final_path = os.path.join(temp_dir, f"{datetime.now().strftime('%H%M%S')}_{safe_name}")
            shutil.move(raw_path, final_path)
            output_items.append((final_path, os.path.basename(final_path)))
            
        return output_items
    except Exception as e:
        logger.error(f"Upload processing failed: {e}")
        return []

def cleanup_temp_directory():
    try:
        shutil.rmtree(st.session_state['temp_dir'], ignore_errors=True)
        st.session_state['temp_dir'] = tempfile.mkdtemp(prefix="wm_pro_v7_")
    except Exception: pass

def get_available_fonts():
    d = config.get_fonts_dir()
    if not d.exists(): return []
    return sorted([f.name for f in list(d.glob("*.ttf")) + list(d.glob("*.otf"))])

def handle_pos_change():
    p = st.session_state.get('wm_pos_key', 'bottom-right')
    s = config.TILED_SETTINGS if p == 'tiled' else config.CORNER_SETTINGS
    for k, v in s.items(): st.session_state[f'{k}_key'] = v

def reset_settings():
    for k, v in config.DEFAULT_SETTINGS.items():
        kn = f'{k}_key' if not k.endswith('_val') else f'{k}_state'
        st.session_state[kn] = v

def get_current_settings_json(wm_file):
    b64 = engine.image_to_base64(wm_file.getvalue()) if wm_file else None
    if not b64 and st.session_state.get('preset_wm_bytes_key'):
        b64 = engine.image_to_base64(st.session_state['preset_wm_bytes_key'])
    
    s = {
        'version': config.APP_VERSION,
        'resize_val': st.session_state.get('resize_val_state'),
        'wm_pos': st.session_state.get('wm_pos_key'),
        'wm_scale': st.session_state.get('wm_scale_key'),
        'wm_text': st.session_state.get('wm_text_key'),
        'wm_image_b64': b64
    }
    return json.dumps(s, indent=4)

def apply_settings_from_json(json_file):
    try:
        d = json.load(json_file)
        mapping = {'resize_val': 'resize_val_state', 'wm_pos': 'wm_pos_key', 'wm_scale': 'wm_scale_key', 'wm_text': 'wm_text_key'}
        for k, v in mapping.items():
            if k in d: st.session_state[v] = d[k]
        if d.get('wm_image_b64'):
            st.session_state['preset_wm_bytes_key'] = engine.base64_to_bytes(d['wm_image_b64'])
        return True, None
    except Exception as e: return False, str(e)

def prepare_watermark_object(wm_file, font_name):
    txt = st.session_state.get('wm_text_key', '').strip()
    if txt:
        fp = str(config.get_fonts_dir() / font_name) if font_name else None
        obj = engine.create_text_watermark(txt, fp, 100, st.session_state.get('wm_text_color_key'))
        return engine.apply_opacity(obj, st.session_state.get('wm_opacity_key'))
    
    b = wm_file.getvalue() if wm_file else st.session_state.get('preset_wm_bytes_key')
    if b:
        obj = engine.load_watermark_from_bytes(b)
        return engine.apply_opacity(obj, st.session_state.get('wm_opacity_key'))
    return None

def get_resize_config():
    p = st.session_state.get('wm_pos_key')
    return {
        'enabled': st.session_state.get('resize_enabled'),
        'mode': st.session_state.get('resize_mode'),
        'value': st.session_state.get('resize_val_state'),
        'wm_scale': st.session_state.get('wm_scale_key') / 100,
        'wm_margin': st.session_state.get('wm_margin_key') if p != 'tiled' else 0,
        'wm_gap': st.session_state.get('wm_gap_key') if p == 'tiled' else 0,
        'wm_position': p,
        'wm_angle': st.session_state.get('wm_angle_key')
    }

def safe_state_update(k, v):
    with _session_lock: st.session_state[k] = v
