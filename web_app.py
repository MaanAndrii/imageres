"""
Watermarker Pro v8.0 - Main Application
========================================
Зміни v8.0:
- Batch rename preview (таблиця до обробки)
- Порівняння до/після (дві колонки у preview)
- Drag-and-drop порядок через streamlit-sortables
- SVG вотермарка (через resvg-py)
- Індикатор підтримки HEIC у sidebar
- Зведена статистика після batch
- Кнопка скасування обробки (CancellationToken)
- Рефакторинг: utils розбито на session/preset/file_manager

Виправлені баги:
- Редактор відкривався самовільно при кожному rerun (editor_open flag)
- wm_file у правій колонці тепер через session_state, не через scope
- out_quality_key читається через .get() з дефолтом
- process_list більше не визначається двічі
- files_map більше не перевизначається у правій колонці
"""

import streamlit as st
import io
import os
import zipfile
import concurrent.futures
import gc
import pandas as pd
from PIL import Image

import config
import watermarker_engine as engine
import editor_module as editor
import translations as T_DATA
import utils
from logger import get_logger
from validators import ValidationError
from watermarker_engine import CancellationToken

logger = get_logger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# SETUP
# ─────────────────────────────────────────────────────────────────────────────
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

logger.info(f"App started - Language: {lang_code}")

# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header(T['sb_config'])

    # Індикатор форматів
    with st.expander("📷 Формати", expanded=False):
        if engine.is_heic_available():
            st.success(T['heic_available'])
        else:
            st.warning(T['heic_unavailable'])
        if not engine.is_svg_available():
            st.info(T['msg_svg_no_cairosvg'])

    # PRESETS
    with st.expander(T['sec_presets'], expanded=False):
        uploaded_preset = st.file_uploader(
            T['lbl_load_preset'],
            type=['json'],
            key='preset_uploader'
        )
        if uploaded_preset is not None:
            if f"processed_{uploaded_preset.name}" not in st.session_state:
                success, error = utils.apply_settings_from_json(uploaded_preset)
                if success:
                    st.session_state[f"processed_{uploaded_preset.name}"] = True
                    st.success(T['msg_preset_loaded'])
                    logger.info("Preset loaded successfully")
                    st.rerun()
                else:
                    st.error(T['error_preset'].format(error))
                    logger.error(f"Preset load failed: {error}")

        st.divider()
        current_wm_file = st.session_state.get('wm_uploader_obj')
        json_str = utils.get_current_settings_json(current_wm_file)
        st.download_button(
            label=T['btn_save_preset'],
            data=json_str,
            file_name=f"watermarker_preset_{lang_code}.json",
            mime="application/json",
            use_container_width=True
        )

    # FILE SETTINGS
    with st.expander(T['sec_file']):
        st.selectbox(T['lbl_format'], config.SUPPORTED_OUTPUT_FORMATS, key='out_fmt_key')
        out_fmt = st.session_state['out_fmt_key']
        if out_fmt != "PNG":
            st.slider(T['lbl_quality'], 50, 100, 80, 5, key='out_quality_key')
        st.selectbox(
            T['lbl_naming'],
            ["Keep Original", "Prefix + Sequence"],
            key='naming_mode_key'
        )
        st.text_input(T['lbl_prefix'], placeholder="img", key='naming_prefix_key')

    # GEOMETRY
    with st.expander(T['sec_geo'], expanded=True):
        resize_on = st.checkbox(T['chk_resize'], value=True, key='resize_enabled')
        st.selectbox(
            T['lbl_mode'],
            ["Max Side", "Exact Width", "Exact Height"],
            disabled=not resize_on,
            key='resize_mode'
        )
        c1, c2, c3 = st.columns(3)

        def set_res(val):
            st.session_state['resize_val_state'] = val

        c1.button(T['btn_preset_hd'],  on_click=set_res, args=(config.RESIZE_PRESETS['HD'],),  use_container_width=True)
        c2.button(T['btn_preset_fhd'], on_click=set_res, args=(config.RESIZE_PRESETS['FHD'],), use_container_width=True)
        c3.button(T['btn_preset_4k'],  on_click=set_res, args=(config.RESIZE_PRESETS['4K'],),  use_container_width=True)
        st.number_input(
            T['lbl_px'],
            min_value=config.MIN_IMAGE_DIMENSION,
            max_value=config.MAX_IMAGE_DIMENSION,
            key='resize_val_state',
            disabled=not resize_on
        )

    # WATERMARK
    with st.expander(T['sec_wm'], expanded=True):
        tab1, tab2 = st.tabs([T['tab_logo'], T['tab_text']])

        with tab1:
            wm_file = st.file_uploader(
                T['lbl_logo_up'],
                type=config.SUPPORTED_WATERMARK_FORMATS,
                key="wm_uploader"
            )
            # Зберігаємо в session_state — використовується в правій колонці
            st.session_state['wm_uploader_obj'] = wm_file
            if wm_file:
                st.session_state['preset_wm_filename_key'] = wm_file.name.lower()

            if not wm_file and st.session_state.get('preset_wm_bytes_key'):
                st.info(T['msg_preset_logo_active'])
                try:
                    preset_img = Image.open(io.BytesIO(st.session_state['preset_wm_bytes_key']))
                    st.image(preset_img, width=150)
                except Exception as e:
                    logger.error(f"Failed to display preset logo: {e}")

        with tab2:
            st.text_area(T['lbl_text_input'], key='wm_text_key', height=100)
            fonts = utils.get_available_fonts()
            if fonts:
                f_idx = 0
                current_f = st.session_state.get('font_name_key')
                if current_f and current_f in fonts:
                    f_idx = fonts.index(current_f)
                st.selectbox(T['lbl_font'], fonts, index=f_idx, key='font_name_key')
            else:
                st.caption(T['msg_no_fonts'])
            st.color_picker(T['lbl_color'], '#FFFFFF', key='wm_text_color_key')

        st.divider()
        wm_pos = st.selectbox(
            T['lbl_pos'],
            ['bottom-right', 'bottom-left', 'top-right', 'top-left', 'center', 'tiled'],
            key='wm_pos_key',
            on_change=utils.handle_pos_change
        )
        st.slider(T['lbl_scale'], config.MIN_WATERMARK_SCALE, config.MAX_WATERMARK_SCALE, key='wm_scale_key')
        st.slider(T['lbl_opacity'], config.MIN_OPACITY, config.MAX_OPACITY, key='wm_opacity_key', step=0.05)
        if wm_pos == 'tiled':
            st.slider(T['lbl_gap'], 0, 200, key='wm_gap_key')
        else:
            st.slider(T['lbl_margin'], 0, 100, key='wm_margin_key')
        st.slider(T['lbl_angle'], -180, 180, key='wm_angle_key')

    # PERFORMANCE
    with st.expander(T['sec_perf'], expanded=False):
        max_threads = st.slider(
            T['lbl_threads'],
            config.MIN_THREADS, config.MAX_THREADS, config.DEFAULT_THREADS,
            help=T['help_threads']
        )

    st.divider()
    if st.button(T['btn_defaults'], on_click=utils.reset_settings, use_container_width=True):
        st.rerun()

    with st.expander(T['about_expander'], expanded=False):
        st.markdown(T['about_prod'])
        st.markdown(T['about_auth'])
        st.markdown(T['about_lic'])
        st.markdown(T['about_repo'])
        st.caption(T['about_copy'])
    with st.expander(T['about_changelog_title']):
        st.markdown(T['about_changelog'])

    st.divider()
    st.caption(T['lang_select'])
    lc1, lc2 = st.columns(2)
    with lc1:
        if st.button("🇺🇦 UA", type="primary" if lang_code == 'ua' else "secondary", use_container_width=True):
            st.session_state['lang_code'] = 'ua'
            st.rerun()
    with lc2:
        if st.button("🇺🇸 EN", type="primary" if lang_code == 'en' else "secondary", use_container_width=True):
            st.session_state['lang_code'] = 'en'
            st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# MAIN LAYOUT
