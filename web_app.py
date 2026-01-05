"""
Watermarker Pro v7.0.1 - Main Application
========================================
Batch watermarking with interactive error notifications
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

st.set_page_config(page_title=f"{config.APP_NAME} v{config.APP_VERSION}", page_icon="📸", layout="wide", initial_sidebar_state="expanded")
utils.inject_css()
utils.init_session_state()

lang_code = st.session_state['lang_code']
T = T_DATA.TRANSLATIONS[lang_code]

# === SIDEBAR ===
with st.sidebar:
    st.header(T['sb_config'])
    
    with st.expander(T['sec_presets'], expanded=False):
        up_preset = st.file_uploader(T['lbl_load_preset'], type=['json'], key='preset_uploader')
        if up_preset:
            if f"proc_{up_preset.name}" not in st.session_state:
                ok, err = utils.apply_settings_from_json(up_preset)
                if ok: st.session_state[f"proc_{up_preset.name}"] = True; st.rerun()
                else: st.error(err)
        json_str = utils.get_current_settings_json(st.session_state.get('wm_uploader_obj'))
        st.download_button(T['btn_save_preset'], json_str, file_name="preset.json", use_container_width=True)

    with st.expander(T['sec_file']):
        st.selectbox(T['lbl_format'], config.SUPPORTED_OUTPUT_FORMATS, key='out_fmt_key')
        st.slider(T['lbl_quality'], 50, 100, 80, 5, key='out_quality_key')
        st.selectbox(T['lbl_naming'], ["Keep Original", "Prefix + Sequence"], key='naming_mode_key')
        st.text_input(T['lbl_prefix'], key='naming_prefix_key')

    with st.expander(T['sec_geo'], expanded=True):
        res_on = st.checkbox(T['chk_resize'], value=True, key='resize_enabled')
        st.selectbox(T['lbl_mode'], ["Max Side", "Exact Width", "Exact Height"], key='resize_mode', disabled=not res_on)
        c1, c2, c3 = st.columns(3)
        c1.button("HD", on_click=lambda: st.session_state.update({'resize_val_state': 1280}))
        c2.button("FHD", on_click=lambda: st.session_state.update({'resize_val_state': 1920}))
        c3.button("4K", on_click=lambda: st.session_state.update({'resize_val_state': 3840}))
        st.number_input(T['lbl_px'], min_value=10, max_value=10000, key='resize_val_state', disabled=not res_on)

    with st.expander(T['sec_wm'], expanded=True):
        t1, t2 = st.tabs([T['tab_logo'], T['tab_text']])
        with t1:
            wm_file = st.file_uploader(T['lbl_logo_up'], type=["png"], key="wm_uploader")
            st.session_state['wm_uploader_obj'] = wm_file
            if not wm_file and st.session_state.get('preset_wm_bytes_key'): st.info(T['msg_preset_logo_active'])
        with t2:
            st.text_area(T['lbl_text_input'], key='wm_text_key')
            fnts = utils.get_available_fonts()
            if fnts: st.selectbox(T['lbl_font'], fnts, key='font_name_key')
            st.color_picker(T['lbl_color'], '#FFFFFF', key='wm_text_color_key')
        
        st.selectbox(T['lbl_pos'], ['bottom-right', 'bottom-left', 'top-right', 'top-left', 'center', 'tiled'], key='wm_pos_key', on_change=utils.handle_pos_change)
        st.slider(T['lbl_scale'], 5, 100, key='wm_scale_key')
        st.slider(T['lbl_opacity'], 0.1, 1.0, key='wm_opacity_key', step=0.05)
        st.slider(T['lbl_angle'], -180, 180, key='wm_angle_key')

    with st.expander(T['sec_perf']):
        threads = st.slider(T['lbl_threads'], 1, 8, config.DEFAULT_THREADS)
    
    if st.button(T['btn_defaults'], on_click=utils.reset_settings, use_container_width=True): st.rerun()
    
    with st.expander(T['about_expander']):
        st.markdown(T['about_prod']); st.markdown(T['about_auth'])
        lc1, lc2 = st.columns(2)
        if lc1.button("🇺🇦 UA", use_container_width=True): st.session_state['lang_code'] = 'ua'; st.rerun()
        if lc2.button("🇺🇸 EN", use_container_width=True): st.session_state['lang_code'] = 'en'; st.rerun()

# === MAIN ===
st.title(T['title'])
c_l, c_r = st.columns([1.8, 1], gap="large")

with c_l:
    st.subheader(T['files_header'])
    if st.button(T['btn_clear_workspace'], type="secondary"):
        utils.cleanup_temp_directory(); st.session_state['file_cache'], st.session_state['selected_files'] = {}, set(); st.rerun()
    
    with st.expander(T['expander_add_files'], expanded=not len(st.session_state['file_cache'])):
        uploaded = st.file_uploader(T['uploader_label'], type=config.SUPPORTED_INPUT_FORMATS, accept_multiple_files=True, key=f"up_{st.session_state['uploader_key']}")
        if uploaded:
            with st.spinner("🔄 Processing files..."):
                for f in uploaded:
                    try:
                        # Спроба обробити файл
                        new_items = utils.process_uploaded_file(f)
                        for path, name in new_items:
                            st.session_state['file_cache'][name] = path
                    except Exception as e:
                        # ПОВІДОМЛЕННЯ ПРО ПОМИЛКУ В UI
                        st.error(f"❌ Error processing '{f.name}': {str(e)}")
                        logger.error(f"UI Error: {str(e)}")
            
            st.session_state['uploader_key'] += 1; st.rerun()
    
    f_map = st.session_state['file_cache']
    if f_map:
        ca1, ca2, ca3 = st.columns(3)
        if ca1.button(T['grid_select_all'], use_container_width=True): st.session_state['selected_files'] = set(f_map.keys()); st.rerun()
        if ca2.button(T['grid_deselect_all'], use_container_width=True): st.session_state['selected_files'].clear(); st.rerun()
        sel = list(st.session_state['selected_files'])
        if ca3.button(f"{T['grid_delete']} ({len(sel)})", type="primary", use_container_width=True, disabled=not sel):
            for f in sel:
                if f in f_map: 
                    if os.path.exists(f_map[f]): os.remove(f_map[f])
                    del f_map[f]
            st.session_state['selected_files'].clear(); st.rerun()
        
        cols = st.columns(4)
        for i, fname in enumerate(f_map.keys()):
            with cols[i % 4]:
                t = engine.get_thumbnail(f_map[fname])
                if t: st.image(t, use_container_width=True)
                is_s = fname in st.session_state['selected_files']
                if st.button(T['btn_selected'] if is_s else T['btn_select'], key=f"b_{fname}", type="primary" if is_s else "secondary", use_container_width=True):
                    if is_s: st.session_state['selected_files'].remove(fname)
                    else: st.session_state['selected_files'].add(fname)
                    st.rerun()
        
        if st.button(T['btn_process'], type="primary", use_container_width=True, disabled=not sel):
            prog = st.progress(0); st_txt = st.empty(); results, z_buf = [], io.BytesIO()
            wm_obj = utils.prepare_watermark_object(wm_file, st.session_state.get('font_name_key'))
            res_cfg = utils.get_resize_config()
            try:
                with concurrent.futures.ThreadPoolExecutor(max_workers=threads) as exc:
                    futures = {exc.submit(engine.process_image, f_map[name], engine.generate_filename(f_map[name], st.session_state['naming_mode_key'], st.session_state['naming_prefix_key'], st.session_state['out_fmt_key'].lower(), i+1), wm_obj, res_cfg, st.session_state['out_fmt_key'], st.session_state['out_quality_key']): name for i, name in enumerate(sel)}
                    with zipfile.ZipFile(z_buf, "w") as zf:
                        for i, fut in enumerate(concurrent.futures.as_completed(futures)):
                            rb, stats = fut.result(); zf.writestr(stats['filename'], rb); results.append((stats['filename'], rb))
                            prog.progress((i+1)/len(sel)); st_txt.text(f"Done: {stats['filename']}")
                utils.safe_state_update('results', {'zip': z_buf.getvalue(), 'files': results})
                st.rerun()
            except Exception as e:
                st.error(f"❌ Processing failed: {str(e)}")

    if st.session_state.get('results'):
        res = st.session_state['results']
        st.success(f"✅ Finished! {len(res['files'])} files processed.")
        st.download_button(T['btn_dl_zip'], res['zip'], "photos.zip", type="primary", use_container_width=True)

with c_r:
    st.subheader(T['prev_header'])
    target = list(st.session_state['selected_files'])[-1] if st.session_state['selected_files'] else None
    if target and target in f_map:
        fpath = f_map[target]
        if st.button(T['btn_open_editor'], type="primary", use_container_width=True):
            st.session_state['editing_file'] = fpath; st.session_state['close_editor'] = False
        if st.session_state.get('editing_file') == fpath and not st.session_state.get('close_editor'):
            editor.open_editor_dialog(fpath, T)
        if st.session_state.get('close_editor'): st.session_state['editing_file'] = None; st.session_state['close_editor'] = False
        
        try:
            wm_obj = utils.prepare_watermark_object(wm_file, st.session_state.get('font_name_key'))
            p_bytes, stats = engine.process_image(fpath, "preview.jpg", wm_obj, utils.get_resize_config(), "JPEG", 80)
            st.image(p_bytes, use_container_width=True)
            m1, m2 = st.columns(2)
            m1.metric(T['stat_res'], stats['new_res']); m2.metric(T['stat_size'], f"{stats['new_size']/1024:.1f} KB")
        except Exception as e:
            st.warning(f"Preview unavailable: {str(e)}")
    else: st.markdown(f'<div class="preview-placeholder">{T["prev_placeholder"]}</div>', unsafe_allow_html=True)
