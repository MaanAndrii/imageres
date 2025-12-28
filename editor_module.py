import streamlit as st
import os
from PIL import Image, ImageOps
from streamlit_cropper import st_cropper
import config  # Переконайтесь, що цей файл існує (див. нижче)
from logger import get_logger # Переконайтесь, що цей файл існує
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
    """Створює легку копію зображення для відображення в UI."""
    w, h = img.size
    if w <= target_width:
        return img, 1.0
    
    ratio = target_width / w
    new_h = max(1, int(h * ratio))
    proxy = img.resize((target_width, new_h), Image.Resampling.LANCZOS)
    return proxy, w / target_width

def calculate_max_crop_box(proxy_w: int, proxy_h: int, aspect_ratio: tuple) -> dict:
    """Розраховує максимальну рамку (для кнопки MAX). Повертає int координати."""
    if not aspect_ratio:
        pad = 10
        return {
            'left': pad, 'top': pad, 
            'width': max(10, proxy_w - 2*pad), 
            'height': max(10, proxy_h - 2*pad)
        }
    
    # Співвідношення (width / height)
    target_ratio = aspect_ratio[0] / aspect_ratio[1]
    
    # 1. Пробуємо вписати по ширині
    box_w = proxy_w
    box_h = int(box_w / target_ratio)
    
    # 2. Якщо висота завелика, вписуємо по висоті
    if box_h > proxy_h:
        box_h = proxy_h
        box_w = int(box_h * target_ratio)
        
    # Центруємо
    left = int((proxy_w - box_w) / 2)
    top = int((proxy_h - box_h) / 2)
    
    # Гарантуємо int і >0
    return {
        'left': max(0, left),
        'top': max(0, top),
        'width': max(10, int(box_w)),
        'height': max(10, int(box_h))
    }