# ─────────────────────────────────────────────────────────────────────────────
st.title(T['title'])
st.caption(T['subtitle'])

c_left, c_right = st.columns([1.8, 1], gap="large")

# ─────────────────────────────────────────────────────────────────────────────
# LEFT COLUMN: WORKSPACE
# ─────────────────────────────────────────────────────────────────────────────
with c_left:
    col_head, col_clear = st.columns([2, 1])
    with col_head:
        st.subheader(T['files_header'])
    with col_clear:
        if st.button(T['btn_clear_workspace'], type="secondary", use_container_width=True):
            utils.cleanup_temp_directory()
            st.session_state['file_cache'] = {}
            st.session_state['file_order'] = []
            st.session_state['selected_files'] = set()
            st.session_state['uploader_key'] += 1
            st.session_state['results'] = None
            logger.info("Workspace cleared")
            st.rerun()

    has_files = len(st.session_state['file_cache']) > 0

    # FILE UPLOADER
    with st.expander(T['expander_add_files'], expanded=not has_files):
        uploaded = st.file_uploader(
            T['uploader_label'],
            type=['jpg', 'jpeg', 'png', 'webp', 'heic', 'heif'],
            accept_multiple_files=True,
            label_visibility="collapsed",
            key=f"up_{st.session_state['uploader_key']}"
        )

    if uploaded:
        for f in uploaded:
            try:
                fpath, fname = utils.save_uploaded_file(f)
                if fname not in st.session_state['file_cache']:
                    st.session_state['file_cache'][fname] = fpath
                    st.session_state['file_order'].append(fname)
                    logger.info(f"File uploaded: {fname}")
            except Exception as e:
                st.error(f"Failed to upload {f.name}: {e}")
                logger.error(f"Upload failed for {f.name}: {e}")
        st.session_state['uploader_key'] += 1
        st.rerun()

    # Єдине визначення files_map для всього лівого стовпця
    files_map = st.session_state['file_cache']

    # Синхронізуємо file_order: видаляємо відсутні, додаємо нові
    st.session_state['file_order'] = [f for f in st.session_state['file_order'] if f in files_map]
    for fname in files_map:
        if fname not in st.session_state['file_order']:
            st.session_state['file_order'].append(fname)
    files_names = st.session_state['file_order']

    # ── FILE GRID ──────────────────────────────────────────────────────────
    if files_names:
        act1, act2, act3 = st.columns([1, 1, 1])
        with act1:
            if st.button(T['grid_select_all'], use_container_width=True):
                st.session_state['selected_files'] = set(files_names)
                st.rerun()
        with act2:
            if st.button(T['grid_deselect_all'], use_container_width=True):
                st.session_state['selected_files'].clear()
                st.rerun()
        with act3:
            sel_count = len(st.session_state['selected_files'])
            if st.button(
                f"{T['grid_delete']} ({sel_count})",
                type="primary",
                use_container_width=True,
                disabled=sel_count == 0
            ):
                for f in list(st.session_state['selected_files']):
                    if f in files_map:
                        try:
                            os.remove(files_map[f])
                        except Exception as e:
                            logger.error(f"Failed to delete {f}: {e}")
                        del files_map[f]
                st.session_state['file_order'] = [
                    x for x in st.session_state['file_order']
                    if x not in st.session_state['selected_files']
                ]
                st.session_state['selected_files'].clear()
                logger.info(f"Deleted {sel_count} files")
                st.rerun()

        st.divider()

        cols_count = 4
        cols = st.columns(cols_count)
        for i, fname in enumerate(files_names):
            col = cols[i % cols_count]
            fpath = files_map[fname]
            with col:
                try:
                    thumb = engine.get_thumbnail(fpath)
                    if thumb:
                        st.image(thumb, use_container_width=True)
                    else:
                        st.warning("⚠️")
                except Exception as e:
                    st.error(f"Error: {e}")
                    logger.error(f"Thumbnail display failed for {fname}: {e}")

                is_sel = fname in st.session_state['selected_files']
                if st.button(
                    T['btn_selected'] if is_sel else T['btn_select'],
                    key=f"btn_{fname}",
                    type="primary" if is_sel else "secondary",
                    use_container_width=True
                ):
                    if is_sel:
                        st.session_state['selected_files'].remove(fname)
                    else:
                        st.session_state['selected_files'].add(fname)
                    st.rerun()

        st.caption(T['stat_files_selected'].format(
            len(files_names), len(st.session_state['selected_files'])
        ))

        # ── DRAG-AND-DROP ORDER ───────────────────────────────────────────
        with st.expander(T['sec_order'], expanded=False):
            st.caption(T['order_hint'])
            try:
                from streamlit_sortables import sort_items
                sorted_order = sort_items(
                    files_names,
                    direction="vertical",
                    key="sortable_files"
                )
                if sorted_order != st.session_state['file_order']:
                    st.session_state['file_order'] = sorted_order
                    st.rerun()
            except ImportError:
                st.info("Для drag-and-drop встановіть: pip install streamlit-sortables")
                for i, fname in enumerate(files_names, 1):
                    st.text(f"{i}. {fname}")

        # ── BATCH RENAME PREVIEW ──────────────────────────────────────────
        # process_list визначається один раз тут і використовується далі
        process_list = [f for f in files_names if f in st.session_state['selected_files']]

        if process_list:
            with st.expander(T['sec_rename_preview'], expanded=False):
                out_ext = st.session_state.get('out_fmt_key', 'JPEG').lower()
                naming_mode = st.session_state.get('naming_mode_key', 'Keep Original')
                prefix = st.session_state.get('naming_prefix_key', '')

                preview_rows = []
                for i, fname in enumerate(process_list, 1):
                    new_name = engine.generate_filename(
                        files_map[fname], naming_mode, prefix, out_ext, i
                    )
                    preview_rows.append({
                        T['rename_col_original']: fname,
                        T['rename_col_output']:   new_name,
                    })
                st.dataframe(pd.DataFrame(preview_rows), use_container_width=True, hide_index=True)

    else:
        # Немає файлів — порожній process_list
        process_list = []

    # ── PROCESS / CANCEL BUTTONS ──────────────────────────────────────────
    can_process = len(process_list) > 0 and not st.session_state.get('processing_active', False)

    btn_col1, btn_col2 = st.columns([3, 1])
    with btn_col1:
        start_clicked = st.button(
            T['btn_process'],
            type="primary",
            use_container_width=True,
            disabled=not can_process
        )
    with btn_col2:
        # Кнопка скасування завжди активна — Streamlit однопоточний,
        # тому cancel спрацює на наступному rerun після натискання Start
        cancel_clicked = st.button(
            T['btn_cancel'],
            type="secondary",
            use_container_width=True
        )

    if cancel_clicked and st.session_state.get('cancel_token'):
        st.session_state['cancel_token'].cancel()
        logger.info("Cancellation requested by user")

    if start_clicked and can_process:
        token = CancellationToken()
        st.session_state['cancel_token'] = token
        st.session_state['processing_active'] = True

        progress    = st.progress(0)
        status_text = st.empty()
        cancel_info = st.empty()

        try:
            selected_font = st.session_state.get('font_name_key')
            # wm_file береться з session_state — надійніше ніж scope з sidebar
            _wm_file = st.session_state.get('wm_uploader_obj')
            wm_obj      = utils.prepare_watermark_object(_wm_file, selected_font)
            resize_cfg  = utils.get_resize_config()

            results    = []
            report     = []
            zip_buffer = io.BytesIO()
            cancelled  = False

            logger.info(f"Starting batch processing: {len(process_list)} files")

            with concurrent.futures.ThreadPoolExecutor(max_workers=max_threads) as executor:
                futures = {}
                for i, fname in enumerate(process_list):
                    fpath = files_map[fname]
                    new_fname = engine.generate_filename(
                        fpath,
                        st.session_state['naming_mode_key'],
                        st.session_state['naming_prefix_key'],
                        st.session_state['out_fmt_key'].lower(),
                        i + 1
                    )
                    future = executor.submit(
                        engine.process_image,
                        fpath, new_fname, wm_obj, resize_cfg,
                        st.session_state['out_fmt_key'],
                        st.session_state.get('out_quality_key', 80),  # .get() — PNG не має слайдера
                        token
                    )
                    futures[future] = fname

                with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                    for i, fut in enumerate(concurrent.futures.as_completed(futures)):
                        fname = futures[fut]

                        if token.is_cancelled():
                            cancelled = True
                            for pending in futures:
                                pending.cancel()
                            break

                        status_text.text(f"{T['msg_processing']} {fname}")
                        try:
                            res_bytes, stats = fut.result()
                            zf.writestr(stats['filename'], res_bytes)
                            results.append((stats['filename'], res_bytes))
                            report.append(stats)
                            del res_bytes
                            gc.collect()
                        except InterruptedError:
                            cancelled = True
                            break
                        except Exception as e:
                            st.error(f"❌ Error processing {fname}: {e}")
                            logger.error(f"Processing failed for {fname}: {e}", exc_info=True)

                        progress.progress((i + 1) / len(process_list))

            if cancelled:
                cancel_info.warning(T['msg_cancelled'])
                logger.info(f"Batch cancelled. Processed {len(results)}/{len(process_list)}")
            else:
                status_text.empty()
                st.toast(T['msg_done'], icon='🎉')
                logger.info(f"Batch completed: {len(results)} files")

            if results:
                utils.safe_state_update('results', {
                    'zip':    zip_buffer.getvalue(),
                    'files':  results,
                    'report': report
                })

        except ValidationError as e:
            st.error(f"❌ Validation error: {e}")
            logger.error(f"Validation failed: {e}")
        except Exception as e:
            st.error(T['error_wm_load'].format(e))
            logger.error(f"Processing failed: {e}", exc_info=True)
        finally:
            st.session_state['processing_active'] = False
            st.session_state['cancel_token'] = None

    # ── RESULTS ───────────────────────────────────────────────────────────
    if st.session_state.get('results'):
        res = st.session_state['results']
        st.success(f"✅ {T['msg_done']} {len(res['files'])} files processed")

        st.download_button(
            T['btn_dl_zip'],
            res['zip'],
            f"watermarked_{len(res['files'])}_photos.zip",
            "application/zip",
            type="primary",
            use_container_width=True
        )

        with st.expander(T['exp_dl_separate']):
            for name, data in res['files']:
                c1, c2 = st.columns([3, 1])
                c1.write(f"📄 {name}")
                c2.download_button("⬇️", data, file_name=name, key=f"dl_{name}")

        # ── PROCESSING STATS ─────────────────────────────────────────────
        with st.expander(T['sec_stats'], expanded=True):
            rpt          = res['report']
            total_before = sum(r['orig_size'] for r in rpt)
            total_after  = sum(r['new_size']  for r in rpt)
            avg_compr    = (total_before - total_after) / total_before * 100 if total_before > 0 else 0

            s1, s2, s3, s4 = st.columns(4)
            s1.metric(T['stats_total_files'],  len(rpt))
            s2.metric(T['stats_total_before'], f"{total_before / 1024 / 1024:.1f} MB")
            s3.metric(
                T['stats_total_after'],
                f"{total_after / 1024 / 1024:.1f} MB",
                f"{(total_after - total_before) / 1024 / 1024:+.1f} MB",
                delta_color="inverse"
            )
            s4.metric(T['stats_avg_compression'], f"{avg_compr:.1f}%")

            df = pd.DataFrame([{
                T['rename_col_output']:   r['filename'],
                T['rename_col_original']: r['orig_res'],
                "→":                      r['new_res'],
                "До (KB)":                f"{r['orig_size'] / 1024:.0f}",
                "Після (KB)":             f"{r['new_size'] / 1024:.0f}",
                "Scale":                  r['scale_factor'],
            } for r in rpt])
            st.dataframe(df, use_container_width=True, hide_index=True)


