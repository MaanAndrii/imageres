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
    """Центрує рамку, гарантуючи межі."""
    # Не даємо рамці бути більшою за саме зображення
    target_w = min(target_w, proxy_w)
    target_h = min(target_h, proxy_h)
    
    # Не даємо рамці бути меншою за 10px (щоб не зникла)
    target_w = max(10, target_w)
    target_h = max(10, target_h)
    
    left = int((proxy_w - target_w) / 2)
    top = int((proxy_h - target_h) / 2)
    
    return (left, top, int(target_w), int(target_h))

# --- MAIN ---

@st.dialog("🛠 Editor", width="large")
def open_editor_dialog(fpath: str, T: dict):
    file_id = os.path.basename(fpath)
    
    # 1. INIT STATE
    k_rot = f"rot_{file_id}"
    k_box = f"box_{file_id}"      # Примусова рамка (tuple)
    k_upd = f"upd_{file_id}"      # Лічильник оновлень
    k_asp = f"asp_{file_id}"      # Ключ пропорцій

    if k_rot not in st.session_state: st.session_state[k_rot] = 0
    if k_box not in st.session_state: st.session_state[k_box] = None
    if k_upd not in st.session_state: st.session_state[k_upd] = 0
    if k_asp not in st.session_state: st.session_state[k_asp] = "Free / Вільний"

    # 2. LOAD IMAGE
    try:
        validate_image_file(fpath)
        img_orig = Image.open(fpath)
        img_orig = ImageOps.exif_transpose(img_orig)
        img_orig = img_orig.convert('RGB')
        
        # Rotate
        if st.session_state[k_rot] != 0:
            img_orig = img_orig.rotate(-st.session_state[k_rot], expand=True)
            
        # Proxy
        img_proxy, scale_factor = create_proxy_image(img_orig)
        proxy_w, proxy_h = img_proxy.size
        orig_w, orig_h = img_orig.size
        
    except Exception as e:
        st.error(f"Error: {e}")
        return

    st.caption(get_file_info_str(fpath, img_orig))

    # --- 3. LOGIC HANDLERS (CALLBACKS) ---
    # Прості дії залишаємо на callbacks
    
    def on_rotate(delta):
        st.session_state[k_rot] += delta
        st.session_state[k_box] = None
        st.session_state[k_upd] += 1

    def on_reset():
        st.session_state[k_rot] = 0
        st.session_state[k_box] = None
        st.session_state[k_asp] = "Free / Вільний"
        st.session_state[k_upd] += 1

    def on_max():
        # Беремо поточний аспект
        asp_key = st.session_state[k_asp]
        asp_tuple = config.ASPECT_RATIOS.get(asp_key, None)
        
        if asp_tuple:
            # Aspect Mode
            r = asp_tuple[0] / asp_tuple[1]
            bw = proxy_w
            bh = int(bw / r)
            if bh > proxy_h:
                bh = proxy_h
                bw = int(bh * r)
        else:
            # Free Mode (Max Area)
            bw, bh = proxy_w - 20, proxy_h - 20
            
        st.session_state[k_box] = get_center_box_tuple(proxy_w, proxy_h, bw, bh)
        st.session_state[k_upd] += 1

    # --- 4. LAYOUT ---
    col_can, col_ui = st.columns([3, 1], gap="medium")

    # === UI PANEL ===
    with col_ui:
        st.markdown("**1. Інструменти**")
        c1, c2 = st.columns(2)
        c1.button("↺ -90°", key=f"l{file_id}", on_click=on_rotate, args=(-90,), use_container_width=True)
        c2.button("↻ +90°", key=f"r{file_id}", on_click=on_rotate, args=(90,), use_container_width=True)
        
        st.selectbox("Пропорції", list(config.ASPECT_RATIOS.keys()), key=k_asp, label_visibility="collapsed")
        
        b1, b2 = st.columns(2)
        b1.button("Скинути", key=f"rst{file_id}", on_click=on_reset, use_container_width=True)
        b2.button("MAX", key=f"max{file_id}", on_click=on_max, use_container_width=True)
        
        st.divider()
        
        # === FORM FOR MANUAL SIZE (CRITICAL FIX) ===
        st.markdown("**2. Точний розмір**")
        
        # Форма гарантує, що дані відправляться пакетом
        with st.form(key=f"size_form_{file_id}", border=False):
            fc1, fc2 = st.columns(2)
            # Встановлюємо value як default, але не прив'язуємо key до session_state напряму, щоб уникнути конфліктів
            # Користувач вводить нові дані -> тисне кнопку -> ми їх читаємо
            in_w = fc1.number_input("W", value=orig_w, min_value=10, max_value=orig_w, label_visibility="collapsed")
            in_h = fc2.number_input("H", value=orig_h, min_value=10, max_value=orig_h, label_visibility="collapsed")
            
            submit_size = st.form_submit_button("✓ Застосувати", use_container_width=True, type="primary")
            
            if submit_size:
                # Цей код виконається при натисканні, маючи актуальні in_w та in_h
                
                # 1. Примусово Free Mode
                st.session_state[k_asp] = "Free / Вільний"
                
                # 2. Розрахунок Proxy
                pw = int(in_w / scale_factor)
                ph = int(in_h / scale_factor)
                
                # 3. Оновлення рамки
                st.session_state[k_box] = get_center_box_tuple(proxy_w, proxy_h, pw, ph)
                st.session_state[k_upd] += 1
                st.rerun()

    # === CANVAS PANEL ===
    with col_can:
        # Унікальний ключ = Hard Reset віджета
        cropper_id = f"crp_{file_id}_{st.session_state[k_upd]}_{st.session_state[k_asp]}"
        
        aspect_val = config.ASPECT_RATIOS.get(st.session_state[k_asp], None)
        forced_box = st.session_state[k_box]

        rect = st_cropper(
            img_proxy,
            realtime_update=True,
            box_color='#FF0000',
            aspect_ratio=aspect_val,
            default_coords=forced_box,
            should_resize_image=False, 
            return_type='box',
            key=cropper_id
        )

    # === SAVE PANEL ===
    with col_ui:
        # Info & Save Logic
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
            
        if real_w > 0:
            st.divider()
            st.success(f"Обрано: **{real_w} x {real_h}** px")
            
            if st.button("💾 ЗБЕРЕГТИ", key=f"sv_{file_id}", use_container_width=True):
                try:
                    final = img_orig.crop(crop_box)
                    final.save(fpath, quality=95, subsampling=0)
                    
                    # Clean
                    for k in [k_rot, k_box, k_upd, k_asp]:
                        if k in st.session_state: del st.session_state[k]
                    thumb = f"{fpath}.thumb.jpg"
                    if os.path.exists(thumb): os.remove(thumb)
                    
                    st.session_state['close_editor'] = True
                    st.toast("Готово!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")
