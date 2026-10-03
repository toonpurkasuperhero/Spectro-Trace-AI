import io
import time
import numpy as np
import pytest
from fastapi.testclient import TestClient
from api.main import app
from api.core.exports import to_canvas, build_export_transform, PROFILES
from api.core.schema import JobResult, Finding, Calibration

client = TestClient(app)

def test_to_canvas_identical_resolution():
    # 1920x1080 into 1920x1080 -> scale = 1.0, offsets = 0
    box = (100, 200, 300, 150)
    cx, cy, cw, ch = to_canvas(box, (1920, 1080), (1920, 1080))
    assert (cx, cy, cw, ch) == (100, 200, 300, 150)

def test_to_canvas_square_into_16x9():
    # 1000x1000 src into 1920x1080 dst
    # s = min(1920/1000, 1080/1000) = 1.08
    # scaled w = 1080, scaled h = 1080
    # off_x = (1920 - 1080) / 2 = 420, off_y = 0
    box = (100, 200, 400, 300)
    cx, cy, cw, ch = to_canvas(box, (1000, 1000), (1920, 1080))

    expected_x = round(100 * 1.08 + 420)  # 108 + 420 = 528
    expected_y = round(200 * 1.08 + 0)    # 216
    expected_w = round(400 * 1.08)        # 432
    expected_h = round(300 * 1.08)        # 324

    assert (cx, cy, cw, ch) == (expected_x, expected_y, expected_w, expected_h)

def test_to_canvas_clamping():
    # Box exceeding canvas boundaries
    box = (900, 900, 500, 500)
    cx, cy, cw, ch = to_canvas(box, (1000, 1000), (1080, 1080))
    assert cx + cw <= 1080
    assert cy + ch <= 1080
    assert cx >= 0
    assert cy >= 0

def test_build_export_transform_fills_and_policy():
    job = JobResult(
        job_id="test_job_1",
        module="print",
        status="done",
        risk_level="high",
        risk_score=85,
        findings=[
            Finding(
                id="f1",
                label="crack",
                region_px=(50, 50, 100, 80),
                severity=0.8,
                risk_level="high"
            )
        ]
    )

    # Blur fill
    t_blur = build_export_transform(job, view="annotated", profile="slide_16x9", fill="blur", annotated=True)
    assert any("blurred" in str(step.get("background", "")) for step in t_blur)

    # Solid fill
    t_solid = build_export_transform(job, view="annotated", profile="slide_16x9", fill="solid", annotated=True)
    assert any("rgb:0b0f14" in str(step.get("background", "")) for step in t_solid)

    # Generative fill on print module is permitted
    t_gen = build_export_transform(job, view="annotated", profile="slide_16x9", fill="generative", annotated=True)
    assert any("gen_fill" in str(step.get("background", "")) for step in t_gen)
    # Check that in-image label overlay was added
    assert any("Background extended by AI" in str(step) for step in t_gen)

def test_build_export_transform_policy_denial():
    # Audio module must reject generative fill with PermissionError
    job_audio = JobResult(
        job_id="test_audio_job",
        module="audio",
        status="done"
    )

    with pytest.raises(PermissionError):
        build_export_transform(job_audio, view="annotated", profile="slide_16x9", fill="generative")

def test_get_job_exports_api_endpoint():
    """
    Tests export endpoint behaviour.
    When Cloudinary credentials are NOT configured (CI / local dev):
      - /jobs/run-local still succeeds (200) with local fallback views.
      - /jobs/{id}/exports returns 503 (Cloudinary required) — this is correct.
      - Invalid profile still returns 422.
    When Cloudinary IS configured (production):
      - /jobs/{id}/exports returns 200 with a signed Cloudinary URL.
    """
    from api.core.cloudinary_client import cloudinary_configured

    # 1. Run a local job first
    arr = np.full((60, 60), 22.0, dtype=np.float32)
    arr[20:35, 20:35] = 52.0  # +30 C leak
    buf = io.BytesIO()
    np.savetxt(buf, arr, delimiter=",", fmt="%.2f")
    csv_bytes = buf.getvalue()

    res_run = client.post(
        "/jobs/run-local",
        data={"module": "thermal"},
        files={"file": ("test_thermal.csv", csv_bytes, "text/csv")}
    )
    assert res_run.status_code == 200
    job_id = res_run.json()["job_id"]

    import time
    time.sleep(1.0)

    # 2. Invalid profile always returns 422
    res_inv = client.get(f"/jobs/{job_id}/exports?profile=invalid_aspect")
    assert res_inv.status_code == 422

    if cloudinary_configured():
        # Full Cloudinary path — expect signed URL and 200
        res_export = client.get(f"/jobs/{job_id}/exports?profile=slide_16x9&fill=blur&annotated=true")
        assert res_export.status_code == 200
        data = res_export.json()
        assert data["job_id"] == job_id
        assert data["profile"] == "slide_16x9"
        assert data["fill"] == "blur"
        assert "export_url" in data
        assert data["export_url"].startswith("http")
        assert data.get("cloudinary") is True

        res_mobile = client.get(f"/jobs/{job_id}/exports?profile=mobile_9x16&fill=solid")
        assert res_mobile.status_code == 200

        # Generative fill on thermal (radiometric) returns 403
        res_gen_blocked = client.get(f"/jobs/{job_id}/exports?profile=slide_16x9&fill=generative")
        assert res_gen_blocked.status_code == 403
    else:
        # No Cloudinary credentials — endpoint correctly returns 503
        res_no_cld = client.get(f"/jobs/{job_id}/exports?profile=slide_16x9&fill=blur")
        assert res_no_cld.status_code == 503
        assert "Cloudinary" in res_no_cld.json()["detail"]
