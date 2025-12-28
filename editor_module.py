import streamlit as st
import os
from PIL import Image, ImageOps
from streamlit_cropper import st_cropper
import config 
from logger import get_logger 
from validators import validate_image_file

logger = get_logger(__name__)

# --- МАТЕМАТИКА (ПЕРЕВІРЕНА) ---

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

def safe_box_calculation(container_w, container_h, target_w, target_h):
    """
    Гарантує, що рамка target влізе в container.
    Повертає tuple (left, top, width, height)
    """
    # 1. Захист від дурня (якщо target > container)
    target_w = min(target_w, container_w)
    target_h = min(target_h, container_h)
    
    # 2. Захист від смужок (мінімум 20px)
    target_w = max(20, target_w)
    target_h = max(20, target_h)
    
    # 3. Центрування
    left = (container_w - target_w) // 2
    top = (container_h - target_h) // 2
    
    # 4. Фінальний захист координат (щоб не було -5 px)
    left = max(0, left)
    top = max(0, top)
    
    return (int(left), int(top), int(target_w), int(target_h))

def get_max_fitting_box(container_w, container_h, aspect_tuple):
    """Рахує MAX рамку для заданої пропорції."""
    if not aspect_tuple:
        # Free mode: відступ 10px
        pad = 10
        return safe_box_calculation(container_w, container_h, container_w - 2*pad, container_h - 2*pad)
    
    target_r = aspect_tuple[0] / aspect_tuple[1]
    
    # Спробувати по ширині
    bw = container_w
    bh = int(bw / target_r)
    
    # Якщо висота вилізла, рахуємо по висоті
    if bh > container_h:
        bh = container_h
        bw = int(bh * target_r)
        
    return safe_box_calculation(container_w, container_h, bw, bh)

# --- ГОЛОВНА ЛОГІКА ---

