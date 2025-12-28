import streamlit as st
import os
from PIL import Image, ImageOps
from streamlit_cropper import st_cropper
import config 
from logger import get_logger 
from validators import validate_image_file

logger = get_logger(__name__)

# --- ДОПОМІЖНІ ФУНКЦІЇ ---

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
    """Центрує рамку, гарантуючи межі (мінімум 10px)."""
    # Захист від дурня: якщо target більший за proxy
    target_w = min(target_w, proxy_w)
    target_h = min(target_h, proxy_h)
    
    # Захист від смужок: мінімум 10 пікселів
    target_w = max(10, target_w)
    target_h = max(10, target_h)
    
    left = int((proxy_w - target_w) / 2)
    top = int((proxy_h - target_h) / 2)
    
    return (left, top, int(target_w), int(target_h))

# --- ОСНОВНА ФУНКЦІЯ ---

@st.dialog("🛠 Editor", width="large")
def open_editor_dialog(fpath: str, T: dict):
    file_id = os.path.basename(fpath)
    
    # === 1. ВИЗНАЧЕННЯ КЛЮЧІВ (KEYS) ===
    # Визначаємо ключі заздалегідь, щоб використовувати їх і в UI, і в Callbacks
    k_rot = f"rot_{file_id}"
    k_box = f"box_{file_id}"      # Примусова рамка (tuple)
    k_upd = f"upd_{file_id}"      # Лічильник оновлень (Hard Reset)
    k_asp = f"asp_{file_id}"      # Селектор пропорцій
    k_in_w = f"in_w_{file_id}"    # Інпут ширини
    k_in_h = f"in_h_{file_id}"    # Інпут висоти

    # === 2. ІНІЦІАЛІЗАЦІЯ СТАНУ ===
    if k_rot not in st.session_state: st.session_state[k_rot] = 0
    if k_box not in st.session_state: st.session_state[k_box] = None
    if k_upd not in st.session_state: st.session_state[k_upd] = 0
    if k_asp not in st.session_state: st.session_state[k_asp] = "Free / Вільний"

    # === 3. ЗАВАНТАЖЕННЯ ===
    try:
        validate_image_file(fpath)
        img_orig = Image.open(fpath)
        img_orig = ImageOps.exif_transpose(img_orig)
        img_orig = img_orig.convert('RGB')
        
        # Поворот
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

    # === 4. ЛОГІКА (CALLBACKS) ===
    # Ці функції виконуються ДО того, як Streamlit почне малювати віджети.
    # Це вирішує проблему StreamlitAPIException.

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
        asp_key = st.session_state[k_asp]
        asp_tuple = config.ASPECT_RATIOS.get(asp_key, None)
        
        if asp_tuple:
            r = asp_tuple[0] / asp_tuple[1]
            bw = proxy_w
            bh = int(bw / r)
            if bh > proxy_h:
                bh = proxy_h
                bw = int(bh * r)
        else:
            bw, bh = proxy_w - 20, proxy_h - 20
            
        st.session_state[k_box] = get_center_box_tuple(proxy_w, proxy_h, bw, bh)
        st.session_state[k_upd] += 1

    def on_apply_manual_size():
        """
        Викликається при натисканні 'Застосувати' у формі.
        В цей момент значення в k_in_w та k_in_h ВЖЕ оновлені формою.
        """
        # 1. Читаємо введені дані
        val_w = st.session_state[k_in_w]
        val_h = st.session_state[k_in_h]
        
        # 2. Примусово перемикаємо на Free Mode (тут це безпечно, бо віджет ще не намальовано)
        free_key = [k for k, v in config.ASPECT_RATIOS.items() if v is None][0]
        st.session_state[k_asp] = free_key
        
        # 3. Переводимо в Proxy координати
        pw = int(val_w / scale_factor)
        ph = int(val_h / scale_factor)
        
        # 4. Встановлюємо нову рамку
        st.session_state[k_box] = get_center_box_tuple(proxy_w, proxy_h, pw, ph)
        st.session_state[k_upd] += 1

    # === 5. ІНТЕРФЕЙС ===
    col_can, col_ui = st.columns([3, 1], gap="medium")

    # --- ПАНЕЛЬ ІНСТРУМЕНТІВ ---
    with col_ui:
        st.markdown("**1. Інструменти**")
        c1, c2 = st.columns(2)
        c1.button("↺ -90°", key=f"l{file_id}", on_click=on_rotate, args=(-90,), use_container_width=True)
        c2.button("↻ +90°", key=f"r{file_id}", on_click=on_rotate, args=(90,), use_container_width=True)
        
        # Селектор використовує key=k_asp, який ми безпечно змінюємо в callbacks
        st.selectbox("Пропорції", list(config.ASPECT_RATIOS.keys()), key=k_asp, label_visibility="collapsed")
        
        b1, b2 = st.columns(2)
        b1.button("Скинути", key=f"rst{file_id}", on_click=on_reset, use_container_width=True)
        b2.button("MAX", key=f"max{file_id}", on_click=on_max, use_container_width=True)
        
        st.divider()
        
        # === ФОРМА ДЛЯ ВВЕДЕННЯ РОЗМІРУ ===
        # st.form гарантує цілісність даних
        st.markdown("**2. Точний розмір**")
        
        with st.form(key=f"size_form_{file_id}", border=False):
            fc1, fc2 = st.columns(2)
            # Встановлюємо ключі, щоб callback міг їх прочитати
            fc1.number_input("W", value=orig_w, min_value=10, max_value=orig_w, key=k_in_w, label_visibility="collapsed")
            fc2.number_input("H", value=orig_h, min_value=10, max_value=orig_h, key=k_in_h, label_visibility="collapsed")
            
            # ВАЖЛИВО: on_click викликає функцію ДО перезавантаження скрипта
            st.form_submit_button("✓ Застосувати", on_click=on_apply_manual_size, use_container_width=True, type="primary")

    # --- ПОЛОТНО (CANVAS) ---
    with col_can:
        # Унікальний ключ гарантує повне перестворення віджета при змінах
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

    # --- ПАНЕЛЬ ЗБЕРЕЖЕННЯ ---
    with col_ui:
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
                    
                    # Cleanup
                    for k in [k_rot, k_box, k_upd, k_asp, k_in_w, k_in_h]:
                        if k in st.session_state: del st.session_state[k]
                    
                    thumb = f"{fpath}.thumb.jpg"
                    if os.path.exists(thumb): os.remove(thumb)
                    
                    st.session_state['close_editor'] = True
                    st.toast("Готово!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")
