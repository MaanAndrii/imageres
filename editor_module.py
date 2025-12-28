import streamlit as st
import os
from PIL import Image, ImageOps
from streamlit_cropper import st_cropper
import config 
from logger import get_logger 
from validators import validate_image_file

logger = get_logger(__name__)

# --- FUNCTIONS ---

def get_file_info_str(fpath: str, img: Image.Image) -> str:
    try:
        size_bytes = os.path.getsize(fpath)
        size_mb = size_bytes / (1024 * 1024)
        size_str = f"{size_mb:.2f} MB" if size_mb >= 1 else f"{size_bytes/1024:.1f} KB"
        return f"📄 **{os.path.basename(fpath)}** &nbsp;•&nbsp; 📏 **{img.width}x{img.height}** &nbsp;•&nbsp; 💾 **{size_str}**"
    except Exception:
        return "📄 Інфо недоступне"

def create_proxy_image(img: Image.Image, target_width: int = 700):
    w, h = img.size
    if w <= target_width:
        return img, 1.0
    
    ratio = target_width / w
    new_h = max(1, int(h * ratio))
    proxy = img.resize((target_width, new_h), Image.Resampling.LANCZOS)
    return proxy, w / target_width

def get_center_box_tuple(proxy_w, proxy_h, target_w, target_h):
    """Центрує прямокутник target всередині proxy."""
    # Захист від дурня: якщо target більший за proxy
    target_w = min(target_w, proxy_w)
    target_h = min(target_h, proxy_h)
    
    left = int((proxy_w - target_w) / 2)
    top = int((proxy_h - target_h) / 2)
    
    return (int(left), int(top), int(target_w), int(target_h))

# --- EDITOR ---

