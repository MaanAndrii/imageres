"""
Watermarker Pro v7.0 - Utils Module
====================================
File handling, settings, presets, and UI utilities
"""

import streamlit as st
import os
import glob
import json
import tempfile
import shutil
import threading
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import config
import watermarker_engine as engine
from logger import get_logger
from validators import sanitize_filename, ValidationError

logger = get_logger(__name__)

# Thread lock for session state
_session_lock = threading.Lock()

# === CSS INJECTION ===
def inject_css():
    """Inject custom CSS for UI styling"""
    st.markdown("""
    <style>
        div[data-testid="column"] {
            background-color: #f8f9fa;
            border-radius: 8px;
            padding: 10px;
            border: 1px solid #eee;
            transition: all 0.2s ease;
        }
        div[data-testid="column"]:hover {
            border-color: #ff4b4b;
            transform: translateY(-2px);
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }
        div[data-testid="column"] button {
            width: 100%;
            margin-top: 5px;
        }
        .block-container {
            padding-top: 2rem;
        }
        .preview-placeholder {
            border: 2px dashed #e0e0e0;
            border-radius: 10px;
            padding: 40px 20px;
            text-align: center;
            color: #888;
            background-color: #fafafa;
            margin-top: 10px;
        }
        .preview-icon {
            font-size: 40px;
            margin-bottom: 10px;
            display: block;
        }
        .stat-card {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 15px;
            border-radius: 10px;
            color: white;
            margin: 10px 0;
        }
    </style>
    """, unsafe_allow_html=True)

# === SESSION STATE INITIALIZATION ===
def init_session_state():
    """Initialize session state with default values"""
    
    # Core state
    if 'temp_dir' not in st.session_state:
        try:
            st.session_state['temp_dir'] = tempfile.mkdtemp(prefix="wm_pro_v7_")
            logger.info(f"Temp directory created: {st.session_state['temp_dir']}")
        except Exception as e:
            logger.error(f"Failed to create temp dir: {e}")
            st.session_state['temp_dir'] = tempfile.gettempdir()
    
    if 'file_cache' not in st.session_state:
        st.session_state['file_cache'] = {}
    
    if 'selected_files' not in st.session_state:
        st.session_state['selected_files'] = set()
    
    if 'uploader_key' not in st.session_state:
        st.session_state['uploader_key'] = 0
    
    if 'lang_code' not in st.session_state:
        st.session_state['lang_code'] = 'ua'
    
    if 'editing_file' not in st.session_state:
        st.session_state['editing_file'] = None
    
    if 'close_editor' not in st.session_state:
        st.session_state['close_editor'] = False
    
    if 'results' not in st.session_state:
        st.session_state['results'] = None
    
    # Initialize settings keys
    for key, value in config.DEFAULT_SETTINGS.items():
        key_name = f'{key}_key' if not key.endswith('_val') else f'{key}_state'
        if key_name not in st.session_state:
            st.session_state[key_name] = value

# === FILE OPERATIONS ===
def save_uploaded_file(uploaded_file) -> Tuple[str, str]:
    """
    Save uploaded file to temp directory
    
    Args:
        uploaded_file: Streamlit UploadedFile
        
    Returns:
        Tuple of (file_path, sanitized_filename)
    """
    try:
        temp_dir = st.session_state['temp_dir']
        
        # Sanitize filename
        safe_name = sanitize_filename(uploaded_file.name)
        file_path = os.path.join(temp_dir, safe_name)
        
        # Handle duplicates
        if os.path.exists(file_path):
            base, ext = os.path.splitext(safe_name)
            timestamp = datetime.now().strftime("%H%M%S%f")
            safe_name = f"{base}_{timestamp}{ext}"
            file_path = os.path.join(temp_dir, safe_name)
        
        # Write file
        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        
        logger.info(f"File saved: {safe_name}")
        return file_path, safe_name
    
    except Exception as e:
        logger.error(f"Failed to save file {uploaded_file.name}: {e}")
        raise

def cleanup_temp_directory():
    """Clean up temporary directory and files"""
    try:
        temp_dir = st.session_state.get('temp_dir')
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
            logger.info(f"Temp directory cleaned: {temp_dir}")
            
            # Create new temp dir
            st.session_state['temp_dir'] = tempfile.mkdtemp(prefix="wm_pro_v7_")
    
    except Exception as e:
        logger.error(f"Cleanup failed: {e}")

