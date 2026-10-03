import io
import pytest
import numpy as np
from PIL import Image, ImageDraw

from api.modules.specimen import (
    analyze_histology_patch,
    analyze_materials_patch,
    process_specimen_pipeline
)

def create_synthetic_specimen(mode: str = "histology") -> bytes:
    buf = io.BytesIO()
    if mode == "histology":
        img = Image.new("RGB", (200, 200), color=(240, 200, 215))  # Eosin pink
        draw = ImageDraw.Draw(img)
        # Draw 15 purple nuclei
        for i in range(15):
            x = 20 + (i % 4) * 45
            y = 20 + (i // 4) * 45
            draw.ellipse([x - 5, y - 5, x + 5, y + 5], fill=(60, 20, 90))
    else:
        # Materials: dark metal with bright crack line
        img = Image.new("RGB", (200, 200), color=(50, 50, 50))
        draw = ImageDraw.Draw(img)
        draw.line([30, 40, 170, 160], fill=(220, 220, 220), width=3)

    img.save(buf, format="PNG")
    return buf.getvalue()

def test_histology_patch_analysis():
    raw_bytes = create_synthetic_specimen("histology")
    arr = np.array(Image.open(io.BytesIO(raw_bytes)))

    findings, cal, stats = analyze_histology_patch(arr, um_per_px=0.5)

    assert stats["total_nuclei_count"] >= 5
    assert cal.kind == "slide"
    assert cal.axes["x"].unit == "um"

def test_materials_patch_analysis():
    raw_bytes = create_synthetic_specimen("materials")
    arr = np.array(Image.open(io.BytesIO(raw_bytes)))

    findings, cal, stats = analyze_materials_patch(arr, um_per_px=1.0)

    assert stats["crack_count"] >= 1
    assert stats["total_crack_length_um"] > 50.0

def test_specimen_pipeline_end_to_end():
    raw_bytes = create_synthetic_specimen("histology")
    findings, cal, norm_img, stats, prov = process_specimen_pipeline(raw_bytes, sub_mode="histology")

    assert len(findings) >= 1
    assert prov.pipeline_version == "1.0.0"
    assert findings[0].vision is not None