@st.dialog("🛠 Editor", width="large")
def open_editor_dialog(fpath: str, T: dict):
    file_id = os.path.basename(fpath)
    
    # --- STATE INIT ---
    # Зберігаємо кут повороту
    if f'rot_{file_id}' not in st.session_state: 
        st.session_state[f'rot_{file_id}'] = 0
    # Лічильник для примусового оновлення віджета
    if f'reset_{file_id}' not in st.session_state: 
        st.session_state[f'reset_{file_id}'] = 0
    # Зберігаємо координати рамки (для MAX/Apply)
    if f'default_box_{file_id}' not in st.session_state: 
        st.session_state[f'default_box_{file_id}'] = None

    # --- LOAD IMAGE ---
    try:
        validate_image_file(fpath)
        img_original = Image.open(fpath)
        img_original = ImageOps.exif_transpose(img_original)
        img_original = img_original.convert('RGB')
        
        # Застосування повороту
        angle = st.session_state[f'rot_{file_id}']
        if angle != 0:
            img_original = img_original.rotate(-angle, expand=True)
            
        # Створення Proxy (для швидкодії)
        img_proxy, scale_factor = create_proxy_image(img_original)
        proxy_w, proxy_h = img_proxy.size
        orig_w, orig_h = img_original.size

    except Exception as e:
        st.error(f"Помилка завантаження: {e}")
        return

    # Info Header
    st.caption(get_file_info_str(fpath, img_original))

    # --- LAYOUT ---
    col_canvas, col_controls = st.columns([3, 1], gap="medium")

    # --- RIGHT PANEL (CONTROLS) ---
    with col_controls:
        # 1. Rotate
        st.markdown("**Обертання**")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("↺ -90°", key=f"l_{file_id}", use_container_width=True):
                st.session_state[f'rot_{file_id}'] -= 90
                st.session_state[f'reset_{file_id}'] += 1
                st.session_state[f'default_box_{file_id}'] = None # Скидаємо рамку
                st.rerun()
        with c2:
            if st.button("↻ +90°", key=f"r_{file_id}", use_container_width=True):
                st.session_state[f'rot_{file_id}'] += 90
                st.session_state[f'reset_{file_id}'] += 1
                st.session_state[f'default_box_{file_id}'] = None
                st.rerun()
        
        # 2. Aspect Ratio
        st.markdown("**Пропорції**")
        aspect_choice = st.selectbox(
            "Співвідношення", 
            list(config.ASPECT_RATIOS.keys()), 
            label_visibility="collapsed",
            key=f"asp_{file_id}"
        )
        aspect_val = config.ASPECT_RATIOS[aspect_choice]
        
        # 3. Reset & MAX
        br1, br2 = st.columns(2)
        with br1:
             if st.button("Скинути", key=f"rst_{file_id}", use_container_width=True):
                st.session_state[f'rot_{file_id}'] = 0
                st.session_state[f'default_box_{file_id}'] = None
                st.session_state[f'reset_{file_id}'] += 1
                st.rerun()
        with br2:
            if st.button("MAX ⛶", key=f"max_{file_id}", use_container_width=True):
                # Розрахунок максимальної рамки
                max_box = calculate_max_crop_box(proxy_w, proxy_h, aspect_val)
                st.session_state[f'default_box_{file_id}'] = max_box
                st.session_state[f'reset_{file_id}'] += 1
                st.rerun()

        st.divider()

    # --- CENTER (CANVAS) ---
    with col_canvas:
        # Унікальний ключ змушує віджет перемалюватись при зміні параметрів
        cropper_key = f"crp_{file_id}_{st.session_state[f'reset_{file_id}']}_{aspect_choice}"
        
        # Отримуємо примусові координати (якщо були задані кнопками MAX або Apply)
        default_coords = st.session_state.get(f'default_box_{file_id}', None)

        rect = st_cropper(
            img_proxy,
            realtime_update=True,
            box_color='#FF0000',
            aspect_ratio=aspect_val,
            default_coords=default_coords,
            should_resize_image=False, # Ми самі зробили проксі, не треба ресайзити
            return_type='box', # Повертає dict {left, top, width, height}
            key=cropper_key
        )

    # --- RIGHT PANEL (SAVE & INFO) ---
    with col_controls:
        # Розрахунок реальних координат з даних кропера
        real_w, real_h = 0, 0
        crop_box = None
        
        if rect:
            # Масштабуємо координати з Proxy на Original
            left = int(rect['left'] * scale_factor)
            top = int(rect['top'] * scale_factor)
            width = int(rect['width'] * scale_factor)
            height = int(rect['height'] * scale_factor)
            
            # Захист від виходу за межі (Clamping)
            left = max(0, min(left, orig_w))
            top = max(0, min(top, orig_h))
            if left + width > orig_w: width = orig_w - left
            if top + height > orig_h: height = orig_h - top
            
            real_w, real_h = width, height
            crop_box = (left, top, left + width, top + height)

        # --- MANUAL SIZE SECTION (SYNCED) ---
        st.markdown("**Точний розмір (px)**")
        
        # Відображаємо поточні розміри як значення за замовчуванням
        # Це "синхронізує" інпути з тим, що ви натягнули рамкою
        cur_w = real_w if real_w > 0 else orig_w
        cur_h = real_h if real_h > 0 else orig_h
        
        c_w, c_h = st.columns(2)
        input_w = c_w.number_input("W", value=cur_w, min_value=10, max_value=orig_w, label_visibility="collapsed")
        input_h = c_h.number_input("H", value=cur_h, min_value=10, max_value=orig_h, label_visibility="collapsed")
        
        # Кнопка застосування розміру
        if st.button("✓ Застосувати розмір", key=f"apply_size_{file_id}", use_container_width=True):
            # Переводимо реальні пікселі в координати Proxy
            target_w_proxy = int(input_w / scale_factor)
            target_h_proxy = int(input_h / scale_factor)
            
            # Центруємо
            new_left = int((proxy_w - target_w_proxy) / 2)
            new_top = int((proxy_h - target_h_proxy) / 2)
            
            st.session_state[f'default_box_{file_id}'] = {
                'left': max(0, new_left),
                'top': max(0, new_top),
                'width': target_w_proxy,
                'height': target_h_proxy
            }
            st.session_state[f'reset_{file_id}'] += 1
            st.rerun()

        # Поточний результат (Інфо)
        if real_w > 0:
            st.success(f"Результат: **{real_w} x {real_h}** px")
        
        st.divider()

        # --- SAVE BUTTON ---
        if st.button(T.get('btn_save_edit', '💾 Зберегти'), type="primary", use_container_width=True, key=f"save_{file_id}"):
            if crop_box:
                try:
                    # Кропаємо оригінал
                    final_img = img_original.crop(crop_box)
                    
                    # Зберігаємо з максимальною якістю
                    final_img.save(fpath, quality=95, subsampling=0)
                    
                    # Очистка
                    thumb = f"{fpath}.thumb.jpg"
                    if os.path.exists(thumb): os.remove(thumb)
                    
                    # Видаляємо ключі сесії
                    keys = [f'rot_{file_id}', f'reset_{file_id}', f'default_box_{file_id}']
                    for k in keys:
                        if k in st.session_state: del st.session_state[k]
                    
                    st.session_state['close_editor'] = True
                    st.toast("Зміни збережено!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Помилка збереження: {e}")
            else:
                st.warning("Спочатку виберіть область!")
