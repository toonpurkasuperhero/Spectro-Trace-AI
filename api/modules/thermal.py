import io
import math
import numpy as np
from PIL import Image
import matplotlib
matplotlib.use('Agg')
import matplotlib.cm as cm
from typing import Tuple, List, Dict, Any, Optional

from api.core.schema import Calibration, CalibrationAxis, ValueMap, Finding, Provenance, GenerativeStep
from api.core.calibration import pixel_to_physical
from api.core.vision import run_vision
from api.modules.registry import MODULES

def extract_temperature_matrix(
    raw_data: bytes,
    is_csv: bool = False,
    approx_range: Optional[Tuple[float, float]] = None
) -> Tuple[np.ndarray, str]:
    """
    Extracts 2D temperature array in Celsius.
    Returns: (matrix, source_type) where source_type is "radiometric" or "approximate".
    """
    if is_csv:
        # Load CSV matrix
        text = raw_data.decode("utf-8")
        matrix = np.genfromtxt(io.StringIO(text), delimiter=",", dtype=np.float32)
        return matrix, "radiometric"

    # Otherwise load as image
    img = Image.open(io.BytesIO(raw_data)).convert("L")
    arr = np.array(img, dtype=np.float32)
    
    if approx_range:
        min_t, max_t = approx_range
        # Linearly map grayscale 0..255 to temperature range
        matrix = min_t + (arr / 255.0) * (max_t - min_t)
        return matrix, "approximate"
    else:
        # Default standard building inspection scale [0°C to 50°C] if unspecified
        matrix = 0.0 + (arr / 255.0) * 50.0
        return matrix, "approximate"

def render_standardized_ironbow(matrix: np.ndarray, vmin: float = 10.0, vmax: float = 80.0) -> Image.Image:
    """
    Deterministically renders standardized Ironbow (Inferno) colormap image.
    Fixed vmin/vmax ensures cross-image comparability.
    """
    norm = np.clip((matrix - vmin) / max(vmax - vmin, 1e-4), 0.0, 1.0)
    rgba = cm.inferno(norm)
    rgb = (rgba[:, :, :3] * 255).astype(np.uint8)
    return Image.fromarray(rgb)

