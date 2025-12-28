import streamlit as st
import os
from PIL import Image, ImageOps
from streamlit_cropper import st_cropper
import config 
from logger import get_logger 
from validators import validate_image_file

logger = get_logger(__name__)

def get_file_info_str(fpath: str, img: Image.Image) -> str:
    try:
        size_bytes = os.path.getsize(fpath)
        size_mb = size_bytes / (1024 * 1024)
        size_str = f"{size_mb:.2f} MB" if size_mb >= 1 else f"{size_bytes/1024:.1f} KB"
        return f"📄 **{os.path.basename(fpath)}** &nbsp;•&nbsp; 📏 **{img.width}x{img.height}** &nbsp;•&nbsp; 💾 **{size_str}**"
    except Exception:
        return "📄 Інформація недоступна"

def create_proxy_image(img: Image.Image, target_width: int = 700):
    w, h = img.size
    if w <= target_width:
        return img, 1.0
    ratio = target_width / w
    new_h = max(1, int(h * ratio))
    proxy = img.resize((target_width, new_h), Image.Resampling.LANCZOS)
    return proxy, w / target_width

def calculate_max_crop_box(proxy_w: int, proxy_h: int, aspect_ratio: tuple) -> tuple:
    """Розрахунок максимальної рамки. Повертає tuple (left, top, width, height)."""
    pad = 10
    
    # Якщо пропорції не задані (Free mode)
    if not aspect_ratio:
        safe_w = max(10, proxy_w - 2*pad)
        safe_h = max(10, proxy_h - 2*pad)
        return (pad, pad, safe_w, safe_h)
    
    # Якщо пропорції задані (наприклад, 16:9)
    # aspect_ratio[0] - це ширина пропорції (16)
    # aspect_ratio[1] - це висота пропорції (9)
    target_ratio = float(aspect_ratio[0]) / float(aspect_ratio[1])
    
    # 1. Пробуємо вписати рамку по ширині проксі-картинки
    box_w = proxy_w
    box_h = int(box_w / target_ratio)
    
    # 2. Якщо висота рамки вийшла більшою за висоту картинки, 
    #    значить вписувати треба по висоті
    if box_h > proxy_h:
        box_h = proxy_h
        box_w = int(box_h * target_ratio)
        
    # Центруємо рамку
    left = int((proxy_w - box_w) / 2)
    top = int((proxy_h - box_h) / 2)
    
    # Повертаємо цілі числа, гарантуємо що > 0
    return (
        max(0, left),
        max(0, top),
        max(10, int(box_w)),
        max(10, int(box_h))
    )

