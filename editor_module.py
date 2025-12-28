# ... (початок файлу без змін)

            st.divider()
            
            # MAX button
            if st.button(
                "MAX ⛶",
                use_container_width=True,
                key=f"max_{file_id}",
                help="Максимальна область у вибраному співвідношенні"
            ):
                # Calculate MAX box for PROXY image
                max_box = calculate_max_crop_box(proxy_w, proxy_h, aspect_val)
                st.session_state[f'crop_box_{file_id}'] = max_box
                st.session_state[f'reset_{file_id}'] += 1
                
                # Calculate real dimensions for display
                real_w = int(max_box['width'] * scale_factor)
                real_h = int(max_box['height'] * scale_factor)
                
                if aspect_val:
                    ratio_str = f"{aspect_val[0]}:{aspect_val[1]}"
                else:
                    ratio_str = "free"
                
                # FIX 2: Заміна проблемного емодзі ⛶ на валідний
                st.toast(
                    f"✅ MAX: {real_w}×{real_h}px ({ratio_str})",
                    icon="📐"  # або "🖼️", "🔍" — будь-який простий емодзі
                )
                logger.info(
                    f"MAX activated: {real_w}x{real_h} ({ratio_str}) "
                    f"for proxy {proxy_w}x{proxy_h}"
                )
                st.rerun()
        
        # === CANVAS ===
        with col_canvas:
            cropper_id = f"crp_{file_id}_{st.session_state[f'reset_{file_id}']}_{aspect_choice}"
            default_box = st.session_state.get(f'crop_box_{file_id}', None)
            
            try:
                rect = st_cropper(
                    img_proxy,
                    realtime_update=True,
                    box_color='#FF0000',
                    aspect_ratio=aspect_val,
                    should_resize_image=False,
                    default_coords=default_box,
                    return_type='box',
                    key=cropper_id
                )
            except Exception as e:
                st.error(f"Cropper error: {e}")
                logger.error(f"Cropper failed: {e}")
                rect = None
        
        # === CROP INFO & SAVE ===
        with col_controls:
            crop_box = None
            real_w, real_h = 0, 0
            
            if rect:
                try:
                    left = int(rect['left'] * scale_factor)
                    top = int(rect['top'] * scale_factor)
                    width = int(rect['width'] * scale_factor)
                    height = int(rect['height'] * scale_factor)
                    
                    orig_w, orig_h = img_full.size
                    
                    left = max(0, min(left, orig_w))
                    top = max(0, min(top, orig_h))
                    
                    if left + width > orig_w:
                        width = orig_w - left
                    if top + height > orig_h:
                        height = orig_h - top
                    
                    width = max(1, width)
                    height = max(1, height)
                    
                    crop_box = (left, top, left + width, top + height)
                    real_w, real_h = width, height
                    
                    # FIX 1: Синхронізація Manual Size з поточною рамкою обрізки
                    # Зберігаємо реальні розміри в session_state для використання в number_input нижче
                    st.session_state[f'manual_w_val_{file_id}'] = real_w
                    st.session_state[f'manual_h_val_{file_id}'] = real_h
                    
                    logger.debug(
                        f"Crop calculated: proxy ({rect['left']:.0f}, {rect['top']:.0f}, "
                        f"{rect['width']:.0f}x{rect['height']:.0f}) → "
                        f"original ({left}, {top}, {width}x{height})"
                    )
                
                except Exception as e:
                    logger.error(f"Crop calculation failed: {e}")
                    st.warning(f"⚠️ Помилка розрахунку: {e}")
            
            # Display dimensions
            if real_w > 0 and real_h > 0:
                st.info(f"📏 **{real_w} × {real_h}** px")
            else:
                st.info("📏 **Оберіть область**")
            
            # FIX 1 + FIX 4: Переміщення блоку Manual Size ПІСЛЯ розрахунку реальних розмірів
            # та додавання умовного блокування/корекції при фіксованому аспекті
            st.markdown("**📐 Manual Size (px)**")
            col_w, col_h = st.columns(2)
            
            # Ініціалізація значень за замовчуванням, якщо ще немає
            if f'manual_w_val_{file_id}' not in st.session_state:
                st.session_state[f'manual_w_val_{file_id}'] = img_full.width // 2
            if f'manual_h_val_{file_id}' not in st.session_state:
                st.session_state[f'manual_h_val_{file_id}'] = img_full.height // 2
            
            # Якщо аспект фіксований — коригуємо один вимір під нього
            if aspect_val is not None and real_w > 0 and real_h > 0:
                # Використовуємо поточні розміри як базу (вони вже відповідають аспекту)
                default_w = real_w
                default_h = real_h
            else:
                default_w = st.session_state[f'manual_w_val_{file_id}']
                default_h = st.session_state[f'manual_h_val_{file_id}']
            
            with col_w:
                manual_width = st.number_input(
                    "Width",
                    min_value=10,
                    max_value=img_full.width,
                    value=default_w,
                    step=10,
                    key=f"manual_w_input_{file_id}",  # унікальний key
                    label_visibility="collapsed",
                    disabled=aspect_val is not None  # FIX 4: блокуємо при фіксованому аспекті
                )
            
            with col_h:
                manual_height = st.number_input(
                    "Height",
                    min_value=10,
                    max_value=img_full.height,
                    value=default_h,
                    step=10,
                    key=f"manual_h_input_{file_id}",
                    label_visibility="collapsed",
                    disabled=aspect_val is not None
                )
            
            # Кнопка Apply — активна тільки при вільному аспекті
            apply_disabled = aspect_val is not None
            if apply_disabled:
                st.caption("ℹ️ Manual size доступний тільки при вільному аспекті")
            
            if st.button(
                "✓ Apply Size",
                use_container_width=True,
                key=f"apply_manual_{file_id}",
                help="Set crop box to specified dimensions",
                disabled=apply_disabled
            ):
                proxy_width = int(manual_width / scale_factor)
                proxy_height = int(manual_height / scale_factor)
                
                left = (proxy_w - proxy_width) // 2
                top = (proxy_h - proxy_height) // 2
                
                left = max(0, min(left, proxy_w - proxy_width))
                top = max(0, min(top, proxy_h - proxy_height))
                
                st.session_state[f'crop_box_{file_id}'] = {
                    'left': left,
                    'top': top,
                    'width': proxy_width,
                    'height': proxy_height
                }
                st.session_state[f'reset_{file_id}'] += 1
                st.toast(f"✅ Set: {manual_width}×{manual_height}px", icon="📐")
                st.rerun()

            # ... (решта коду без змін — Save button тощо)
