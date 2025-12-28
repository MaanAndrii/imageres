import streamlit as st
import os
import uuid
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

def calculate_centered_box(proxy_w, proxy_h, target_w, target_h):
    """Центрує рамку в межах proxy зображення."""
    # 1. Захист: рамка не може бути більшою за картинку
    target_w = min(int(target_w), proxy_w)
    target_h = min(int(target_h), proxy_h)
    
    # 2. Захист: рамка не може бути меншою за 10px
    target_w = max(10, target_w)
    target_h = max(10, target_h)
    
    # 3. Центруємо
    left = int((proxy_w - target_w) / 2)
    top = int((proxy_h - target_h) / 2)
    
    return (left, top, int(target_w), int(target_h))

# --- ОСНОВНА ФУНКЦІЯ ---

@st.dialog("🛠 Editor", width="large")
def open_editor_dialog(fpath: str, T: dict):
    file_id = os.path.basename(fpath)
    
    # === 1. STATE MANAGEMENT ===
    # Використовуємо префікс, щоб не плутати файли
    p = f"ed_{file_id}_" 
    
    if f'{p}rot' not in st.session_state: st.session_state[f'{p}rot'] = 0
    if f'{p}key_uid' not in st.session_state: st.session_state[f'{p}key_uid'] = str(uuid.uuid4()) # Унікальний ID віджета
    if f'{p}box' not in st.session_state: st.session_state[f'{p}box'] = None
    if f'{p}aspect' not in st.session_state: st.session_state[f'{p}aspect'] = "Free / Вільний"

    # === 2. LOAD IMAGE ===
    try:
        validate_image_file(fpath)
        img_orig = Image.open(fpath)
        img_orig = ImageOps.exif_transpose(img_orig)
        img_orig = img_orig.convert('RGB')
        
        # Поворот
        rot = st.session_state[f'{p}rot']
        if rot != 0:
            img_orig = img_orig.rotate(-rot, expand=True)
            
        # Створення Proxy
        img_proxy, scale = create_proxy_image(img_orig)
        pw, ph = img_proxy.size
        ow, oh = img_orig.size
        
    except Exception as e:
        st.error(f"Error: {e}")
        return

    st.caption(get_file_info_str(fpath, img_orig))

    # === 3. LAYOUT ===
    col_can, col_ui = st.columns([3, 1], gap="medium")

    # --- ПАНЕЛЬ ІНСТРУМЕНТІВ (ПРАВА) ---
    with col_ui:
        st.write("🔧 **Інструменти**")
        
        # A. Rotate
        c1, c2 = st.columns(2)
        if c1.button("↺ -90°", key=f"{p}bl", use_container_width=True):
            st.session_state[f'{p}rot'] -= 90
            st.session_state[f'{p}box'] = None
            st.session_state[f'{p}key_uid'] = str(uuid.uuid4()) # Hard Reset
            st.rerun()
            
        if c2.button("↻ +90°", key=f"{p}br", use_container_width=True):
            st.session_state[f'{p}rot'] += 90
            st.session_state[f'{p}box'] = None
            st.session_state[f'{p}key_uid'] = str(uuid.uuid4()) # Hard Reset
            st.rerun()

        # B. Aspect Ratio
        def on_asp_change():
            # При зміні пропорцій просто скидаємо віджет
            st.session_state[f'{p}box'] = None
            st.session_state[f'{p}key_uid'] = str(uuid.uuid4())

        st.selectbox(
            "Пропорції", list(config.ASPECT_RATIOS.keys()), 
            key=f'{p}aspect', on_change=on_asp_change, label_visibility="collapsed"
        )
        
        # C. Reset / MAX
        b1, b2 = st.columns(2)
        if b1.button("Скинути", key=f"{p}rst", use_container_width=True):
            st.session_state[f'{p}rot'] = 0
            st.session_state[f'{p}box'] = None
            st.session_state[f'{p}aspect'] = "Free / Вільний"
            st.session_state[f'{p}key_uid'] = str(uuid.uuid4())
            st.rerun()

        if b2.button("MAX", key=f"{p}max", use_container_width=True):
            # Рахуємо MAX для поточного аспекту
            asp_key = st.session_state[f'{p}aspect']
            asp_val = config.ASPECT_RATIOS.get(asp_key, None)
            
            # Логіка MAX
            if asp_val:
                r = asp_val[0] / asp_val[1]
                bw = pw
                bh = int(bw / r)
                if bh > ph:
                    bh = ph
                    bw = int(bh * r)
            else:
                bw, bh = pw - 20, ph - 20 # Free mode max
            
            st.session_state[f'{p}box'] = calculate_centered_box(pw, ph, bw, bh)
            st.session_state[f'{p}key_uid'] = str(uuid.uuid4()) # Hard Reset
            st.rerun()
            
        st.divider()

        # D. Manual Size (Form)
        st.write("✏️ **Точний розмір**")
        with st.form(key=f"{p}form", border=False):
            fc1, fc2 = st.columns(2)
            # ВАЖЛИВО: value беремо з оригіналу, але це просто стартове значення
            in_w = fc1.number_input("W", value=ow, min_value=10, max_value=ow, label_visibility="collapsed")
            in_h = fc2.number_input("H", value=oh, min_value=10, max_value=oh, label_visibility="collapsed")
            
            if st.form_submit_button("✓ Застосувати", use_container_width=True, type="primary"):
                # 1. Скидаємо пропорції на Free, інакше кропер проігнорує висоту
                st.session_state[f'{p}aspect'] = "Free / Вільний"
                
                # 2. Конвертуємо введені пікселі (Orig) -> в екранні (Proxy)
                target_pw = int(in_w / scale)
                target_ph = int(in_h / scale)
                
                # 3. Рахуємо коробку
                new_box = calculate_centered_box(pw, ph, target_pw, target_ph)
                
                # 4. Зберігаємо і ОНОВЛЮЄМО ID ВІДЖЕТА
                st.session_state[f'{p}box'] = new_box
                st.session_state[f'{p}key_uid'] = str(uuid.uuid4()) # <-- Ось це лікує баг 17px
                st.rerun()

    # --- CANVAS (ЛІВА) ---
    with col_can:
        # ГЕНЕРУЄМО КЛЮЧ
        # Кожен раз, коли змінюється key_uid, створюється НОВИЙ кропер.
        # Новий кропер бере default_coords і ігнорує старий стан миші.
        cropper_id = f"crp_{st.session_state[f'{p}key_uid']}"
        
        asp_val = config.ASPECT_RATIOS.get(st.session_state[f'{p}aspect'], None)
        def_coords = st.session_state[f'{p}box']

        rect = st_cropper(
            img_proxy,
            realtime_update=True,
            box_color='#FF0000',
            aspect_ratio=asp_val,
            default_coords=def_coords, 
            should_resize_image=False, 
            return_type='box',
            key=cropper_id
        )

    # --- ЗБЕРЕЖЕННЯ ---
    with col_ui:
        if rect:
            # Конвертація Proxy -> Original
            l = int(rect['left'] * scale)
            t = int(rect['top'] * scale)
            w = int(rect['width'] * scale)
            h = int(rect['height'] * scale)
            
            # Clamp
            l = max(0, min(l, ow))
            t = max(0, min(t, oh))
            if l + w > ow: w = ow - l
            if t + h > oh: h = oh - t
            
            st.divider()
            st.success(f"Обрано: **{w} x {h}** px")
            
            if st.button("💾 ЗБЕРЕГТИ", key=f"{p}save", use_container_width=True):
                try:
                    crop_box = (l, t, l+w, t+h)
                    final = img_orig.crop(crop_box)
                    final.save(fpath, quality=95, subsampling=0)
                    
                    # Очистка пам'яті сесії
                    keys_to_del = [k for k in st.session_state.keys() if k.startswith(p)]
                    for k in keys_to_del:
                        del st.session_state[k]
                    
                    # Видалення тумби
                    thumb = f"{fpath}.thumb.jpg"
                    if os.path.exists(thumb): os.remove(thumb)
                    
                    st.session_state['close_editor'] = True
                    st.toast("Збережено!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")