# === FONT OPERATIONS ===
def get_available_fonts() -> List[str]:
    """
    Get list of available font files
    
    Returns:
        List of font filenames
    """
    try:
        font_dir = config.get_fonts_dir()
        
        if not font_dir.exists():
            logger.warning(f"Font directory not found: {font_dir}")
            return []
        
        fonts = list(font_dir.glob("*.ttf")) + list(font_dir.glob("*.otf"))
        font_names = [f.name for f in fonts]
        
        logger.debug(f"Found {len(font_names)} fonts")
        return sorted(font_names)
    
    except Exception as e:
        logger.error(f"Failed to list fonts: {e}")
        return []

# === SETTINGS OPERATIONS ===
def handle_pos_change():
    """Handle watermark position change with preset application"""
    try:
        position = st.session_state.get('wm_pos_key', 'bottom-right')
        
        if position == 'tiled':
            settings = config.TILED_SETTINGS
        else:
            settings = config.CORNER_SETTINGS
        
        # Apply settings
        for key, value in settings.items():
            st.session_state[f'{key}_key'] = value
        
        logger.debug(f"Position changed to: {position}")
    
    except Exception as e:
        logger.error(f"Failed to handle position change: {e}")

def reset_settings():
    """Reset all settings to defaults"""
    try:
        for key, value in config.DEFAULT_SETTINGS.items():
            key_name = f'{key}_key' if not key.endswith('_val') else f'{key}_state'
            st.session_state[key_name] = value
        
        logger.info("Settings reset to defaults")
    
    except Exception as e:
        logger.error(f"Failed to reset settings: {e}")

# === PRESET OPERATIONS ===
def get_current_settings_json(uploaded_wm_file) -> str:
    """
    Export current settings as JSON
    
    Args:
        uploaded_wm_file: Currently uploaded watermark file
        
    Returns:
        JSON string of settings
    """
    try:
        wm_b64 = None
        
        # Get watermark bytes
        if uploaded_wm_file:
            wm_b64 = engine.image_to_base64(uploaded_wm_file.getvalue())
        elif st.session_state.get('preset_wm_bytes_key'):
            wm_b64 = engine.image_to_base64(st.session_state['preset_wm_bytes_key'])
        
        settings = {
            'version': config.APP_VERSION,
            'created': datetime.now().isoformat(),
            'resize_val': st.session_state.get('resize_val_state', 1920),
            'wm_pos': st.session_state.get('wm_pos_key', 'bottom-right'),
            'wm_scale': st.session_state.get('wm_scale_key', 15),
            'wm_opacity': st.session_state.get('wm_opacity_key', 1.0),
            'wm_margin': st.session_state.get('wm_margin_key', 15),
            'wm_gap': st.session_state.get('wm_gap_key', 30),
            'wm_angle': st.session_state.get('wm_angle_key', 0),
            'wm_text': st.session_state.get('wm_text_key', ''),
            'wm_text_color': st.session_state.get('wm_text_color_key', '#FFFFFF'),
            'font_name': st.session_state.get('font_name_key', None),
            'out_fmt': st.session_state.get('out_fmt_key', 'JPEG'),
            'out_quality': st.session_state.get('out_quality_key', 80),
            'naming_mode': st.session_state.get('naming_mode_key', 'Keep Original'),
            'naming_prefix': st.session_state.get('naming_prefix_key', ''),
            'wm_image_b64': wm_b64
        }
        
        return json.dumps(settings, indent=4, ensure_ascii=False)
    
    except Exception as e:
        logger.error(f"Failed to export settings: {e}")
        return "{}"

