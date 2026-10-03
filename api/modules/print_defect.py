import io
import math
import numpy as np
import cv2
from PIL import Image
import matplotlib
matplotlib.use('Agg')
import matplotlib.cm as cm
from typing import Tuple, List, Dict, Any, Optional

from api.core.schema import Calibration, CalibrationAxis, ValueMap, Finding, Provenance, GenerativeStep
from api.core.calibration import pixel_to_physical
from api.core.vision import run_vision
from api.modules.registry import MODULES

def align_layers(actual: np.ndarray, golden: np.ndarray) -> np.ndarray:
    """
    Aligns actual layer image to golden reference using ORB feature matching.
    Falls back to unaligned actual if feature matching fails.
    """
    try:
        orb = cv2.ORB_create(nfeatures=500)
        kp1, des1 = orb.detectAndCompute(actual, None)
        kp2, des2 = orb.detectAndCompute(golden, None)

        if des1 is None or des2 is None or len(kp1) < 4 or len(kp2) < 4:
            return actual

        bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
        matches = bf.match(des1, des2)
        matches = sorted(matches, key=lambda x: x.distance)

        good_matches = matches[:min(50, len(matches))]
        if len(good_matches) < 4:
            return actual

        src_pts = np.float32([kp1[m.queryIdx].pt for m in good_matches]).reshape(-1, 1, 2)
        dst_pts = np.float32([kp2[m.trainIdx].pt for m in good_matches]).reshape(-1, 1, 2)

        H, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
        if H is None:
            return actual

        h, w = golden.shape[:2]
        aligned = cv2.warpPerspective(actual, H, (w, h))
        return aligned
    except Exception:
        return actual

def compute_deviation_heatmap(diff_mask: np.ndarray) -> Image.Image:
    """
    Generates transparent RGBA deviation-density heatmap (Gaussian-smoothed).
    This serves as the 'Deviation / Stress-Risk Map' overlay.
    """
    blurred = cv2.GaussianBlur(diff_mask.astype(np.float32), (31, 31), 0)
    norm = np.clip(blurred / max(float(np.max(blurred)), 1.0), 0.0, 1.0)

    # Use turbo or hot colormap
    rgba = cm.hot(norm)
    # Alpha proportional to density
    rgba[:, :, 3] = norm * 0.75
    img_data = (rgba * 255).astype(np.uint8)
    return Image.fromarray(img_data, mode="RGBA")

def detect_dark_cracks(gray: np.ndarray) -> np.ndarray:
    """
    Detects surface cracks as dark linear discontinuities on a bright background.
    Works on finished-part side-view images where cracks appear as dark lines/gaps.
    """
    # Adaptive threshold inverted — finds regions significantly darker than local neighbourhood
    adaptive = cv2.adaptiveThreshold(
        gray, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        blockSize=31,   # neighbourhood size
        C=12            # how much darker a pixel must be vs neighbourhood
    )

    # Also catch absolute dark regions (shadows, deep cracks)
    _, abs_dark = cv2.threshold(gray, 60, 255, cv2.THRESH_BINARY_INV)

    # Combine both signals
    combined = cv2.bitwise_or(adaptive, abs_dark)

    # Remove large flat-dark regions (backgrounds, borders) — keep only thin features
    kernel_open = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 1))
    kernel_close = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    cleaned = cv2.morphologyEx(combined, cv2.MORPH_CLOSE, kernel_close)
    cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_OPEN, kernel_open)

    return cleaned


