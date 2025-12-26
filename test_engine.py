"""
Watermarker Pro v7.0 - Unit Tests
==================================
Test suite for engine module
"""

import pytest
import os
import tempfile
from PIL import Image
import sys

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import watermarker_engine as engine
from validators import ValidationError, validate_image_file, sanitize_filename, validate_color_hex

# === FIXTURES ===

@pytest.fixture
def temp_image():
    """Create temporary test image"""
    img = Image.new('RGB', (800, 600), color='white')
    with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as f:
        img.save(f.name, 'JPEG')
        yield f.name
    os.unlink(f.name)

@pytest.fixture
def temp_watermark():
    """Create temporary watermark image"""
    img = Image.new('RGBA', (200, 100), color=(255, 0, 0, 128))
    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
        img.save(f.name, 'PNG')
        with open(f.name, 'rb') as fp:
            content = fp.read()
    os.unlink(f.name)
    return content

# === VALIDATION TESTS ===

def test_sanitize_filename():
    """Test filename sanitization"""
    assert sanitize_filename("test file.jpg") == "test_file.jpg"
    assert sanitize_filename("файл№1.jpg") == "файл1.jpg"
    assert sanitize_filename("a" * 300 + ".jpg") == "a" * 251 + ".jpg"
    assert sanitize_filename("") == "unnamed.jpg"
    assert sanitize_filename("../../../etc/passwd") == "etcpasswd"

def test_validate_color_hex():
    """Test color validation"""
    assert validate_color_hex("#FFFFFF") == (255, 255, 255)
    assert validate_color_hex("#000000") == (0, 0, 0)
    assert validate_color_hex("#FF5733") == (255, 87, 51)
    
    with pytest.raises(ValidationError):
        validate_color_hex("#FFF")
    
    with pytest.raises(ValidationError):
        validate_color_hex("FFFFFF")
    
    with pytest.raises(ValidationError):
        validate_color_hex("#GGGGGG")

def test_validate_image_file_nonexistent():
    """Test validation with non-existent file"""
    with pytest.raises(ValidationError, match="File not found"):
        validate_image_file("/nonexistent/file.jpg")

def test_validate_image_file_invalid_format():
    """Test validation with invalid format"""
    with tempfile.NamedTemporaryFile(suffix='.txt', delete=False) as f:
        f.write(b"not an image")
        f.flush()
        
        with pytest.raises(ValidationError, match="Unsupported format"):
            validate_image_file(f.name)
        
        os.unlink(f.name)

def test_validate_image_file_corrupted():
    """Test validation with corrupted image"""
    with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as f:
        f.write(b"corrupted image data")
        f.flush()
        
        with pytest.raises(ValidationError, match="Corrupted"):
            validate_image_file(f.name)
        
        os.unlink(f.name)

# === ENGINE TESTS ===

def test_generate_filename_sequence():
    """Test sequential filename generation"""
    result = engine.generate_filename(
        "/path/img.jpg",
        "Prefix + Sequence",
        "test",
        "jpg",
        5
    )
    assert result == "test_005.jpg"

def test_generate_filename_keep_original():
    """Test keep original filename mode"""
    result = engine.generate_filename(
        "/path/my_photo.jpg",
        "Keep Original",
        "watermarked",
        "jpg",
        1
    )
    assert result == "watermarked_my-photo.jpg"

def test_generate_filename_transliteration():
    """Test transliteration in filename"""
    result = engine.generate_filename(
        "/path/фото.jpg",
        "Keep Original",
        "",
        "jpg",
        1
    )
    # Should be transliterated
    assert "photo" in result or "foto" in result

def test_base64_encoding():
    """Test base64 encoding/decoding"""
    original = b"test image data"
    encoded = engine.image_to_base64(original)
    decoded = engine.base64_to_bytes(encoded)
    assert decoded == original

def test_load_watermark_from_bytes(temp_watermark):
    """Test watermark loading"""
    wm = engine.load_watermark_from_bytes(temp_watermark)
    assert wm.mode == 'RGBA'
    assert wm.width > 0
    assert wm.height > 0

def test_load_watermark_empty_bytes():
    """Test watermark loading with empty bytes"""
    with pytest.raises(ValueError, match="empty"):
        engine.load_watermark_from_bytes(b"")

def test_create_text_watermark():
    """Test text watermark creation"""
    wm = engine.create_text_watermark(
        "Test Text",
        None,
        50,
        "#FFFFFF"
    )
    assert wm is not None
    assert wm.mode == 'RGBA'
    assert wm.width > 0
    assert wm.height > 0

def test_create_text_watermark_empty():
    """Test text watermark with empty text"""
    wm = engine.create_text_watermark("", None, 50, "#FFFFFF")
    assert wm is None