# ─────────────────────────────────────────────────────────────────────────────
# RIGHT COLUMN: PREVIEW + BEFORE/AFTER
# ─────────────────────────────────────────────────────────────────────────────
with c_right:
    st.subheader(T['prev_header'])

    selected_list = list(st.session_state['selected_files'])
    target_file   = selected_list[-1] if selected_list else None
    # Використовуємо вже визначений files_map — не перевизначаємо
    files_map     = st.session_state['file_cache']

    with st.container(border=True):
        if target_file and target_file in files_map:
            fpath = files_map[target_file]

            # ── EDITOR ────────────────────────────────────────────────────
            # Натискання кнопки встановлює editing_file + editor_open=True.
            # editor_open скидається після закриття діалогу.
            # Це єдиний надійний спосіб уникнути самовільного відкриття при rerun.
            if st.button(T['btn_open_editor'], type="primary", use_container_width=True):
                st.session_state['editing_file'] = fpath
                st.session_state['editor_open']  = True
                st.session_state['close_editor'] = False

            # Відкриваємо лише якщо editor_open явно True для саме цього файлу
            if (st.session_state.get('editor_open') and
                    st.session_state.get('editing_file') == fpath and
                    not st.session_state.get('close_editor')):
                editor.open_editor_dialog(fpath, T)

            # Після закриття скидаємо всі прапори
            if st.session_state.get('close_editor'):
                st.session_state['editing_file'] = None
                st.session_state['editor_open']  = False
                st.session_state['close_editor'] = False

            st.divider()

            # ── PREVIEW + BEFORE/AFTER ────────────────────────────────────
            try:
                selected_font = st.session_state.get('font_name_key')
                # wm_file з session_state — не залежимо від scope sidebar
                _wm_file_preview = st.session_state.get('wm_uploader_obj')
                wm_obj     = utils.prepare_watermark_object(_wm_file_preview, selected_font)
                resize_cfg = utils.get_resize_config()

                preview_fname = engine.generate_filename(
                    fpath,
                    st.session_state['naming_mode_key'],
                    st.session_state['naming_prefix_key'],
                    st.session_state['out_fmt_key'].lower(),
                    1
                )

                with st.spinner(T['msg_processing']):
                    prev_bytes, stats = engine.process_image(
                        fpath, preview_fname, wm_obj, resize_cfg,
                        st.session_state['out_fmt_key'],
                        st.session_state.get('out_quality_key', 80)
                    )

                # Before / After
                st.subheader(T['sec_compare'])
                ba1, ba2 = st.columns(2)
                with ba1:
                    st.caption(T['compare_before'])
                    st.image(fpath, use_container_width=True)
                with ba2:
                    st.caption(T['compare_after'])
                    st.image(prev_bytes, use_container_width=True)

                st.divider()

                m1, m2 = st.columns(2)
                delta_size = (stats['new_size'] - stats['orig_size']) / stats['orig_size'] * 100
                m1.metric(T['stat_res'],  stats['new_res'], stats['scale_factor'])
                m2.metric(
                    T['stat_size'],
                    f"{stats['new_size'] / 1024:.1f} KB",
                    f"{delta_size:.1f}%",
                    delta_color="inverse"
                )

            except ValidationError as e:
                st.error(f"❌ Validation error: {e}")
                logger.error(f"Preview validation failed: {e}")
            except Exception as e:
                st.error(f"{T['msg_preview_error']}: {e}")
                logger.error(f"Preview generation failed: {e}", exc_info=True)

        else:
            st.markdown(
                f"""<div class="preview-placeholder">
                    <span class="preview-icon">🖼️</span>
                    <p>{T['prev_placeholder']}</p>
                </div>""",
                unsafe_allow_html=True
            )


# ─────────────────────────────────────────────────────────────────────────────
# CLEANUP ON EXIT
# ─────────────────────────────────────────────────────────────────────────────
import atexit


def _cleanup():
    try:
        temp_dir = st.session_state.get('temp_dir')
        if temp_dir and os.path.exists(temp_dir):
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
            logger.info("Exit cleanup completed")
    except Exception as e:
        logger.error(f"Exit cleanup failed: {e}")


atexit.register(_cleanup)
