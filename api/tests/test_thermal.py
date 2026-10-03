import pytest
import numpy as np
from api.modules.thermal import (
    analyze_thermal_radiometry,
    render_standardized_ironbow,
    process_thermal_pipeline
)

def test_thermal_hotspot_detection_and_measurements():
    # Construct 100x100 matrix with ambient 20.0 C
    arr = np.full((100, 100), 20.0, dtype=np.float32)
    # Inject 45.0 C hotspot at (40..60, 40..60) -> Delta T = 25.0 C
    arr[40:60, 40:60] = 45.0

    findings, cal, stats = analyze_thermal_radiometry(
        arr,
        source_type="radiometric",
        ambient_ref_c=20.0,
        delta_t_threshold=8.0
    )

    assert len(findings) == 1
    f = findings[0]
    
    # Check physical measurements
    assert f.measurements["ambient_ref_c"] == 20.0
    assert f.measurements["max_temp_c"] == 45.0
    assert f.measurements["delta_t_c"] == 25.0
    assert f.risk_level == "high"
    assert f.measurements["area_px"] == 400

    # Check bounding box encompasses the 20x20 region
    x, y, w, h = f.region_px
    assert x <= 40 and y <= 40
    assert x + w >= 60 and y + h >= 60

def test_thermal_end_to_end_pipeline():
    arr = np.full((50, 50), 22.0, dtype=np.float32)
    arr[15:25, 15:25] = 48.0  # +26 C leak

    import io
    csv_buf = io.BytesIO()
    np.savetxt(csv_buf, arr, delimiter=",", fmt="%.2f")
    raw_csv = csv_buf.getvalue()

    findings, cal, render_img, stats, prov = process_thermal_pipeline(raw_csv, is_csv=True)

    assert len(findings) == 1
    assert render_img.size == (50, 50)
    assert prov.pipeline_version == "1.0.0"
    assert findings[0].vision is not None
    assert "leak" in findings[0].vision.classification.lower() or "thermal" in findings[0].vision.classification.lower()