def apply_settings_from_json(json_file) -> Tuple[bool, Optional[str]]:
    """
    Load settings from JSON preset
    
    Args:
        json_file: Uploaded JSON file
        
    Returns:
        Tuple of (success: bool, error_message: Optional[str])
    """
    try:
        data = json.load(json_file)
        
        # Validate version (optional)
        if 'version' in data:
            logger.info(f"Loading preset version: {data['version']}")
        
        # Apply settings safely
        mapping = {
            'resize_val': 'resize_val_state',
            'wm_pos': 'wm_pos_key',
            'wm_scale': 'wm_scale_key',
            'wm_opacity': 'wm_opacity_key',
            'wm_margin': 'wm_margin_key',
            'wm_gap': 'wm_gap_key',
            'wm_angle': 'wm_angle_key',
            'wm_text': 'wm_text_key',
            'wm_text_color': 'wm_text_color_key',
            'font_name': 'font_name_key',
            'out_fmt': 'out_fmt_key',
            'out_quality': 'out_quality_key',
            'naming_mode': 'naming_mode_key',
            'naming_prefix': 'naming_prefix_key'
        }
        
        for data_key, state_key in mapping.items():
            if data_key in data:
                st.session_state[state_key] = data[data_key]
        
        # Handle watermark image
        if 'wm_image_b64' in data and data['wm_image_b64']:
            try:
                img_bytes = engine.base64_to_bytes(data['wm_image_b64'])
                st.session_state['preset_wm_bytes_key'] = img_bytes
            except Exception as e:
                logger.warning(f"Failed to load preset watermark: {e}")
                st.session_state['preset_wm_bytes_key'] = None
        else:
            st.session_state['preset_wm_bytes_key'] = None
        
        logger.info("Preset loaded successfully")
        return True, None
    
    except json.JSONDecodeError as e:
        error_msg = f"Invalid JSON format: {e}"
        logger.error(error_msg)
        return False, error_msg
    
    except Exception as e:
        error_msg = f"Failed to load preset: {e}"
        logger.error(error_msg)
        return False, error_msg

# === WATERMARK PREPARATION ===
def prepare_watermark_object(wm_file, selected_font_name: Optional[str]) -> Optional[object]:
    """
    Prepare watermark object from text or image
    
    Args:
        wm_file: Uploaded watermark file (or None)
        selected_font_name: Selected font filename
        
    Returns:
        PIL Image watermark or None
    """
    try:
        wm_text = st.session_state.get('wm_text_key', '').strip()
        
        # Text watermark has priority
        if wm_text:
            font_path = None
            if selected_font_name:
                font_path = str(config.get_fonts_dir() / selected_font_name)
            
            wm_obj = engine.create_text_watermark(
                wm_text,
                font_path,
                config.DEFAULT_TEXT_SIZE_PT,
                st.session_state.get('wm_text_color_key', '#FFFFFF')
            )
            
            if wm_obj:
                opacity = st.session_state.get('wm_opacity_key', 1.0)
                wm_obj = engine.apply_opacity(wm_obj, opacity)
                return wm_obj
        
        # Image watermark
        wm_bytes = None
        if wm_file:
            wm_bytes = wm_file.getvalue()
        elif st.session_state.get('preset_wm_bytes_key'):
            wm_bytes = st.session_state['preset_wm_bytes_key']
        
        if wm_bytes:
            wm_obj = engine.load_watermark_from_bytes(wm_bytes)
            opacity = st.session_state.get('wm_opacity_key', 1.0)
            wm_obj = engine.apply_opacity(wm_obj, opacity)
            return wm_obj
        
        return None
    
    except Exception as e:
        logger.error(f"Watermark preparation failed: {e}")
        raise

def get_resize_config() -> Dict:
    """
    Get current resize configuration
    
    Returns:
        Resize config dictionary
    """
    wm_pos = st.session_state.get('wm_pos_key', 'bottom-right')
    
    return {
        'enabled': st.session_state.get('resize_enabled', True),
        'mode': st.session_state.get('resize_mode', 'Max Side'),
        'value': st.session_state.get('resize_val_state', 1920),
        'wm_scale': st.session_state.get('wm_scale_key', 15) / 100,
        'wm_margin': st.session_state.get('wm_margin_key', 15) if wm_pos != 'tiled' else 0,
        'wm_gap': st.session_state.get('wm_gap_key', 30) if wm_pos == 'tiled' else 0,
        'wm_position': wm_pos,
        'wm_angle': st.session_state.get('wm_angle_key', 0)
    }

# === THREAD-SAFE STATE UPDATE ===
def safe_state_update(key: str, value):
    """Thread-safe session state update"""
    with _session_lock:
        st.session_state[key] = value
