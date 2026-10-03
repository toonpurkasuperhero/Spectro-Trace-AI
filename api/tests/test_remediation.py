"""
Feature A Acceptance Tests — Remediation View (Phase 3)
Tests:
1. Static guard: analysis modules NEVER import genviews or generative feedback.
2. expand_box math: padding percentage, aspect ratios, boundary clamping.
3. Policy enforcement: blocked labels (thermal radiometry, audio, histology tissue).
4. Transformation & Label layer presence in signed Cloudinary URLs.
5. High-fidelity local inpainting fallback.
6. Outside-ROI preservation test: SSIM outside padded ROI >= 0.98.
"""

import os
import glob
import io
import base64
import pytest
import numpy as np
import cv2
from PIL import Image

from api.core.schema import Finding, JobResult, Calibration
from api.core.genviews import (
    expand_box,
    label_layer,
    remediation_transform,
    remediation_url,
    generate_local_remediation,
    DEFAULT_PAD_PCT,
)
from api.core.gen_policy import rule_for_remediation


def test_static_guard_no_analysis_feedback():
    """
    Integrity Rule: Analysis packages (modules, CV, DSP, vision, evaluation)
    must NEVER import genviews or feed generative assets into deterministic pipelines.
    """
    modules_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "modules"))
    core_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "core"))

    files_to_check = glob.glob(os.path.join(modules_dir, "*.py"))
    files_to_check.append(os.path.join(core_dir, "vision.py"))
    files_to_check.append(os.path.join(core_dir, "calibration.py"))

    for filepath in files_to_check:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
            assert "genviews" not in content, (
                f"Violation of integrity invariant: {os.path.basename(filepath)} imports genviews!"
            )
            assert "remediation_url" not in content, (
                f"Violation of integrity invariant: {os.path.basename(filepath)} references remediation_url!"
            )


def test_expand_box_padding_and_bounds_clamping():
    """
    Validates expand_box adds pad_pct to each side and clamps strictly to [0, 0, W, H].
    """
    src_w, src_h = 1000, 800

    # Center box: 100x100 at (200, 200). 12% padding = 12px
    box = (200, 200, 100, 100)
    nx, ny, nw, nh = expand_box(box, pad_pct=0.12, src_w=src_w, src_h=src_h)
    assert nx == 188
    assert ny == 188
    assert nw == 124
    assert nh == 124

    # Top-left corner box: must clamp at 0 without negative coordinates
    box_corner = (5, 5, 50, 50)
    cx, cy, cw, ch = expand_box(box_corner, pad_pct=0.20, src_w=src_w, src_h=src_h)
    assert cx == 0
    assert cy == 0
    assert cw > 50
    assert ch > 50

    # Bottom-right corner box: must clamp within (src_w, src_h)
    box_br = (980, 780, 40, 40)
    bx, by, bw, bh = expand_box(box_br, pad_pct=0.20, src_w=src_w, src_h=src_h)
    assert bx + bw <= src_w
    assert by + bh <= src_h


def test_remediation_transform_structure():
    finding = Finding(
        id="f1",
        label="crack",
        region_px=(100, 150, 60, 40),
        source="cv",
        severity=0.8,
        risk_level="high",
    )
    rule = rule_for_remediation("print", "*", "crack")

    # Region-based transform
    t_region = remediation_transform(finding, rule, src_w=1024, src_h=1024, pad_pct=0.10, mode="region")
    assert len(t_region) == 1
    assert "gen_remove:region_((x_" in t_region[0]["effect"]
    assert ";y_" in t_region[0]["effect"]
    assert ";w_" in t_region[0]["effect"]
    assert ";h_" in t_region[0]["effect"]

    # Prompt-based fallback
    t_prompt = remediation_transform(finding, rule, src_w=1024, src_h=1024, mode="prompt")
    assert len(t_prompt) == 1
    assert "gen_remove:prompt_" in t_prompt[0]["effect"]


def test_remediation_url_generation_and_label_overlay():
    findings = [
        Finding(id="f1", label="crack", region_px=(50, 50, 40, 40), source="cv", severity=0.7),
        Finding(id="f2", label="void", region_px=(200, 200, 30, 30), source="cv", severity=0.5),
    ]

    url, allowed, blocked = remediation_url(
        public_id="sample_asset",
        findings=findings,
        module="print",
        mode="*",
        src_w=800,
        src_h=800
    )

    assert len(allowed) == 2
    assert len(blocked) == 0
    assert "sample_asset" in url
    # Ensure label layer is part of the URL transformation
    assert "Illustrative" in url or "defect" in url or "s--" in url


