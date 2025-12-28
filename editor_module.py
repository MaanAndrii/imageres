import streamlit as st
import os
from PIL import Image, ImageOps
from streamlit_cropper import st_cropper
import config 
from logger import get_logger 
from validators import validate_image_file

logger = get_logger(__name__)

# --- HELPER FUNCTIONS ---

def get_file_info_str(fpath: str, img: Image.Image) -> str:
    try:
        size_bytes = os.path.getsize(fpath)
        size_mb = size_bytes / (1024 * 1024)
        size_str = f"{size_mb:.2f} MB" if size_mb >= 1 else f"{size_bytes/1024:.1f} KB"
        return f"📄 **{os.path.basename(fpath)}** &nbsp;•&nbsp; 📏 **{img.width}x{img.height}** &nbsp;•&nbsp; 💾 **{size_str}**"
    except Exception:
        return "📄 Інформація недоступна"

def create_proxy_image(img: Image.Image, target_width: int = 700):
    """Створює легку копію зображення для UI."""
    w, h = img.size
    if w <= target_width:
        return img, 1.0
    ratio = target_width / w
    new_h = max(1, int(h * ratio))
    proxy = img.resize((target_width, new_h), Image.Resampling.LANCZOS)
    return proxy, w / target_width

def sanitize_int(val, min_v, max_v):
    """Гарантує, що число int і знаходиться в межах."""
    try:
        val = int(val)
        return max(min_v, min(val, max_v))
    except (ValueError, TypeError):
        return min_v

def calculate_max_box(proxy_w, proxy_h, aspect_ratio_tuple):
    """Рахує MAX рамку. Повертає TUPLE (left, top, width, height)."""
    pad = 10
    
    # 1. FREE MODE
    if not aspect_ratio_tuple:
        safe_w = max(10, proxy_w - 2*pad)
        safe_h = max(10, proxy_h - 2*pad)
        return (pad, pad, safe_w, safe_h)
    
    # 2. ASPECT MODE
    try:
        ar_w, ar_h = aspect_ratio_tuple
        target_ratio = ar_w / ar_h
        
        # Вписуємо по ширині
        box_w = proxy_w
        box_h = int(box_w / target_ratio)
        
        # Якщо не влізло по висоті, вписуємо по висоті
        if box_h > proxy_h:
            box_h = proxy_h
            box_w = int(box_h * target_ratio)
            
        left = int((proxy_w - box_w) / 2)
        top = int((proxy_h - box_h) / 2)
        
        return (max(0, left), max(0, top), max(10, box_w), max(10, box_h))
    except Exception:
        return (0, 0, proxy_w, proxy_h)