def analyze_thermal_radiometry(
    matrix: np.ndarray,
    source_type: str = "radiometric",
    ambient_ref_c: Optional[float] = None,
    delta_t_threshold: float = 8.0,
    min_area_px: int = 15
) -> Tuple[List[Finding], Calibration, Dict[str, Any]]:
    """
    Classical CV & Radiometric Analysis:
    1. Computes ambient reference temperature
    2. Identifies thermal anomalies where delta T > threshold
    3. Segments connected components
    4. Computes physical metrics: max temp, mean temp, delta T, relative heat-loss index
    """
    h, w = matrix.shape

    # 1. Ambient reference
    ambient = float(np.median(matrix)) if ambient_ref_c is None else ambient_ref_c
    delta_matrix = matrix - ambient

    # 2. Binary mask of candidate leak/hotspot regions
    hotspot_mask = (delta_matrix >= delta_t_threshold).astype(np.uint8)

    # 3. Connected Components
    import cv2
    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(hotspot_mask, connectivity=8)

    # Build Calibration contract
    cal = Calibration(
        kind="thermal",
        width_px=w,
        height_px=h,
        axes={
            "x": CalibrationAxis(unit="px", min=0, max=w, scale="linear"),
            "y": CalibrationAxis(unit="px", min=0, max=h, scale="linear")
        },
        value_map=ValueMap(
            unit="°C",
            min=float(np.min(matrix)),
            max=float(np.max(matrix)),
            source=source_type
        ),
        provenance={"algorithm": "cv2_connected_components", "ambient_c": ambient}
    )

    findings: List[Finding] = []
    total_heat_loss_index = 0.0

    for i in range(1, num_labels):  # Skip background 0
        area = int(stats[i, cv2.CC_STAT_AREA])
        if area < min_area_px:
            continue

        rx = int(stats[i, cv2.CC_STAT_LEFT])
        ry = int(stats[i, cv2.CC_STAT_TOP])
        rw = int(stats[i, cv2.CC_STAT_WIDTH])
        rh = int(stats[i, cv2.CC_STAT_HEIGHT])

        region_slice = matrix[ry:ry + rh, rx:rx + rw]
        region_mask = (labels[ry:ry + rh, rx:rx + rw] == i)

        if not np.any(region_mask):
            continue

        max_t = float(np.max(region_slice[region_mask]))
        mean_t = float(np.mean(region_slice[region_mask]))
        delta_t = max_t - ambient

        # Relative Heat-Loss Index: f(Delta T, Area)
        # Scaled indicator of conductive/convective heat flow
        heat_loss_index = round(float((delta_t ** 1.25) * (area / 100.0)), 2)
        total_heat_loss_index += heat_loss_index

        # Risk level determination
        if delta_t >= 20.0 or heat_loss_index > 50.0:
            risk_level = "high"
            severity = 0.9
        elif delta_t >= 10.0 or heat_loss_index > 20.0:
            risk_level = "medium"
            severity = 0.6
        else:
            risk_level = "low"
            severity = 0.3

        short_label = f"ΔT +{delta_t:.1f}°C"

        f = Finding(
            id=f"therm_{i}",
            label="thermal_leak_candidate",
            short_label=short_label,
            region_px=(rx, ry, rw, rh),
            region_physical=pixel_to_physical(cal, (rx, ry, rw, rh)),
            measurements={
                "max_temp_c": round(max_t, 2),
                "mean_temp_c": round(mean_t, 2),
                "delta_t_c": round(delta_t, 2),
                "ambient_ref_c": round(ambient, 2),
                "area_px": area,
                "relative_heat_loss_index": heat_loss_index
            },
            source="cv",
            severity=severity,
            risk_level=risk_level
        )
        findings.append(f)

    # Sort findings by severity
    findings.sort(key=lambda x: x.measurements.get("delta_t_c", 0), reverse=True)

    summary_stats = {
        "ambient_c": round(ambient, 2),
        "min_temp_c": round(float(np.min(matrix)), 2),
        "max_temp_c": round(float(np.max(matrix)), 2),
        "total_anomalies": len(findings),
        "total_heat_loss_index": round(total_heat_loss_index, 2),
        "source": source_type
    }

    return findings, cal, summary_stats

def process_thermal_pipeline(
    raw_data: bytes,
    is_csv: bool = False,
    approx_range: Optional[Tuple[float, float]] = None,
    image_url_for_vision: str = ""
) -> Tuple[List[Finding], Calibration, Image.Image, Dict[str, Any], Provenance]:
    """
    End-to-End Pipeline for Module B:
    1. Deterministic extraction
    2. Standardized ironbow rendering
    3. Classical CV anomaly measurement
    4. Vision classification & physical explanation
    """
    matrix, source_type = extract_temperature_matrix(raw_data, is_csv=is_csv, approx_range=approx_range)
    render_img = render_standardized_ironbow(matrix)
    findings, cal, stats = analyze_thermal_radiometry(matrix, source_type=source_type)

    # Classify via Vision Layer
    prompt = MODULES["thermal"].vision_prompt
    findings = run_vision(image_url_for_vision, findings, prompt)

    # Build provenance
    provenance = Provenance(
        pipeline_version="1.0.0",
        deterministic_steps=["radiometric_extract", "standardized_ironbow_render", "connected_components_threshold"],
        generative_steps=[GenerativeStep(step="e_gen_remove", purpose="display only")],
        vision={"provider": "heuristic_fallback", "model": "rule_based_v1", "prompt_version": "thermal-v1"}
    )

    return findings, cal, render_img, stats, provenance