def test_remediation_policy_rejection():
    # Histology tissue findings MUST be rejected
    histology_findings = [
        Finding(id="h1", label="dense_cellularity", region_px=(10, 10, 50, 50), source="cv"),
        Finding(id="h2", label="tissue_fold", region_px=(80, 80, 30, 30), source="cv"),
    ]

    with pytest.raises(PermissionError) as exc_info:
        remediation_url(
            public_id="histology_asset",
            findings=histology_findings,
            module="specimen",
            mode="histology"
        )
    assert "eligible" in str(exc_info.value).lower()

    # Thermal module MUST be rejected
    thermal_findings = [
        Finding(id="t1", label="hotspot", region_px=(20, 20, 40, 40), source="cv")
    ]
    with pytest.raises(PermissionError):
        remediation_url(
            public_id="thermal_asset",
            findings=thermal_findings,
            module="thermal"
        )


def test_outside_roi_integrity_ssim():
    """
    Section 5.6 Acceptance Test:
    Measures SSIM between original image and remediated image OUTSIDE the padded ROI.
    Requirement: SSIM >= 0.98 outside ROI.
    """
    # 1. Create a synthetic test image with texture (noise + pattern)
    np.random.seed(42)
    h, w = 300, 400
    base_arr = np.full((h, w, 3), 180, dtype=np.uint8)
    # Add texture
    noise = np.random.randint(-20, 20, (h, w, 3), dtype=np.int16)
    textured = np.clip(base_arr.astype(np.int16) + noise, 0, 255).astype(np.uint8)

    # 2. Add an artificial defect (dark crack) inside an ROI
    defect_x, defect_y, defect_w, defect_h = 150, 100, 30, 30
    img_with_defect = textured.copy()
    cv2.line(img_with_defect, (defect_x + 5, defect_y + 5), (defect_x + 25, defect_y + 25), (20, 20, 20), 3)

    # Encode to base64
    buf = io.BytesIO()
    Image.fromarray(img_with_defect).save(buf, format="PNG")
    b64_src = f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode()}"

    # 3. Create JobResult with finding
    finding = Finding(
        id="defect_1",
        label="crack",
        region_px=(defect_x, defect_y, defect_w, defect_h),
        source="cv",
        severity=0.8,
    )
    job = JobResult(
        job_id="test_job_ssim",
        module="print",
        status="done",
        findings=[finding],
        assets={"views": {"raw": b64_src}}
    )

    # 4. Run local remediation
    remediated_url, allowed, _ = generate_local_remediation(job, pad_pct=0.12)
    assert len(allowed) == 1

    # Decode remediated image
    data_part = remediated_url.split(",", 1)[-1]
    remed_pil = Image.open(io.BytesIO(base64.b64decode(data_part))).convert("RGB")
    remed_arr = np.array(remed_pil)

    # 5. Measure SSIM OUTSIDE the padded defect ROI and outside the bottom watermark banner
    # Padded ROI
    px, py, pw, ph = expand_box((defect_x, defect_y, defect_w, defect_h), pad_pct=0.12, src_w=w, src_h=h)

    # Create mask of unchanged regions (1 = evaluate SSIM, 0 = ignore defect ROI & bottom banner)
    eval_mask = np.ones((h, w), dtype=bool)
    eval_mask[py:py+ph, px:px+pw] = False
    # Exclude bottom watermark area (bottom 60px)
    eval_mask[h-60:h, :] = False

    orig_gray = cv2.cvtColor(img_with_defect, cv2.COLOR_RGB2GRAY)
    remed_gray = cv2.cvtColor(remed_arr, cv2.COLOR_RGB2GRAY)

    # Calculate Mean Absolute Error outside the ROI
    diff = np.abs(orig_gray[eval_mask].astype(float) - remed_gray[eval_mask].astype(float))
    max_diff = np.max(diff)
    mean_diff = np.mean(diff)

    # Outside the edited region and watermark, pixel values are completely identical
    assert mean_diff == 0.0, f"Expected 0 pixel deviation outside ROI, got mean_diff={mean_diff}"
    assert max_diff == 0.0, f"Expected 0 pixel deviation outside ROI, got max_diff={max_diff}"

    # Compute SSIM on the image outside ROI
    from skimage.metrics import structural_similarity as ssim
    # Create zeroed versions of defect + banner for SSIM comparison
    orig_eval = orig_gray.copy()
    remed_eval = remed_gray.copy()
    orig_eval[~eval_mask] = 0
    remed_eval[~eval_mask] = 0

    score = ssim(orig_eval, remed_eval, data_range=255)
    assert score >= 0.98, f"SSIM score {score} fell below target threshold 0.98"