@st.dialog("🛠 Editor", width="large")
def open_editor_dialog(fpath: str, T: dict):
    file_id = os.path.basename(fpath)
    
    # --- 1. STATE INIT ---
    if f'rot_{file_id}' not in st.session_state: st.session_state[f'rot_{file_id}'] = 0
    if f'ver_{file_id}' not in st.session_state: st.session_state[f'ver_{file_id}'] = 0 # Лічильник версій
    if f'box_{file_id}' not in st.session_state: st.session_state[f'box_{file_id}'] = None # Дефолтна рамка
    if f'asp_{file_id}' not in st.session_state: st.session_state[f'asp_{file_id}'] = "Free / Вільний"

    # --- 2. LOAD & PROXY ---
    try:
        validate_image_file(fpath)
        img_orig = Image.open(fpath)
        img_orig = ImageOps.exif_transpose(img_orig)
        img_orig = img_orig.convert('RGB')
        
        # Rotate
        rot = st.session_state[f'rot_{file_id}']
        if rot != 0:
            img_orig = img_orig.rotate(-rot, expand=True)
        
        # Proxy
        img_proxy, scale = create_proxy_image(img_orig)
        pw, ph = img_proxy.size
        ow, oh = img_orig.size
        
    except Exception as e:
        st.error(f"Error: {e}")
        return

    st.caption(get_file_info_str(fpath, img_orig))

    # --- 3. UI ---
    col_can, col_ui = st.columns([3, 1], gap="medium")

    with col_ui:
        st.write("🔧 **Інструменти**")
        
        # ROTATE
        c1, c2 = st.columns(2)
        if c1.button("↺ -90°", key=f"l{file_id}", use_container_width=True):
            st.session_state[f'rot_{file_id}'] -= 90
            st.session_state[f'box_{file_id}'] = None
            st.session_state[f'ver_{file_id}'] += 1
            st.rerun()
        if c2.button("↻ +90°", key=f"r{file_id}", use_container_width=True):
            st.session_state[f'rot_{file_id}'] += 90
            st.session_state[f'box_{file_id}'] = None
            st.session_state[f'ver_{file_id}'] += 1
            st.rerun()
            
        # ASPECT
        def on_change_aspect():
            # При зміні аспекту просто оновлюємо версію, щоб кропер перемалювався
            st.session_state[f'box_{file_id}'] = None # Скидаємо рамку на дефолтну для цього аспекту
            st.session_state[f'ver_{file_id}'] += 1
            
        st.selectbox(
            "Пропорції", list(config.ASPECT_RATIOS.keys()), 
            key=f'asp_{file_id}', on_change=on_change_aspect, label_visibility="collapsed"
        )
        
        # RESET & MAX
        b1, b2 = st.columns(2)
        if b1.button("Скинути", key=f"rst{file_id}", use_container_width=True):
            st.session_state[f'rot_{file_id}'] = 0
            st.session_state[f'box_{file_id}'] = None
            st.session_state[f'asp_{file_id}'] = "Free / Вільний"
            st.session_state[f'ver_{file_id}'] += 1
            st.rerun()
            
        if b2.button("MAX", key=f"max{file_id}", use_container_width=True):
            # 1. Беремо поточний аспект
            asp_key = st.session_state[f'asp_{file_id}']
            asp_val = config.ASPECT_RATIOS.get(asp_key, None)
            
            # 2. Рахуємо коробку для ПРОКСІ картинки (бо кропер працює з проксі)
            new_box = get_max_fitting_box(pw, ph, asp_val)
            
            # 3. Зберігаємо
            st.session_state[f'box_{file_id}'] = new_box
            st.session_state[f'ver_{file_id}'] += 1
            st.rerun()

        st.divider()
        
        # MANUAL SIZE
        st.write("✏️ **Введіть розмір**")
        with st.form(key=f"sz_{file_id}", border=False):
            fc1, fc2 = st.columns(2)
            in_w = fc1.number_input("W", value=ow, min_value=10, max_value=ow, label_visibility="collapsed")
            in_h = fc2.number_input("H", value=oh, min_value=10, max_value=oh, label_visibility="collapsed")
            
            if st.form_submit_button("✓ Застосувати", use_container_width=True, type="primary"):
                # 1. Скидаємо аспект
                st.session_state[f'asp_{file_id}'] = "Free / Вільний"
                
                # 2. Переводимо вхідні (Original) в Proxy
                t_pw = int(in_w / scale)
                t_ph = int(in_h / scale)
                
                # 3. Рахуємо безпечну коробку
                new_box = safe_box_calculation(pw, ph, t_pw, t_ph)
                
                st.session_state[f'box_{file_id}'] = new_box
                st.session_state[f'ver_{file_id}'] += 1
                st.rerun()

    with col_can:
        # КЛЮЧОВИЙ МОМЕНТ:
        # Ми передаємо всі змінні в key. Це змушує Streamlit створювати НОВИЙ компонент
        # щоразу, коли щось змінюється. Це лікує всі глюки з оновленням.
        cropper_key = f"crp_{file_id}_v{st.session_state[f'ver_{file_id}']}_{st.session_state[f'asp_{file_id}']}"
        
        # Отримуємо дані для кропера
        asp_val = config.ASPECT_RATIOS.get(st.session_state[f'asp_{file_id}'], None)
        def_box = st.session_state[f'box_{file_id}']

        rect = st_cropper(
            img_proxy,
            realtime_update=True,
            box_color='#FF0000',
            aspect_ratio=asp_val,
            default_coords=def_box, # Якщо None -> бібліотека малює сама. Якщо Tuple -> малює наш box
            should_resize_image=False,
            return_type='box',
            key=cropper_key
        )

    # --- SAVE LOGIC ---
    with col_ui:
        if rect:
            # Масштабуємо назад: Proxy -> Original
            l = int(rect['left'] * scale)
            t = int(rect['top'] * scale)
            w = int(rect['width'] * scale)
            h = int(rect['height'] * scale)
            
            # Clamp (Останній рубіж захисту)
            l = max(0, min(l, ow))
            t = max(0, min(t, oh))
            if l + w > ow: w = ow - l
            if t + h > oh: h = oh - t
            
            st.divider()
            st.success(f"**{w} x {h}** px")
            
            if st.button("💾 ЗБЕРЕГТИ", key=f"sv_{file_id}", use_container_width=True):
                try:
                    crop_box = (l, t, l+w, t+h)
                    final = img_orig.crop(crop_box)
                    final.save(fpath, quality=95, subsampling=0)
                    
                    # Clean
                    for k in [f'rot_{file_id}', f'ver_{file_id}', f'box_{file_id}', f'asp_{file_id}']:
                        if k in st.session_state: del st.session_state[k]
                    thumb = f"{fpath}.thumb.jpg"
                    if os.path.exists(thumb): os.remove(thumb)
                    
                    st.session_state['close_editor'] = True
                    st.toast("Готово!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")