def analyze_print_defects(
    actual_img: np.ndarray,
    golden_img: Optional[np.ndarray] = None,
    layer_index: int = 1,
    mm_per_px: float = 0.1
) -> Tuple[List[Finding], Calibration, Image.Image, Dict[str, Any]]:
    """
    Deterministic Print Defect & Deviation Analysis:
    1. Compares actual layer against golden reference (or edge model).
    2. Dark-crack detector for surface discontinuities on bright parts.
    3. Identifies connected defect components (area, aspect ratio, perimeter).
    4. Heuristics for stringing, voids, under-extrusion, cracks.
    5. Computes per-layer defect score and halt flag threshold.
    """
    h, w = actual_img.shape[:2]

    # Convert to grayscale
    gray_act = cv2.cvtColor(actual_img, cv2.COLOR_RGB2GRAY) if actual_img.ndim == 3 else actual_img

    if golden_img is not None:
        gray_gold = cv2.cvtColor(golden_img, cv2.COLOR_RGB2GRAY) if golden_img.ndim == 3 else golden_img
        if gray_gold.shape != gray_act.shape:
            gray_gold = cv2.resize(gray_gold, (w, h))
        aligned_act = align_layers(gray_act, gray_gold)
        diff = cv2.absdiff(aligned_act, gray_gold)
        _, thresh = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)
    else:
        # Path 1: Edge-based deviation (lower thresholds to catch subtle features)
        edges = cv2.Canny(gray_act, 20, 60)

        # Path 2: Dark-crack detection (surface cracks = dark discontinuities on bright surface)
        crack_mask = detect_dark_cracks(gray_act)

        # Combine — either edge deviations OR dark crack features
        thresh = cv2.bitwise_or(edges, crack_mask)

    # Use MORPH_CLOSE instead of MORPH_OPEN — close fills thin cracks rather than erasing them
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    cleaned = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)

    heatmap_img = compute_deviation_heatmap(cleaned)

    # Connected Components — lower min area to catch narrow crack fragments
    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(cleaned, connectivity=8)

    cal = Calibration(
        kind="layer",
        width_px=w,
        height_px=h,
        axes={
            "x": CalibrationAxis(unit="mm", min=0.0, max=round(float(w * mm_per_px), 2), scale="linear"),
            "y": CalibrationAxis(unit="mm", min=0.0, max=round(float(h * mm_per_px), 2), scale="linear")
        },
        value_map=ValueMap(unit="deviation_score", min=0.0, max=100.0, source="ssim_diff"),
        encoding={"layer_index": layer_index, "mm_per_px": mm_per_px},
        provenance={"pipeline": "orb_homography_diff_morphology_v2_crack_aware"}
    )

    findings: List[Finding] = []
    total_defect_area_px = 0

    for i in range(1, num_labels):
        area = int(stats[i, cv2.CC_STAT_AREA])
        if area < 6:   # lowered from 12 — crack fragments can be small
            continue

        rx = int(stats[i, cv2.CC_STAT_LEFT])
        ry = int(stats[i, cv2.CC_STAT_TOP])
        rw = int(stats[i, cv2.CC_STAT_WIDTH])
        rh = int(stats[i, cv2.CC_STAT_HEIGHT])

        total_defect_area_px += area

        aspect = max(rw, rh) / max(min(rw, rh), 1)
        area_mm2 = round(float(area * (mm_per_px ** 2)), 3)

        # Check if this component coincides with dark-crack mask pixels
        comp_mask = (labels == i).astype(np.uint8) * 255
        if golden_img is None:
            crack_region = detect_dark_cracks(gray_act)
            overlap = cv2.bitwise_and(comp_mask, crack_region)
            is_crack = bool(np.sum(overlap) > 0.3 * np.sum(comp_mask))
        else:
            is_crack = False

        if is_crack and aspect > 2.0:
            defect_type = "surface_crack"
            severity = 0.85
            risk_level = "high"
        elif aspect > 4.0:
            defect_type = "stringing"
            severity = 0.65
            risk_level = "medium"
        elif area > 350:
            defect_type = "under_extrusion_void"
            severity = 0.90
            risk_level = "high"
        else:
            defect_type = "surface_deviation"
            severity = 0.40
            risk_level = "low"

        phys = pixel_to_physical(cal, (rx, ry, rw, rh))

        f = Finding(
            id=f"print_{i}",
            label=defect_type,
            short_label=f"{defect_type[:12]}",
            region_px=(rx, ry, rw, rh),
            region_physical=phys,
            measurements={
                "area_px": area,
                "area_mm2": area_mm2,
                "aspect_ratio": round(float(aspect), 2),
                "layer_index": int(layer_index),
                "is_crack": is_crack,
            },
            source="cv",
            severity=severity,
            risk_level=risk_level
        )
        findings.append(f)

    findings.sort(key=lambda x: x.measurements.get("area_px", 0), reverse=True)

    defect_ratio = float(total_defect_area_px / max(w * h, 1))
    halt_flag = bool(defect_ratio > 0.04 or any(f.risk_level == "high" for f in findings))
    severity_score = min(100, int(defect_ratio * 1000) + len(findings) * 4)

    stats_summary = {
        "layer_index": int(layer_index),
        "total_anomalies": int(len(findings)),
        "total_defect_area_px": int(total_defect_area_px),
        "defect_area_ratio": round(defect_ratio, 5),
        "print_halt_recommended": halt_flag,
        "severity_score": int(severity_score)
    }

    return findings, cal, heatmap_img, stats_summary


def process_print_pipeline(
    actual_bytes: bytes,
    golden_bytes: Optional[bytes] = None,
    layer_index: int = 1,
    image_url_for_vision: str = ""
) -> Tuple[List[Finding], Calibration, Any, Image.Image, Dict[str, Any], Provenance]:
    """
    End-to-End Pipeline for Module A (3D Print Defect & Deviation Mapping).
    Returns: findings, calibration, original_img (np.ndarray RGB), heatmap_img (PIL RGBA),
             stats, provenance
    """
    actual_img = np.array(Image.open(io.BytesIO(actual_bytes)).convert("RGB"))
    golden_img = None
    if golden_bytes:
        golden_img = np.array(Image.open(io.BytesIO(golden_bytes)).convert("RGB"))

    findings, cal, heatmap_img, stats = analyze_print_defects(
        actual_img,
        golden_img,
        layer_index=layer_index
    )

    # Classify via Vision Provider
    prompt = MODULES["print"].vision_prompt
    findings = run_vision(image_url_for_vision, findings, prompt)

    provenance = Provenance(
        pipeline_version="1.0.0",
        deterministic_steps=["orb_alignment", "ssim_diff", "morphological_connected_components", "deviation_density_map"],
        generative_steps=[GenerativeStep(step="b_gen_fill", purpose="display only")],
        vision={"provider": "heuristic_fallback", "model": "rule_based_v1", "prompt_version": "print-v1"}
    )

    # Return the original image too so callers can composite it correctly
    return findings, cal, actual_img, heatmap_img, stats, provenance
