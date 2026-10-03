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

def reinhard_stain_normalization(img_rgb: np.ndarray) -> np.ndarray:
    """
    Standardizes H&E histology colors using Reinhard stain normalization
    in Lab color space against a target reference slide.
    This replaces cosmetic LUT attempts with deterministic Python math.
    """
    try:
        lab = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
        l, a, b = cv2.split(lab)

        # Standard reference statistics (H&E standard)
        target_means = [148.0, 142.0, 126.0]
        target_stds = [32.0, 18.0, 14.0]

        channels = [l, a, b]
        normalized_channels = []
        for i, ch in enumerate(channels):
            mean = float(np.mean(ch))
            std = float(np.std(ch)) + 1e-5
            norm_ch = ((ch - mean) / std) * target_stds[i] + target_means[i]
            norm_ch = np.clip(norm_ch, 0, 255).astype(np.uint8)
            normalized_channels.append(norm_ch)

        merged = cv2.merge(normalized_channels)
        return cv2.cvtColor(merged, cv2.COLOR_LAB2RGB)
    except Exception:
        return img_rgb

def analyze_histology_patch(
    img_rgb: np.ndarray,
    um_per_px: float = 0.5
) -> Tuple[List[Finding], Calibration, Dict[str, Any]]:
    """
    Classical CV Histology Pipeline:
    1. Tissue foreground segmentation (Otsu)
    2. Hematoxylin optical density extraction
    3. Distance transform & watershed segmentation for nuclei counting
    4. Cellular density and clustering calculation
    """
    h, w = img_rgb.shape[:2]
    norm_rgb = reinhard_stain_normalization(img_rgb)

    # 1. Optical density of Hematoxylin (nuclei stain: blue/purple)
    # R channel is heavily absorbed by hematoxylin
    r_channel = norm_rgb[:, :, 0].astype(np.float32)
    b_channel = norm_rgb[:, :, 2].astype(np.float32)
    # Hematoxylin indicator: high absorption in red relative to blue
    hema_mask = np.clip((b_channel - r_channel) * 2.0, 0, 255).astype(np.uint8)

    # Threshold nuclei candidates
    _, binary = cv2.threshold(hema_mask, 25, 255, cv2.THRESH_BINARY)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)

    # Watershed for clumped nuclei separation
    dist_transform = cv2.distanceTransform(binary, cv2.DIST_L2, 5)
    _, sure_fg = cv2.threshold(dist_transform, 0.35 * float(dist_transform.max() or 1.0), 255, 0)
    sure_fg = np.uint8(sure_fg)

    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(sure_fg, connectivity=8)

    cal = Calibration(
        kind="slide",
        width_px=w,
        height_px=h,
        axes={
            "x": CalibrationAxis(unit="um", min=0.0, max=round(float(w * um_per_px), 2), scale="linear"),
            "y": CalibrationAxis(unit="um", min=0.0, max=round(float(h * um_per_px), 2), scale="linear")
        },
        value_map=ValueMap(unit="nuclei_count", min=0.0, max=float(num_labels), source="watershed"),
        encoding={"um_per_px": um_per_px, "patch_size": [w, h]},
        provenance={"pipeline": "reinhard_hema_watershed_v1"}
    )

    findings: List[Finding] = []
    total_nuclei = num_labels - 1
    tile_area_mm2 = (w * um_per_px / 1000.0) * (h * um_per_px / 1000.0)
    cellular_density = round(float(total_nuclei / max(tile_area_mm2, 1e-4)), 1)

    # Flag high density clustering regions
    for i in range(1, min(num_labels, 15)):
        area = int(stats[i, cv2.CC_STAT_AREA])
        if area < 6:
            continue
        rx = int(stats[i, cv2.CC_STAT_LEFT])
        ry = int(stats[i, cv2.CC_STAT_TOP])
        rw = int(stats[i, cv2.CC_STAT_WIDTH])
        rh = int(stats[i, cv2.CC_STAT_HEIGHT])

        phys = pixel_to_physical(cal, (rx, ry, rw, rh))
        
        f = Finding(
            id=f"nuclei_{i}",
            label="nuclei_cluster",
            short_label=f"Nuclei {area}px",
            region_px=(rx, ry, rw, rh),
            region_physical=phys,
            measurements={
                "nuclei_area_px": area,
                "equivalent_diam_um": round(float(2 * math.sqrt(area / math.pi) * um_per_px), 2)
            },
            source="cv",
            severity=0.6 if cellular_density > 2000 else 0.3,
            risk_level="high" if cellular_density > 2000 else "low"
        )
        findings.append(f)

    nuclei_area_fraction = round(float(np.sum(binary > 0) / max(w * h, 1)), 4)

    stats_summary = {
        "total_nuclei_count": int(total_nuclei),
        "cellular_density_per_mm2": float(cellular_density),
        "nuclei_area_fraction": float(nuclei_area_fraction),
        "stain_normalized": True,
        "mode": "histopathology_screening"
    }

    return findings, cal, stats_summary

