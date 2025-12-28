import streamlit as st
import os
from PIL import Image, ImageOps
from streamlit_cropper import st_cropper
import config 
from logger import get_logger 
from validators import validate_image_file

logger = get_logger(__name__)

# --- MATH FUNCTIONS ---

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

def get_fitting_box(container_w, container_h, aspect_tuple):
    """
    Надійно розраховує максимальний прямокутник заданої пропорції, 
    який влізає в контейнер (картинку).
    """
    # 1. Відступи безпеки (щоб не глючив JS на краях)
    pad = 2 
    max_w = container_w - (pad * 2)
    max_h = container_h - (pad * 2)
    
    if not aspect_tuple:
        # Free mode: майже вся картинка
        return (pad, pad, max_w, max_h)
    
    # Цільова пропорція
    target_ratio = aspect_tuple[0] / aspect_tuple[1]
    # Пропорція контейнера
    container_ratio = max_w / max_h
    
    if container_ratio > target_ratio:
        # Контейнер ширший за ціль -> Обмежуємо по висоті
        box_h = max_h
        box_w = int(box_h * target_ratio)
    else:
        # Контейнер вищий за ціль -> Обмежуємо по ширині
        box_w = max_w
        box_h = int(box_w / target_ratio)
        
    # Центрування
    left = pad + (max_w - box_w) // 2
    top = pad + (max_h - box_h) // 2
    
    return (int(left), int(top), int(box_w), int(box_h))

def get_center_box_manual(proxy_w, proxy_h, target_w, target_h):
    """Центрує довільний розмір."""
    target_w = min(int(target_w), proxy_w)
    target_h = min(int(target_h), proxy_h)
    
    target_w = max(10, target_w)
    target_h = max(10, target_h)
    
    left = int((proxy_w - target_w) / 2)
    top = int((proxy_h - target_h) / 2)
    
    return (left, top, target_w, target_h)

# --- EDITOR DIALOG ---

