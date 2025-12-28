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
    """Створює легку версію картинки для відображення в браузері."""
    w, h = img.size
    if w <= target_width:
        return img, 1.0
    
    ratio = target_width / w
    new_h = max(1, int(h * ratio))
    proxy = img.resize((target_width, new_h), Image.Resampling.LANCZOS)
    return proxy, w / target_width

def get_max_box_tuple(proxy_w, proxy_h, aspect_ratio):
    """Рахує максимальну рамку і повертає кортеж (left, top, width, height)."""
    pad = 10
    
    # 1. Вільний режим
    if not aspect_ratio:
        return (pad, pad, max(10, proxy_w - 2*pad), max(10, proxy_h - 2*pad))
    
    # 2. Фіксовані пропорції
    ar_w, ar_h = aspect_ratio
    target_ratio = ar_w / ar_h
    
    # Вписуємо по ширині
    box_w = proxy_w
    box_h = int(box_w / target_ratio)
    
    # Якщо висота завелике, вписуємо по висоті
    if box_h > proxy_h:
        box_h = proxy_h
        box_w = int(box_h * target_ratio)
        
    left = int((proxy_w - box_w) / 2)
    top = int((proxy_h - box_h) / 2)
    
    return (max(0, left), max(0, top), max(10, box_w), max(10, box_h))

# --- ОСНОВНА ФУНКЦІЯ ---

