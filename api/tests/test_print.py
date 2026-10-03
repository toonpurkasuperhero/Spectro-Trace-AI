import io
import pytest
import numpy as np
from PIL import Image, ImageDraw

from api.modules.print_defect import (
    analyze_print_defects,
    process_print_pipeline
)

def create_synthetic_layers():
    # Golden reference layer
    golden = Image.new("RGB", (200, 200), color=(30, 30, 30))
    draw_g = ImageDraw.Draw(golden)
    draw_g.rectangle([40, 40, 160, 160], outline=(200, 200, 200), width=6)

    # Defective layer with stringing (aspect ratio > 4) and void defect
    actual = golden.copy()
    draw_a = ImageDraw.Draw(actual)
    # Long thin stringing defect
    draw_a.line([50, 60, 150, 70], fill=(180, 180, 180), width=2)
    # Void defect
    draw_a.rectangle([80, 80, 110, 110], fill=(240, 240, 240))

    buf_g = io.BytesIO()
    golden.save(buf_g, format="PNG")
    buf_a = io.BytesIO()
    actual.save(buf_a, format="PNG")

    return buf_a.getvalue(), buf_g.getvalue()

def test_print_defect_detection_and_measurements():
    actual_bytes, golden_bytes = create_synthetic_layers()
    actual_img = np.array(Image.open(io.BytesIO(actual_bytes)))
    golden_img = np.array(Image.open(io.BytesIO(golden_bytes)))

    findings, cal, heatmap, stats = analyze_print_defects(
        actual_img,
        golden_img,
        layer_index=42,
        mm_per_px=0.1
    )

    assert len(findings) >= 1
    assert stats["layer_index"] == 42
    assert cal.kind == "layer"
    assert heatmap.size == (200, 200)

    # Check for stringing or void finding
    labels = [f.label for f in findings]
    assert any("stringing" in l or "void" in l or "deviation" in l for l in labels)

def test_print_pipeline_end_to_end():
    actual_bytes, golden_bytes = create_synthetic_layers()
    findings, cal, actual_img, heatmap, stats, prov = process_print_pipeline(actual_bytes, golden_bytes, layer_index=15)

    assert len(findings) >= 1
    assert prov.pipeline_version == "1.0.0"
    assert findings[0].vision is not None
    assert "area_mm2" in findings[0].measurements