def test_apply_opacity():
    """Test opacity application"""
    img = Image.new('RGBA', (100, 100), (255, 0, 0, 255))
    
    # Full opacity
    result = engine.apply_opacity(img, 1.0)
    assert result == img
    
    # Half opacity
    result = engine.apply_opacity(img, 0.5)
    alpha = result.split()[3]
    assert alpha.getextrema()[1] < 255

def test_thumbnail_generation(temp_image):
    """Test thumbnail generation"""
    thumb = engine.get_thumbnail(temp_image)
    assert thumb is not None
    assert os.path.exists(thumb)
    
    # Verify thumbnail is cached
    thumb2 = engine.get_thumbnail(temp_image)
    assert thumb == thumb2

def test_thumbnail_removal(temp_image):
    """Test thumbnail removal"""
    thumb = engine.get_thumbnail(temp_image)
    assert os.path.exists(thumb)
    
    result = engine.remove_thumbnail(temp_image)
    assert result is True
    assert not os.path.exists(thumb)

def test_process_image_basic(temp_image, temp_watermark):
    """Test basic image processing"""
    wm_obj = engine.load_watermark_from_bytes(temp_watermark)
    
    resize_config = {
        'enabled': False,
        'mode': 'Max Side',
        'value': 1920,
        'wm_scale': 0.15,
        'wm_margin': 15,
        'wm_gap': 30,
        'wm_position': 'bottom-right',
        'wm_angle': 0
    }
    
    result_bytes, stats = engine.process_image(
        temp_image,
        "output.jpg",
        wm_obj,
        resize_config,
        "JPEG",
        80
    )
    
    assert len(result_bytes) > 0
    assert stats['filename'] == "output.jpg"
    assert 'x' in stats['new_res']
    assert stats['new_size'] > 0

def test_process_image_with_resize(temp_image):
    """Test image processing with resize"""
    resize_config = {
        'enabled': True,
        'mode': 'Max Side',
        'value': 400,
        'wm_scale': 0.15,
        'wm_margin': 15,
        'wm_gap': 30,
        'wm_position': 'center',
        'wm_angle': 0
    }
    
    result_bytes, stats = engine.process_image(
        temp_image,
        "resized.jpg",
        None,
        resize_config,
        "JPEG",
        80
    )
    
    assert len(result_bytes) > 0
    # Check that image was actually resized
    img = Image.open(io.BytesIO(result_bytes))
    assert max(img.width, img.height) <= 400

def test_process_image_tiled_watermark(temp_image, temp_watermark):
    """Test tiled watermark application"""
    wm_obj = engine.load_watermark_from_bytes(temp_watermark)
    
    resize_config = {
        'enabled': False,
        'mode': 'Max Side',
        'value': 1920,
        'wm_scale': 0.1,
        'wm_margin': 0,
        'wm_gap': 50,
        'wm_position': 'tiled',
        'wm_angle': 45
    }
    
    result_bytes, stats = engine.process_image(
        temp_image,
        "tiled.jpg",
        wm_obj,
        resize_config,
        "JPEG",
        80
    )
    
    assert len(result_bytes) > 0

# === INTEGRATION TESTS ===

def test_full_workflow(temp_image, temp_watermark):
    """Test complete workflow"""
    # 1. Validate image
    validate_image_file(temp_image)
    
    # 2. Load watermark
    wm_obj = engine.load_watermark_from_bytes(temp_watermark)
    wm_obj = engine.apply_opacity(wm_obj, 0.7)
    
    # 3. Process image
    resize_config = {
        'enabled': True,
        'mode': 'Max Side',
        'value': 1200,
        'wm_scale': 0.2,
        'wm_margin': 20,
        'wm_gap': 30,
        'wm_position': 'bottom-right',
        'wm_angle': -15
    }
    
    result_bytes, stats = engine.process_image(
        temp_image,
        "final.jpg",
        wm_obj,
        resize_config,
        "JPEG",
        85
    )
    
    # 4. Verify output
    assert len(result_bytes) > 0
    img = Image.open(io.BytesIO(result_bytes))
    assert img.width > 0
    assert img.height > 0

# === PERFORMANCE TESTS ===

@pytest.mark.slow
def test_large_image_processing():
    """Test processing of large image"""
    # Create large image
    img = Image.new('RGB', (4000, 3000), color='blue')
    with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as f:
        img.save(f.name, 'JPEG')
        temp_path = f.name
    
    try:
        resize_config = {
            'enabled': True,
            'mode': 'Max Side',
            'value': 1920,
            'wm_scale': 0.15,
            'wm_margin': 15,
            'wm_gap': 30,
            'wm_position': 'center',
            'wm_angle': 0
        }
        
        result_bytes, stats = engine.process_image(
            temp_path,
            "large.jpg",
            None,
            resize_config,
            "JPEG",
            80
        )
        
        assert len(result_bytes) > 0
        result_img = Image.open(io.BytesIO(result_bytes))
        assert max(result_img.width, result_img.height) == 1920
    
    finally:
        os.unlink(temp_path)

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