@st.dialog("🛠 Editor", width="large")
def open_editor_dialog(fpath: str, T: dict):
    file_id = os.path.basename(fpath)
    
    # === 1. ІНІЦІАЛІЗАЦІЯ СТАНУ ===
    # Використовуємо унікальні ключі для кожного файлу
    
    # Кут повороту
    k_rot = f"rot_{file_id}"
    if k_rot not in st.session_state: st.session_state[k_rot] = 0
    
    # Лічильник оновлень (найважливіше для Hard Reset)
    k_update_id = f"upd_{file_id}" 
    if k_update_id not in st.session_state: st.session_state[k_update_id] = 0
    
    # Примусові координати рамки (Tuple)
    k_force_box = f"box_{file_id}"
    if k_force_box not in st.session_state: st.session_state[k_force_box] = None
    
    # Поточні пропорції (ключ словника)
    k_aspect_key = f"asp_key_{file_id}"
    if k_aspect_key not in st.session_state: 
        st.session_state[k_aspect_key] = "Free / Вільний" # Дефолт

    # === 2. ЗАВАНТАЖЕННЯ ЗОБРАЖЕННЯ ===
    try:
        validate_image_file(fpath)
        img_orig = Image.open(fpath)
        img_orig = ImageOps.exif_transpose(img_orig)
        img_orig = img_orig.convert('RGB')
        
        # Застосування повороту
        current_angle = st.session_state[k_rot]
        if current_angle != 0:
            img_orig = img_orig.rotate(-current_angle, expand=True)
            
        # Створення Proxy
        img_proxy, scale_factor = create_proxy_image(img_orig)
        proxy_w, proxy_h = img_proxy.size
        orig_w, orig_h = img_orig.size
        
    except Exception as e:
        st.error(f"Помилка відкриття: {e}")
        return

    st.caption(get_file_info_str(fpath, img_orig))

    # === 3. CALLBACKS (ЛОГІКА КНОПОК) ===
    # Ці функції виконуються ДО перемальовки екрану

    def on_rotate(delta):
        st.session_state[k_rot] += delta
        st.session_state[k_force_box] = None # Скидаємо рамку при повороті
        st.session_state[k_update_id] += 1   # Змушуємо кропер перестворитись

    def on_reset():
        st.session_state[k_rot] = 0
        st.session_state[k_force_box] = None
        st.session_state[k_aspect_key] = "Free / Вільний"
        st.session_state[k_update_id] += 1

    def on_max():
        # Отримуємо поточні пропорції
        curr_asp_name = st.session_state[k_aspect_key]
        curr_asp_val = config.ASPECT_RATIOS.get(curr_asp_name, None)
        
        # Рахуємо макс рамку для цих пропорцій
        max_box = get_max_box_tuple(proxy_w, proxy_h, curr_asp_val)
        
        st.session_state[k_force_box] = max_box
        st.session_state[k_update_id] += 1

    def on_apply_manual_size():
        # Читаємо значення з widget state
        w_val = st.session_state.get(f"in_w_{file_id}", 100)
        h_val = st.session_state.get(f"in_h_{file_id}", 100)
        
        # Переводимо в Proxy координати
        pw = int(w_val / scale_factor)
        ph = int(h_val / scale_factor)
        
        # Центруємо
        pl = int((proxy_w - pw) / 2)
        pt = int((proxy_h - ph) / 2)
        
        # ВАЖЛИВО: Перемикаємо в режим Free, щоб не ламало пропорції
        # Шукаємо ключ для Free (де значення None)
        free_key = [k for k, v in config.ASPECT_RATIOS.items() if v is None][0]
        st.session_state[k_aspect_key] = free_key
        
        st.session_state[k_force_box] = (max(0, pl), max(0, pt), pw, ph)
        st.session_state[k_update_id] += 1

    # === 4. ІНТЕРФЕЙС ===
    col_canvas, col_tools = st.columns([3, 1], gap="medium")

    # --- ПРАВА КОЛОНКА (ІНСТРУМЕНТИ) ---
    with col_tools:
        # A. Rotate
        st.markdown("**1. Поворот**")
        c1, c2 = st.columns(2)
        c1.button("↺ -90°", key=f"btn_l_{file_id}", on_click=on_rotate, args=(-90,), use_container_width=True)
        c2.button("↻ +90°", key=f"btn_r_{file_id}", on_click=on_rotate, args=(90,), use_container_width=True)
        
        # B. Aspect Ratio
        st.markdown("**2. Пропорції**")
        st.selectbox(
            "Ratio", 
            options=list(config.ASPECT_RATIOS.keys()), 
            key=k_aspect_key, # Зв'язано зі станом
            label_visibility="collapsed"
        )
        # Отримуємо значення для передачі в кропер
        selected_aspect_val = config.ASPECT_RATIOS[st.session_state[k_aspect_key]]
        
        # C. Actions
        b1, b2 = st.columns(2)
        b1.button("Скинути", key=f"btn_rst_{file_id}", on_click=on_reset, use_container_width=True)
        b2.button("MAX ⛶", key=f"btn_max_{file_id}", on_click=on_max, use_container_width=True)
        
        st.divider()

    # --- ЛІВА КОЛОНКА (ПОЛОТНО) ---
    with col_canvas:
        # ГЕНЕРУЄМО КЛЮЧ, ЩО ЗАЛЕЖИТЬ ВІД ЛІЧИЛЬНИКА (Hard Reset)
        # Якщо k_update_id змінився, старий віджет знищується, новий створюється.
        # Це гарантує застосування default_coords.
        cropper_dynamic_key = f"crp_{file_id}_{st.session_state[k_update_id]}"
        
        force_box = st.session_state[k_force_box]
        
        rect = st_cropper(
            img_proxy,
            realtime_update=True,
            box_color='#FF0000',
            aspect_ratio=selected_aspect_val,
            default_coords=force_box, # Працює тільки при створенні віджета (зміни ключа)
            should_resize_image=False, 
            return_type='box', 
            key=cropper_dynamic_key
        )

    # --- ПРАВА КОЛОНКА (ЗБЕРЕЖЕННЯ І ВВІД) ---
    with col_tools:
        # Розрахунок реальних координат (тільки для збереження і відображення)
        real_w, real_h = 0, 0
        crop_box = None
        
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
            
        # D. Manual Input
        st.markdown("**3. Точний розмір (px)**")
        cw, ch = st.columns(2)
        
        # Inputs не залежать від кропера, щоб уникнути циклів
        # Вони просто приймають числа для кнопки "Застосувати"
        input_w = cw.number_input("W", value=orig_w, min_value=10, max_value=orig_w, key=f"in_w_{file_id}", label_visibility="collapsed")
        input_h = ch.number_input("H", value=orig_h, min_value=10, max_value=orig_h, key=f"in_h_{file_id}", label_visibility="collapsed")
        
        st.button("✓ Застосувати розмір", key=f"btn_apply_{file_id}", on_click=on_apply_manual_size, use_container_width=True)

        if real_w > 0:
            st.info(f"Обрано: **{real_w} x {real_h}** px")
            
        st.divider()

        # E. Save
        if st.button(T.get('btn_save_edit', '💾 Зберегти'), type="primary", use_container_width=True, key=f"btn_save_{file_id}"):
            if crop_box:
                try:
                    final_img = img_orig.crop(crop_box)
                    final_img.save(fpath, quality=95, subsampling=0)
                    
                    # Cleanup
                    thumb = f"{fpath}.thumb.jpg"
                    if os.path.exists(thumb): os.remove(thumb)
                    
                    # Clean State
                    keys = [k_rot, k_update_id, k_force_box, k_aspect_key, f"in_w_{file_id}", f"in_h_{file_id}"]
                    for k in keys:
                        if k in st.session_state: del st.session_state[k]
                    
                    st.session_state['close_editor'] = True
                    st.toast("Успішно збережено!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Помилка збереження: {e}")
            else:
                st.warning("Область не обрана")
