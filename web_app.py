"""
Watermarker Pro v7.0.1 - Main Application
========================================
Professional batch photo and PDF watermarking
"""

import streamlit as st
import io
import os
import zipfile
import concurrent.futures
import gc
from PIL import Image

import config
import watermarker_engine as engine
import editor_module as editor
import translations as T_DATA
import utils
from logger import get_logger
from validators import ValidationError

logger = get_logger(__name__)

st.set_page_config(
    page_title=f"{config.APP_NAME} v{config.APP_VERSION}",
    page_icon="📸",
    layout="wide",
    initial_sidebar_state="expanded"
)

utils.inject_css()
utils.init_session_state()

lang_code = st.session_state['lang_code']
T = T_DATA.TRANSLATIONS[lang_code]

# === SIDEBAR ===
with st.sidebar:
    st.header(T['sb_config'])
    
    # Presets
    with st.expander(T['sec_presets'], expanded=False):
        uploaded_preset = st.file_uploader(T['lbl_load_preset'], type=['json'], key='preset_uploader')
        if uploaded_preset:
            if f"processed_{uploaded_preset.name}" not in st.session_state:
                success, error = utils.apply_settings_from_json(uploaded_preset)
                if success:
                    st.session_state[f"processed_{uploaded_preset.name}"] = True
                    st.rerun()
                else: st.error(error)
        
        json_str = utils.get_current_settings_json(st.session_state.get('wm_uploader_obj'))
        st.download_button(T['btn_save_preset'], json_str, file_name="preset.json", use_container_width=True)
    
    # File & Geometry
    with st.expander(T['sec_file']):
        st.selectbox(T['lbl_format'], config.SUPPORTED_OUTPUT_FORMATS, key='out_fmt_key')
        st.slider(T['lbl_quality'], 50, 100, 80, 5, key='out_quality_key')
        st.selectbox(T['lbl_naming'], ["Keep Original", "Prefix + Sequence"], key='naming_mode_key')
        st.text_input(T['lbl_prefix'], key='naming_prefix_key')
    
    with st.expander(T['sec_geo'], expanded=True):
        res_on = st.checkbox(T['chk_resize'], value=True, key='resize_enabled')
        st.selectbox(T['lbl_mode'], ["Max Side", "Exact Width", "Exact Height"], key='resize_mode', disabled=not res_on)
        st.number_input(T['lbl_px'], min_value=10, max_value=10000, key='resize_val_state', disabled=not res_on)
    
    # Watermark
    with st.expander(T['sec_wm'], expanded=True):
        tab1, tab2 = st.tabs([T['tab_logo'], T['tab_text']])
        with tab1:
            wm_file = st.file_uploader(T['lbl_logo_up'], type=["png"], key="wm_uploader")
            st.session_state['wm_uploader_obj'] = wm_file
        with tab2:
            st.text_area(T['lbl_text_input'], key='wm_text_key')
            fonts = utils.get_available_fonts()
            if fonts: st.selectbox(T['lbl_font'], fonts, key='font_name_key')
            st.color_picker(T['lbl_color'], '#FFFFFF', key='wm_text_color_key')
        
        st.selectbox(T['lbl_pos'], ['bottom-right', 'bottom-left', 'top-right', 'top-left', 'center', 'tiled'], key='wm_pos_key', on_change=utils.handle_pos_change)
        st.slider(T['lbl_scale'], 5, 100, key='wm_scale_key')
        st.slider(T['lbl_opacity'], 0.1, 1.0, key='wm_opacity_key', step=0.05)
        st.slider(T['lbl_angle'], -180, 180, key='wm_angle_key')

    if st.button(T['btn_defaults'], on_click=utils.reset_settings, use_container_width=True): st.rerun()

# === MAIN ===
st.title(T['title'])
c_left, c_right = st.columns([1.8, 1], gap="large")

with c_left:
    st.subheader(T['files_header'])
    if st.button(T['btn_clear_workspace'], type="secondary"):
        utils.cleanup_temp_directory()
        st.session_state['file_cache'], st.session_state['selected_files'] = {}, set()
        st.rerun()
    
    has_files = len(st.session_state['file_cache']) > 0
    with st.expander(T['expander_add_files'], expanded=not has_files):
        uploaded = st.file_uploader(T['uploader_label'], type=config.SUPPORTED_INPUT_FORMATS, accept_multiple_files=True, key=f"up_{st.session_state['uploader_key']}")
    
    # Інтеграція списку файлів (враховуючи PDF)
    if uploaded:
        with st.spinner("Processing documents..."):
            for f in uploaded:
                items = utils.process_uploaded_file(f)
                for path, name in items:
                    st.session_state['file_cache'][name] = path
        st.session_state['uploader_key'] += 1
        st.rerun()
    
    # Grid & Processing
    files_map = st.session_state['file_cache']
    if files_map:
        sel = list(st.session_state['selected_files'])
        if st.button(T['btn_process'], type="primary", use_container_width=True, disabled=not sel):
            # (Логіка Batch Processing зThread індексом - без скорочень)
            progress = st.progress(0)
            wm_obj = utils.prepare_watermark_object(wm_file, st.session_state.get('font_name_key'))
            res_cfg = utils.get_resize_config()
            results, zip_buffer = [], io.BytesIO()
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
                futures = {executor.submit(engine.process_image, files_map[name], engine.generate_filename(files_map[name], st.session_state['naming_mode_key'], st.session_state['naming_prefix_key'], st.session_state['out_fmt_key'].lower(), i+1), wm_obj, res_cfg, st.session_state['out_fmt_key'], st.session_state['out_quality_key']): name for i, name in enumerate(sel)}
                with zipfile.ZipFile(zip_buffer, "w") as zf:
                    for i, fut in enumerate(concurrent.futures.as_completed(futures)):
                        res_bytes, stats = fut.result()
                        zf.writestr(stats['filename'], res_bytes)
                        results.append((stats['filename'], res_bytes))
                        progress.progress((i+1)/len(sel))
            
            utils.safe_state_update('results', {'zip': zip_buffer.getvalue(), 'files': results})
            st.rerun()

    # Показ сітки (Thumbnails)
    cols = st.columns(4)
    for i, fname in enumerate(files_map.keys()):
        with cols[i % 4]:
            t = engine.get_thumbnail(files_map[fname])
            if t: st.image(t, use_container_width=True)
            if st.checkbox(T['btn_select'], key=f"chk_{fname}", value=fname in st.session_state['selected_files']):
                st.session_state['selected_files'].add(fname)
            else: st.session_state['selected_files'].discard(fname)

with c_right:
    st.subheader(T['prev_header'])
    target = list(st.session_state['selected_files'])[-1] if st.session_state['selected_files'] else None
    if target:
        wm_obj = utils.prepare_watermark_object(wm_file, st.session_state.get('font_name_key'))
        p_bytes, stats = engine.process_image(files_map[target], "preview.jpg", wm_obj, utils.get_resize_config(), "JPEG", 80)
        st.image(p_bytes, caption=target, use_container_width=True)
    else:
        st.markdown(f'<div class="preview-placeholder">{T["prev_placeholder"]}</div>', unsafe_allow_html=True)