@st.dialog("🛠 Editor", width="large")
def open_editor_dialog(fpath: str, T: dict):
    file_id = os.path.basename(fpath)
    
    # 1. KEYS
    k_rot = f"rot_{file_id}"
    k_update = f"upd_{file_id}" 
    k_box = f"box_{file_id}"
    k_aspect = f"asp_{file_id}"
    
    # 2. INIT
    if k_rot not in st.session_state: st.session_state[k_rot] = 0
    if k_update not in st.session_state: st.session_state[k_update] = 0
    if k_box not in st.session_state: st.session_state[k_box] = None
    if k_aspect not in st.session_state: st.session_state[k_aspect] = "Free / Вільний"

    # 3. LOAD
    try:
        validate_image_file(fpath)
        img_orig = Image.open(fpath)
        img_orig = ImageOps.exif_transpose(img_orig)
        img_orig = img_orig.convert('RGB')
        
        if st.session_state[k_rot] != 0:
            img_orig = img_orig.rotate(-st.session_state[k_rot], expand=True)
            
        img_proxy, scale_factor = create_proxy_image(img_orig)
        proxy_w, proxy_h = img_proxy.size
        orig_w, orig_h = img_orig.size
    except Exception as e:
        st.error(f"Error: {e}")
        return

    st.caption(get_file_info_str(fpath, img_orig))

    # 4. ACTIONS (CALLBACKS)
    
    def do_rotate(delta):
        st.session_state[k_rot] += delta
        st.session_state[k_box] = None
        st.session_state[k_update] += 1

    def do_reset():
        st.session_state[k_rot] = 0
        st.session_state[k_box] = None
        st.session_state[k_aspect] = "Free / Вільний"
        st.session_state[k_update] += 1

    def do_max():
        # Отримуємо аспект
        asp_name = st.session_state[k_aspect]
        asp_val = config.ASPECT_RATIOS.get(asp_name, None)
        
        # Рахуємо MAX для проксі
        if asp_val:
            target_r = asp_val[0] / asp_val[1]
            bw = proxy_w
            bh = int(bw / target_r)
            if bh > proxy_h:
                bh = proxy_h
                bw = int(bh * target_r)
        else:
            bw, bh = proxy_w - 20, proxy_h - 20
            
        st.session_state[k_box] = get_center_box_tuple(proxy_w, proxy_h, bw, bh)
        st.session_state[k_update] += 1

    def do_apply_manual():
        # Читаємо ввід
        uw = st.session_state.get(f"w_in_{file_id}", 100)
        uh = st.session_state.get(f"h_in_{file_id}", 100)
        
        # Переводимо в проксі
        pw = int(uw / scale_factor)
        ph = int(uh / scale_factor)
        
        # ВАЖЛИВО: Скидаємо аспект на Free, щоб не сплющило
        free_key = [k for k, v in config.ASPECT_RATIOS.items() if v is None][0]
        st.session_state[k_aspect] = free_key
        
        st.session_state[k_box] = get_center_box_tuple(proxy_w, proxy_h, pw, ph)
        st.session_state[k_update] += 1

    # 5. UI
    col_can, col_ui = st.columns([3, 1], gap="medium")

    with col_ui:
        st.markdown("##### 1. Інструменти")
        c1, c2 = st.columns(2)
        c1.button("↺ -90°", key=f"l{file_id}", on_click=do_rotate, args=(-90,), use_container_width=True)
        c2.button("↻ +90°", key=f"r{file_id}", on_click=do_rotate, args=(90,), use_container_width=True)
        
        st.selectbox("Пропорції", list(config.ASPECT_RATIOS.keys()), key=k_aspect, label_visibility="collapsed")
        
        b1, b2 = st.columns(2)
        b1.button("Reset", key=f"rst{file_id}", on_click=do_reset, use_container_width=True)
        b2.button("MAX", key=f"max{file_id}", on_click=do_max, use_container_width=True)
        
        st.divider()

    with col_can:
        # Унікальний ключ = повна перезагрузка віджета
        cropper_id = f"crp_{file_id}_{st.session_state[k_update]}_{st.session_state[k_aspect]}"
        
        # Отримуємо налаштування
        current_asp_name = st.session_state[k_aspect]
        current_asp_val = config.ASPECT_RATIOS.get(current_asp_name, None)
        forced_box = st.session_state[k_box]

        rect = st_cropper(
            img_proxy,
            realtime_update=True,
            box_color='#FF0000',
            aspect_ratio=current_asp_val,
            default_coords=forced_box,
            should_resize_image=False, 
            return_type='box',
            key=cropper_id
        )

    with col_ui:
        st.markdown("##### 2. Розмір (px)")
        
        # Обчислюємо реальний розмір з рамки
        real_w, real_h, crop_box = 0, 0, None
        
        if rect:
            l = int(rect['left'] * scale_factor)
            t = int(rect['top'] * scale_factor)
            w = int(rect['width'] * scale_factor)
            h = int(rect['height'] * scale_factor)
            
            # Clamp
            l = max(0, min(l, orig_w))
            t = max(0, min(t, orig_h))
            if l + w > orig_w: w = orig_w - l
            if t + h > orig_h: h = orig_h - t
            
            real_w, real_h = w, h
            crop_box = (l, t, l+w, t+h)

        cw, ch = st.columns(2)
        cw.number_input("W", value=orig_w, min_value=10, max_value=orig_w, key=f"w_in_{file_id}", label_visibility="collapsed")
        ch.number_input("H", value=orig_h, min_value=10, max_value=orig_h, key=f"h_in_{file_id}", label_visibility="collapsed")
        
        st.button("✓ Застосувати", key=f"apply{file_id}", on_click=do_apply_manual, use_container_width=True)

        if real_w > 0:
            st.success(f"**{real_w} x {real_h}** px")
        
        # Debug info (допоможе зрозуміти, якщо знову вилізе 483x17)
        with st.expander("Debug Info"):
            st.text(f"Orig: {orig_w}x{orig_h}")
            st.text(f"Proxy: {proxy_w}x{proxy_h}")
            st.text(f"Scale: {scale_factor:.3f}")
            if forced_box:
                st.text(f"Forced Box (Proxy): {forced_box}")
            if rect:
                st.text(f"Rect (Proxy): {rect}")

        st.divider()

        if st.button("💾 Зберегти", type="primary", use_container_width=True, key=f"sav{file_id}"):
            if crop_box:
                try:
                    res = img_orig.crop(crop_box)
                    res.save(fpath, quality=95, subsampling=0)
                    
                    # Cleanup
                    for k in [k_rot, k_update, k_box, k_aspect, f"w_in_{file_id}", f"h_in_{file_id}"]:
                        if k in st.session_state: del st.session_state[k]
                    thumb = f"{fpath}.thumb.jpg"
                    if os.path.exists(thumb): os.remove(thumb)
                    
                    st.session_state['close_editor'] = True
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")
            else:
                st.warning("No selection")
