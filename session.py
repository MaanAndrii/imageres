"""
Watermarker Pro v8.0 - Session Module
======================================
Ініціалізація та управління Streamlit session state.
Виділено з utils.py для розподілу відповідальності.
"""

import streamlit as st
import tempfile
import threading

import config
from logger import get_logger

logger = get_logger(__name__)

_session_lock = threading.Lock()


def init_session_state():
    """Initialize session state with default values"""

    if 'temp_dir' not in st.session_state:
        try:
            st.session_state['temp_dir'] = tempfile.mkdtemp(prefix="wm_pro_v8_")
            logger.info(f"Temp directory created: {st.session_state['temp_dir']}")
        except Exception as e:
            logger.error(f"Failed to create temp dir: {e}")
            st.session_state['temp_dir'] = tempfile.gettempdir()

    defaults = {
        'file_cache': {},           # fname -> fpath
        'file_order': [],           # упорядкований список fname (drag-and-drop)
        'selected_files': set(),
        'uploader_key': 0,
        'lang_code': 'ua',
        'editing_file': None,
        'editor_open':  False,   # True тільки після натискання кнопки — запобігає
                                 # самовільному відкриттю при кожному rerun
        'close_editor': False,
        'results': None,
        'cancel_token': None,       # CancellationToken | None
        'processing_active': False, # True поки йде batch
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

    # Налаштування (ключі з config.DEFAULT_SETTINGS)
    for key, value in config.DEFAULT_SETTINGS.items():
        key_name = f'{key}_key' if not key.endswith('_val') else f'{key}_state'
        if key_name not in st.session_state:
            st.session_state[key_name] = value


def reset_settings():
    """Reset all settings to defaults"""
    try:
        for key, value in config.DEFAULT_SETTINGS.items():
            key_name = f'{key}_key' if not key.endswith('_val') else f'{key}_state'
            st.session_state[key_name] = value
        logger.info("Settings reset to defaults")
    except Exception as e:
        logger.error(f"Failed to reset settings: {e}")


def safe_state_update(key: str, value):
    """Thread-safe session state update"""
    with _session_lock:
        st.session_state[key] = value


def handle_pos_change():
    """Handle watermark position change with preset application"""
    try:
        position = st.session_state.get('wm_pos_key', 'bottom-right')
        settings = config.TILED_SETTINGS if position == 'tiled' else config.CORNER_SETTINGS
        for key, value in settings.items():
            st.session_state[f'{key}_key'] = value
        logger.debug(f"Position changed to: {position}")
    except Exception as e:
        logger.error(f"Failed to handle position change: {e}")