@st.dialog("🛠 Editor", width="large")
def open_editor_dialog(fpath: str, T: dict):
    file_id = os.path.basename(fpath)
    
    # --- 1. KEY MANAGEMENT ---
    # Всі ключі для session_state визначаємо тут, щоб уникнути хаосу
    k_rot = f"ed_rot_{file_id}"
    k_reset = f"ed_reset_{file_id}"     # Лічильник для оновлення кропера
    k_box = f"ed_box_{file_id}"         # Примусові координати (tuple)
    k_aspect = f"ed_asp_{file_id}"      # Ключ селекта пропорцій
    k_in_w = f"ed_in_w_{file_id}"       # Інпут ширини
    k_in_h = f"ed_in_h_{file_id}"       # Інпут висоти

    # --- 2. STATE INITIALIZATION ---
    if k_rot not in st.session_state: st.session_state[k_rot] = 0
    if k_reset not in st.session_state: st.session_state[k_reset] = 0
    if k_box not in st.session_state: st.session_state[k_box] = None
    # Aspect Ratio ініціалізуємо вручну, якщо його немає, щоб мати доступ до нього в callbacks
    if k_aspect not in st.session_state: st.session_state[k_aspect] = list(config.ASPECT_RATIOS.keys())[0]

    # --- 3. LOAD IMAGE & PROXY ---
    try:
        validate_image_file(fpath)
        img_orig = Image.open(fpath)
        img_orig = ImageOps.exif_transpose(img_orig)
        img_orig = img_orig.convert('RGB')
        
        # Apply Rotation
        angle = st.session_state[k_rot]
        if angle != 0:
            img_orig = img_orig.rotate(-angle, expand=True)
            
        # Create Proxy
        img_proxy, scale_factor = create_proxy_image(img_orig)
        proxy_w, proxy_h = img_proxy.size
        orig_w, orig_h = img_orig.size
        
    except Exception as e:
        st.error(f"Critical Load Error: {e}")
        return

    st.caption(get_file_info_str(fpath, img_orig))

    # --- 4. CALLBACKS (LOGIC CORE) ---
    # Ця частина коду виконується ТІЛЬКИ при натисканні кнопок, ДО рендеру

    def cb_rotate(delta):
        st.session_state[k_rot] += delta
        st.session_state[k_box] = None # Скидаємо рамку
        st.session_state[k_reset] += 1

    def cb_reset():
        st.session_state[k_rot] = 0
        st.session_state[k_box] = None
        st.session_state[k_reset] += 1

    def cb_max():
        # 1. Читаємо поточний аспект з селекта
        cur_asp_name = st.session_state[k_aspect]
        cur_asp_val = config.ASPECT_RATIOS.get(cur_asp_name, None)
        
        # 2. Рахуємо рамку
        new_box = calculate_max_box(proxy_w, proxy_h, cur_asp_val)
        
        # 3. Записуємо
        st.session_state[k_box] = new_box
        st.session_state[k_reset] += 1

    def cb_apply_size():
        # 1. Читаємо введені юзером числа
        user_w = st.session_state.get(k_in_w, 100)
        user_h = st.session_state.get(k_in_h, 100)
        
        # 2. Переводимо в Proxy координати
        target_w = int(user_w / scale_factor)
        target_h = int(user_h / scale_factor)
        
        # 3. Центруємо
        l = int((proxy_w - target_w) / 2)
        t = int((proxy_h - target_h) / 2)
        
        # 4. ВАЖЛИВО: Змінюємо пропорції на "Free", інакше кропер сплющить рамку
        # Знаходимо ключ для "Free" (зазвичай "Free / Вільний")
        free_key = [k for k, v in config.ASPECT_RATIOS.items() if v is None][0]
        st.session_state[k_aspect] = free_key
        
        # 5. Оновлюємо рамку
        st.session_state[k_box] = (max(0, l), max(0, t), target_w, target_h)
        st.session_state[k_reset] += 1

    # --- 5. UI LAYOUT ---
    col_can, col_ctrl = st.columns([3, 1], gap="medium")

    # --- LEFT: CANVAS ---
    with col_can:
        # Отримуємо значення пропорцій
        curr_aspect_name = st.session_state.get(k_aspect, "Free / Вільний")
        curr_aspect_val = config.ASPECT_RATIOS.get(curr_aspect_name, None)
        
        # Примусові координати (tuple)
        default_coords = st.session_state.get(k_box, None)
        
        # Унікальний ключ для перестворення віджета при змінах
        cropper_id = f"crp_{file_id}_{st.session_state[k_reset]}_{curr_aspect_name}"

        rect = st_cropper(
            img_proxy,
            realtime_update=True,
            box_color='#FF0000',
            aspect_ratio=curr_aspect_val,
            default_coords=default_coords,
            should_resize_image=False, 
            return_type='box', # Повертає словник!
            key=cropper_id
        )

    # --- RIGHT: CONTROLS ---
    with col_ctrl:
        # A. Rotate
        st.write("🔄 **Обертання**")
        c1, c2 = st.columns(2)
        c1.button("↺ -90°", key=f"btn_l_{file_id}", use_container_width=True, on_click=cb_rotate, args=(-90,))
        c2.button("↻ +90°", key=f"btn_r_{file_id}", use_container_width=True, on_click=cb_rotate, args=(90,))
        
        # B. Aspect Select
        st.write("📐 **Пропорції**")
        st.selectbox(
            "Ratio", 
            list(config.ASPECT_RATIOS.keys()), 
            key=k_aspect, # Прив'язали до state
            label_visibility="collapsed"
        )
        
        # C. Actions
        b1, b2 = st.columns(2)
        b1.button("Скинути", key=f"btn_rst_{file_id}", use_container_width=True, on_click=cb_reset)
        b2.button("MAX ⛶", key=f"btn_max_{file_id}", use_container_width=True, on_click=cb_max)

        st.divider()

        # D. Realtime Stats & Calc
        real_w, real_h = 0, 0
        crop_box = None

        if rect:
            # Масштабуємо Proxy -> Original
            l = int(rect['left'] * scale_factor)
            t = int(rect['top'] * scale_factor)
            w = int(rect['width'] * scale_factor)
            h = int(rect['height'] * scale_factor)
            
            # Clamp (щоб не вилізти за межі)
            l = max(0, min(l, orig_w))
            t = max(0, min(t, orig_h))
            if l + w > orig_w: w = orig_w - l
            if t + h > orig_h: h = orig_h - t
            
            real_w, real_h = w, h
            crop_box = (l, t, l+w, t+h)
        
        # E. Manual Input (Sanitized)
        st.write("✏️ **Точний розмір (px)**")
        
        # Значення для полів вводу (те, що зараз на екрані)
        # Але перевіряємо, щоб не було 0
        val_w = max(10, real_w if real_w > 0 else orig_w)
        val_h = max(10, real_h if real_h > 0 else orig_h)
        
        cw, ch = st.columns(2)
        cw.number_input("W", value=val_w, min_value=10, max_value=orig_w, key=k_in_w, label_visibility="collapsed")
        ch.number_input("H", value=val_h, min_value=10, max_value=orig_h, key=k_in_h, label_visibility="collapsed")
        
        # Кнопка з CALLBACK
        st.button("✓ Застосувати", key=f"btn_apply_{file_id}", use_container_width=True, on_click=cb_apply_size)

        if real_w > 0:
            st.info(f"Розмір: **{real_w} x {real_h}** px")
        
        st.divider()

        # F. Save
        if st.button(T.get('btn_save_edit', '💾 Зберегти'), type="primary", use_container_width=True, key=f"save_{file_id}"):
            if crop_box:
                try:
                    final_img = img_orig.crop(crop_box)
                    final_img.save(fpath, quality=95, subsampling=0)
                    
                    # Cleanup cache
                    thumb = f"{fpath}.thumb.jpg"
                    if os.path.exists(thumb): os.remove(thumb)
                    
                    # Cleanup State
                    keys_to_del = [k_rot, k_reset, k_box, k_aspect, k_in_w, k_in_h]
                    for k in keys_to_del:
                        if k in st.session_state: del st.session_state[k]
                    
                    st.session_state['close_editor'] = True
                    st.rerun()
                except Exception as e:
                    st.error(f"Save Error: {e}")
            else:
                st.warning("Область не обрана")