@st.dialog("🛠 Editor", width="large")
def open_editor_dialog(fpath: str, T: dict):
    file_id = os.path.basename(fpath)
    
    # 1. KEYS
    k_rot = f"rot_{file_id}"
    k_box = f"box_{file_id}"    # Примусові координати (відправляємо в кропер)
    k_upd = f"upd_{file_id}"    # Лічильник версій віджета
    k_asp = f"asp_{file_id}"    # Пропорції
    
    # 2. INIT
    if k_rot not in st.session_state: st.session_state[k_rot] = 0
    if k_box not in st.session_state: st.session_state[k_box] = None
    if k_upd not in st.session_state: st.session_state[k_upd] = 0
    if k_asp not in st.session_state: st.session_state[k_asp] = "Free / Вільний"

    # 3. LOAD IMAGE
    try:
        validate_image_file(fpath)
        img_orig = Image.open(fpath)
        img_orig = ImageOps.exif_transpose(img_orig)
        img_orig = img_orig.convert('RGB')
        
        # Rotate logic
        if st.session_state[k_rot] != 0:
            img_orig = img_orig.rotate(-st.session_state[k_rot], expand=True)
            
        # Proxy logic
        img_proxy, scale_factor = create_proxy_image(img_orig)
        proxy_w, proxy_h = img_proxy.size
        orig_w, orig_h = img_orig.size
        
    except Exception as e:
        st.error(f"Error loading image: {e}")
        return

    st.caption(get_file_info_str(fpath, img_orig))

    # --- UI LAYOUT ---
    col_can, col_ui = st.columns([3, 1], gap="medium")

    # --- CONTROLS ---
    with col_ui:
        st.markdown("**1. Інструменти**")
        c1, c2 = st.columns(2)
        
        # Rotate
        if c1.button("↺ -90°", key=f"l{file_id}", use_container_width=True):
            st.session_state[k_rot] -= 90
            st.session_state[k_box] = None
            st.session_state[k_upd] += 1
            st.rerun()
            
        if c2.button("↻ +90°", key=f"r{file_id}", use_container_width=True):
            st.session_state[k_rot] += 90
            st.session_state[k_box] = None
            st.session_state[k_upd] += 1
            st.rerun()
        
        # Aspect Ratio
        def on_asp_change():
            # Коли міняємо аспект, скидаємо ручну рамку, щоб кропер сам підлаштувався
            st.session_state[k_box] = None 
            st.session_state[k_upd] += 1
            
        st.selectbox(
            "Пропорції", 
            list(config.ASPECT_RATIOS.keys()), 
            key=k_asp, 
            on_change=on_asp_change,
            label_visibility="collapsed"
        )
        
        # Buttons
        b1, b2 = st.columns(2)
        
        # RESET
        if b1.button("Скинути", key=f"rst{file_id}", use_container_width=True):
            st.session_state[k_rot] = 0
            st.session_state[k_box] = None
            st.session_state[k_asp] = "Free / Вільний"
            st.session_state[k_upd] += 1
            st.rerun()
            
        # MAX (FIXED LOGIC)
        if b2.button("MAX", key=f"max{file_id}", use_container_width=True):
            asp_key = st.session_state[k_asp]
            asp_tuple = config.ASPECT_RATIOS.get(asp_key, None)
            
            # Використовуємо надійну математику
            new_box = get_fitting_box(proxy_w, proxy_h, asp_tuple)
            
            st.session_state[k_box] = new_box
            st.session_state[k_upd] += 1
            st.rerun()
            
        st.divider()
        
        # MANUAL SIZE
        st.markdown("**2. Точний розмір**")
        with st.form(key=f"size_form_{file_id}", border=False):
            fc1, fc2 = st.columns(2)
            in_w = fc1.number_input("W", value=orig_w, min_value=10, max_value=orig_w, label_visibility="collapsed")
            in_h = fc2.number_input("H", value=orig_h, min_value=10, max_value=orig_h, label_visibility="collapsed")
            
            submit_size = st.form_submit_button("✓ Застосувати", use_container_width=True, type="primary")
        
        if submit_size:
            st.session_state[k_asp] = "Free / Вільний"
            target_pw = in_w / scale_factor
            target_ph = in_h / scale_factor
            
            st.session_state[k_box] = get_center_box_manual(proxy_w, proxy_h, target_pw, target_ph)
            st.session_state[k_upd] += 1
            st.rerun()

    # --- CANVAS ---
    with col_can:
        # Унікальний ID
        cropper_id = f"crp_{file_id}_{st.session_state[k_upd]}_{st.session_state[k_asp]}"
        
        aspect_val = config.ASPECT_RATIOS.get(st.session_state[k_asp], None)
        forced_box = st.session_state[k_box]

        rect = st_cropper(
            img_proxy,
            realtime_update=True,
            box_color='#FF0000',
            aspect_ratio=aspect_val,
            default_coords=forced_box, # Якщо тут None, st_cropper сам малює дефолт
            should_resize_image=False, 
            return_type='box',
            key=cropper_id
        )

    # --- INFO & SAVE ---
    with col_ui:
        real_w, real_h, crop_box = 0, 0, None
        
        if rect:
            # Математика координат
            l = int(rect['left'] * scale_factor)
            t = int(rect['top'] * scale_factor)
            w = int(rect['width'] * scale_factor)
            h = int(rect['height'] * scale_factor)
            
            # Захист меж (Clamping)
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
                    for k in [k_rot, k_box, k_upd, k_asp]:
                        if k in st.session_state: del st.session_state[k]
                    thumb = f"{fpath}.thumb.jpg"
                    if os.path.exists(thumb): os.remove(thumb)
                    
                    st.session_state['close_editor'] = True
                    st.toast("Збережено!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error: {e}")
        
        # --- DEBUG INFO (Розгорніть це, якщо знову будуть негативні числа) ---
        with st.expander("🛠 Технічні дані", expanded=False):
            st.code(f"""
Proxy Size: {proxy_w}x{proxy_h}
Scale: {scale_factor:.4f}
Aspect Setting: {st.session_state[k_asp]}
Forced Box Sent: {forced_box}
Rect Received: {rect}
            """)