@st.dialog("🛠 Editor", width="large")
def open_editor_dialog(fpath: str, T: dict):
    file_id = os.path.basename(fpath)
    
    # --- SESSION KEYS ---
    # Ключі для віджетів
    key_rot = f'rot_{file_id}'
    key_reset = f'reset_{file_id}'
    key_def_box = f'default_box_{file_id}'
    key_aspect = f"asp_{file_id}"
    key_input_w = f"in_w_{file_id}"
    key_input_h = f"in_h_{file_id}"

    # --- STATE INIT ---
    if key_rot not in st.session_state: st.session_state[key_rot] = 0
    if key_reset not in st.session_state: st.session_state[key_reset] = 0
    if key_def_box not in st.session_state: st.session_state[key_def_box] = None

    # --- LOAD IMAGE ---
    try:
        validate_image_file(fpath)
        img_original = Image.open(fpath)
        img_original = ImageOps.exif_transpose(img_original)
        img_original = img_original.convert('RGB')
        
        angle = st.session_state[key_rot]
        if angle != 0:
            img_original = img_original.rotate(-angle, expand=True)
            
        img_proxy, scale_factor = create_proxy_image(img_original)
        proxy_w, proxy_h = img_proxy.size
        orig_w, orig_h = img_original.size
    except Exception as e:
        st.error(f"Помилка: {e}")
        return

    st.caption(get_file_info_str(fpath, img_original))

    # --- CALLBACKS ---
    # Ці функції виконаються ДО перемальовки екрану, тому помилки не буде
    
    def apply_size_action():
        """Дія для кнопки 'Застосувати розмір'"""
        # 1. Примусово ставимо 'Free' режим
        st.session_state[key_aspect] = "Free / Вільний"
        
        # 2. Читаємо значення з полів вводу
        inp_w = st.session_state[key_input_w]
        inp_h = st.session_state[key_input_h]
        
        # 3. Переводимо в Proxy координати
        target_w_p = int(inp_w / scale_factor)
        target_h_p = int(inp_h / scale_factor)
        
        # 4. Центруємо
        nl = int((proxy_w - target_w_p) / 2)
        nt = int((proxy_h - target_h_p) / 2)
        
        st.session_state[key_def_box] = (max(0, nl), max(0, nt), target_w_p, target_h_p)
        st.session_state[key_reset] += 1

    def max_action():
        """Дія для кнопки 'MAX'"""
        # 1. Дістаємо поточний обраний аспект
        current_choice = st.session_state[key_aspect]
        current_ratio = config.ASPECT_RATIOS.get(current_choice, None)
        
        # 2. Рахуємо макс рамку для ЦЬОГО аспекту
        m_box = calculate_max_crop_box(proxy_w, proxy_h, current_ratio)
        
        st.session_state[key_def_box] = m_box
        st.session_state[key_reset] += 1

    def reset_action():
        st.session_state[key_rot] = 0
        st.session_state[key_def_box] = None
        st.session_state[key_reset] += 1
    
    def rotate_action(delta):
        st.session_state[key_rot] += delta
        st.session_state[key_reset] += 1
        st.session_state[key_def_box] = None

    # --- LAYOUT ---
    col_canvas, col_controls = st.columns([3, 1], gap="medium")

    # --- CONTROLS ---
    with col_controls:
        # 1. Rotate
        st.markdown("**Обертання**")
        c1, c2 = st.columns(2)
        with c1:
            st.button("↺ -90°", key=f"btn_l_{file_id}", use_container_width=True, 
                      on_click=rotate_action, args=(-90,))
        with c2:
            st.button("↻ +90°", key=f"btn_r_{file_id}", use_container_width=True, 
                      on_click=rotate_action, args=(90,))
        
        # 2. Aspect Ratio
        st.markdown("**Пропорції**")
        # Важливо: selectbox керує станом через key_aspect
        aspect_choice = st.selectbox(
            "Співвідношення", 
            list(config.ASPECT_RATIOS.keys()), 
            label_visibility="collapsed",
            key=key_aspect
        )
        # Отримуємо значення для кропера (але для MAX використовуємо значення всередині callback)
        aspect_val = config.ASPECT_RATIOS[aspect_choice]
        
        # 3. Reset & MAX
        br1, br2 = st.columns(2)
        with br1:
             st.button("Скинути", key=f"btn_rst_{file_id}", use_container_width=True, 
                       on_click=reset_action)
        with br2:
            # Використовуємо callback для MAX
            st.button("MAX ⛶", key=f"btn_max_{file_id}", use_container_width=True, 
                      on_click=max_action)

        st.divider()

    # --- CANVAS ---
    with col_canvas:
        # Динамічний ключ для перемальовки
        cropper_uid = f"crp_{file_id}_{st.session_state[key_reset]}_{aspect_choice}"
        default_coords = st.session_state[key_def_box]

        rect = st_cropper(
            img_proxy,
            realtime_update=True,
            box_color='#FF0000',
            aspect_ratio=aspect_val,
            default_coords=default_coords,
            should_resize_image=False, 
            return_type='box',
            key=cropper_uid
        )

    # --- CALC & SAVE ---
    with col_controls:
        # Розрахунок реальних координат
        real_w, real_h = 0, 0
        crop_box = None
        
        if rect:
            left = int(rect['left'] * scale_factor)
            top = int(rect['top'] * scale_factor)
            width = int(rect['width'] * scale_factor)
            height = int(rect['height'] * scale_factor)
            
            left = max(0, min(left, orig_w))
            top = max(0, min(top, orig_h))
            if left + width > orig_w: width = orig_w - left
            if top + height > orig_h: height = orig_h - top
            
            real_w, real_h = width, height
            crop_box = (left, top, left + width, top + height)

        # --- MANUAL SIZE ---
        st.markdown("**Точний розмір (px)**")
        
        # Підготовка значень для input
        val_w = real_w if real_w > 0 else orig_w
        val_h = real_h if real_h > 0 else orig_h
        
        # Обмеження (щоб не було помилок value < min)
        safe_min = 10
        val_w = max(safe_min, min(val_w, orig_w))
        val_h = max(safe_min, min(val_h, orig_h))
        
        c_w, c_h = st.columns(2)
        c_w.number_input("W", value=int(val_w), min_value=safe_min, max_value=orig_w, 
                         label_visibility="collapsed", key=key_input_w)
        c_h.number_input("H", value=int(val_h), min_value=safe_min, max_value=orig_h, 
                         label_visibility="collapsed", key=key_input_h)
        
        # Кнопка з Callback
        st.button("✓ Застосувати розмір", key=f"btn_apply_{file_id}", use_container_width=True,
                  on_click=apply_size_action)

        if real_w > 0:
            st.success(f"Вибрано: **{real_w} x {real_h}** px")
        
        st.divider()

        if st.button(T.get('btn_save_edit', '💾 Зберегти'), type="primary", use_container_width=True, key=f"btn_save_{file_id}"):
            if crop_box:
                try:
                    final_img = img_original.crop(crop_box)
                    final_img.save(fpath, quality=95, subsampling=0)
                    
                    if os.path.exists(f"{fpath}.thumb.jpg"): os.remove(f"{fpath}.thumb.jpg")
                    
                    # Cleanup
                    for k in [key_rot, key_reset, key_def_box, key_aspect, key_input_w, key_input_h]:
                        if k in st.session_state: del st.session_state[k]
                    
                    st.session_state['close_editor'] = True
                    st.toast("Зміни збережено!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Помилка: {e}")
            else:
                st.warning("Виберіть область!")