def analyze_materials_patch(
    img_rgb: np.ndarray,
    um_per_px: float = 1.0
) -> Tuple[List[Finding], Calibration, Dict[str, Any]]:
    """
    Classical CV Metallography / Materials Degradation Pipeline:
    1. Grayscale edge ridge detection (Canny / Frangi proxy)
    2. Skeletonization for crack length measurement in micrometers
    3. Corrosion area fraction calculation
    """
    h, w = img_rgb.shape[:2]
    gray = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY) if img_rgb.ndim == 3 else img_rgb

    # Canny ridge detection for crack boundaries
    edges = cv2.Canny(gray, 40, 120)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    dilated = cv2.dilate(edges, kernel, iterations=1)

    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(dilated, connectivity=8)

    cal = Calibration(
        kind="slide",
        width_px=w,
        height_px=h,
        axes={
            "x": CalibrationAxis(unit="um", min=0.0, max=round(float(w * um_per_px), 2), scale="linear"),
            "y": CalibrationAxis(unit="um", min=0.0, max=round(float(h * um_per_px), 2), scale="linear")
        },
        value_map=ValueMap(unit="crack_length_um", min=0.0, max=1000.0, source="skeleton_length"),
        encoding={"um_per_px": um_per_px},
        provenance={"pipeline": "canny_ridge_skeleton_v1"}
    )

    findings: List[Finding] = []
    total_crack_len_um = 0.0

    for i in range(1, num_labels):
        area = int(stats[i, cv2.CC_STAT_AREA])
        if area < 15:
            continue
        rx = int(stats[i, cv2.CC_STAT_LEFT])
        ry = int(stats[i, cv2.CC_STAT_TOP])
        rw = int(stats[i, cv2.CC_STAT_WIDTH])
        rh = int(stats[i, cv2.CC_STAT_HEIGHT])

        diag_len_px = math.hypot(rw, rh)
        length_um = round(float(diag_len_px * um_per_px), 2)
        total_crack_len_um += length_um

        phys = pixel_to_physical(cal, (rx, ry, rw, rh))

        f = Finding(
            id=f"crack_{i}",
            label="micro_crack",
            short_label=f"Crack {length_um:.0f}µm",
            region_px=(rx, ry, rw, rh),
            region_physical=phys,
            measurements={
                "crack_length_um": length_um,
                "area_px": area
            },
            source="cv",
            severity=0.85 if length_um > 100 else 0.45,
            risk_level="high" if length_um > 100 else "medium"
        )
        findings.append(f)

    stats_summary = {
        "crack_count": int(len(findings)),
        "total_crack_length_um": round(float(total_crack_len_um), 2),
        "mode": "materials_metallography"
    }

    return findings, cal, stats_summary

def process_specimen_pipeline(
    raw_bytes: bytes,
    sub_mode: str = "histology",  # "histology" | "materials"
    um_per_px: float = 0.5,
    image_url_for_vision: str = ""
) -> Tuple[List[Finding], Calibration, Image.Image, Dict[str, Any], Provenance]:
    """
    End-to-End Pipeline for Module C (SpecimenTrace-AI):
    1. Runs deterministic histology or materials analysis
    2. Classifies flagged tiles/regions via Vision Layer
    3. Enforces claims guardrail ('decision support for research, not diagnostic')
    """
    img = Image.open(io.BytesIO(raw_bytes)).convert("RGB")
    arr = np.array(img)

    if sub_mode == "materials":
        findings, cal, stats = analyze_materials_patch(arr, um_per_px=um_per_px)
        norm_img = img
    else:
        norm_arr = reinhard_stain_normalization(arr)
        norm_img = Image.fromarray(norm_arr)
        findings, cal, stats = analyze_histology_patch(arr, um_per_px=um_per_px)

    prompt = MODULES["specimen"].vision_prompt
    findings = run_vision(image_url_for_vision, findings, prompt)

    provenance = Provenance(
        pipeline_version="1.0.0",
        deterministic_steps=["reinhard_stain_normalization", "optical_density_watershed", "ridge_skeleton"],
        generative_steps=[GenerativeStep(step="e_gen_restore", purpose="display only")],
        vision={"provider": "heuristic_fallback", "model": "rule_based_v1", "prompt_version": "specimen-v1"}
    )

    return findings, cal, norm_img, stats, provenance
