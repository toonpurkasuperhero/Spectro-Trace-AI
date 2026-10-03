"""
SpectroTrace AI — Export Profiles & Canvas Geometry Engine (Feature C)
Handles aspect ratio conversions (16:9, 9:16, 1:1), canvas scaling math,
bounding-box coordinate remapping, presentation slide chrome, and
both Cloudinary URL transformations and offline local fallbacks.
"""

import io
import math
import base64
from typing import Tuple, List, Dict, Any, Optional
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from api.core.schema import Finding, JobResult
from api.core.gen_policy import policy_allows_genfill
from api.core.cloudinary_client import signed_url, cld_call
from api.core.config import settings

# Supported standard export aspect ratios and target pixel resolutions
PROFILES: Dict[str, Tuple[int, int]] = {
    "slide_16x9": (1920, 1080),   # Executive presentations & monitors
    "mobile_9x16": (1080, 1920),  # Field alerts & smartphone review
    "square_1x1": (1080, 1080),   # Reports, thumbnails, and chat
}

RISK_COLORS = {
    "high": {"cld": "red", "rgb": (239, 68, 68), "hex": "#ef4444"},
    "medium": {"cld": "orange", "rgb": (245, 158, 11), "hex": "#f59e0b"},
    "low": {"cld": "yellow", "rgb": (16, 185, 129), "hex": "#10b981"},
}

def to_canvas(
    box: Tuple[int, int, int, int],
    src: Tuple[int, int],
    dst: Tuple[int, int]
) -> Tuple[int, int, int, int]:
    """
    Transforms bounding box coordinates [x, y, w, h] from original image dimensions
    into the fitted and centered destination canvas coordinates (Section 6.3).
    
    Formula:
      s = min(dw / sw, dh / sh)
      off_x = (dw - sw * s) / 2
      off_y = (dh - sh * s) / 2
      new_x = round(x * s + off_x)
      new_y = round(y * s + off_y)
      new_w = round(w * s)
      new_h = round(h * s)
    """
    sw, sh = max(1, src[0]), max(1, src[1])
    dw, dh = max(1, dst[0]), max(1, dst[1])

    s = min(dw / sw, dh / sh)
    off_x = (dw - sw * s) / 2.0
    off_y = (dh - sh * s) / 2.0

    x, y, w, h = box
    cx = round(x * s + off_x)
    cy = round(y * s + off_y)
    cw = round(w * s)
    ch = round(h * s)

    # Clamp coordinates inside canvas
    cx = max(0, min(cx, dw - 1))
    cy = max(0, min(cy, dh - 1))
    cw = max(1, min(cw, dw - cx))
    ch = max(1, min(ch, dh - cy))

    return (cx, cy, cw, ch)


def annotation_layers_on_canvas(
    findings: List[Finding],
    src_size: Tuple[int, int],
    dst_size: Tuple[int, int],
    overlay_asset: str = "sys:pixel",
    opacity: int = 40
) -> List[Dict[str, Any]]:
    """
    Builds Cloudinary transformation layers for bounding boxes mapped to the padded canvas.
    Overlays are applied strictly AFTER padding to prevent generative smudging.
    """
    transforms: List[Dict[str, Any]] = []

    for f in findings:
        cx, cy, cw, ch = to_canvas(f.region_px, src_size, dst_size)
        color = RISK_COLORS.get(f.risk_level, {}).get("cld", "yellow")

        # 1. Scaled rectangle layer
        transforms.extend([
            {
                "overlay": overlay_asset,
                "width": cw,
                "height": ch,
                "crop": "scale",
                "effect": "colorize:100",
                "color": color,
                "opacity": opacity
            },
            {
                "flags": "layer_apply",
                "gravity": "north_west",
                "x": cx,
                "y": cy
            }
        ])

        # 2. Text label badge
        label_text = f.short_label or f.label
        # URL sanitize text
        safe_text = label_text.replace(",", "%2C").replace("/", "%2F")
        transforms.extend([
            {
                "overlay": {
                    "font_family": "Arial",
                    "font_size": max(14, round(16 * min(dst_size) / 1080)),
                    "font_weight": "bold",
                    "text": safe_text
                },
                "color": "white",
                "background": "rgb:000000a0"
            },
            {
                "flags": "layer_apply",
                "gravity": "north_west",
                "x": cx,
                "y": max(0, cy - 24)
            }
        ])

    return transforms


def slide_chrome(
    job: JobResult,
    profile: str,
    dst_size: Tuple[int, int]
) -> List[Dict[str, Any]]:
    """
    Builds executive presentation chrome overlays (title, risk badge pill, KPI strip, footer).
    """
    transforms: List[Dict[str, Any]] = []
    dw, dh = dst_size

    module_name = job.module.replace("_", " ").title()
    risk_text = f"{job.risk_level.upper()} RISK ({job.risk_score})"
    risk_color = RISK_COLORS.get(job.risk_level, {}).get("cld", "green")

    if profile == "slide_16x9":
        # Header title
        transforms.extend([
            {
                "overlay": {
                    "font_family": "Arial",
                    "font_size": 24,
                    "font_weight": "bold",
                    "text": f"SpectroTrace AI • {module_name} Inspection"
                },
                "color": "white",
                "background": "rgb:0b0f14d0"
            },
            {"flags": "layer_apply", "gravity": "north_west", "x": 40, "y": 30}
        ])

        # Risk badge pill (top right)
        transforms.extend([
            {
                "overlay": {
                    "font_family": "Arial",
                    "font_size": 20,
                    "font_weight": "bold",
                    "text": f"  {risk_text}  "
                },
                "color": "white",
                "background": f"rgb:{'ef4444' if risk_color == 'red' else ('f59e0b' if risk_color == 'orange' else '10b981')}"
            },
            {"flags": "layer_apply", "gravity": "north_east", "x": 40, "y": 30}
        ])

        # Footer KPI strip
        footer_kpi = f"Findings: {len(job.findings)}   |   Status: {job.status.upper()}   |   Review: {job.review_state.upper()}"
        transforms.extend([
            {
                "overlay": {
                    "font_family": "Arial",
                    "font_size": 15,
                    "text": footer_kpi
                },
                "color": "rgb:94a3b8",
                "background": "rgb:0b0f14d0"
            },
            {"flags": "layer_apply", "gravity": "south_west", "x": 40, "y": 25}
        ])

    elif profile == "mobile_9x16":
        # Mobile top risk badge
        transforms.extend([
            {
                "overlay": {
                    "font_family": "Arial",
                    "font_size": 28,
                    "font_weight": "bold",
                    "text": f"  {risk_text}  "
                },
                "color": "white",
                "background": f"rgb:{'ef4444' if risk_color == 'red' else ('f59e0b' if risk_color == 'orange' else '10b981')}"
            },
            {"flags": "layer_apply", "gravity": "north", "y": 60}
        ])

        # Mobile bottom summary
        transforms.extend([
            {
                "overlay": {
                    "font_family": "Arial",
                    "font_size": 20,
                    "text": f"SpectroTrace • {module_name} • {len(job.findings)} anomalies"
                },
                "color": "white",
                "background": "rgb:0b0f14d0"
            },
            {"flags": "layer_apply", "gravity": "south", "y": 50}
        ])

    return transforms


def build_export_transform(
    job: JobResult,
    view: str,
    profile: str,
    fill: str = "blur",
    annotated: bool = True
) -> List[Dict[str, Any]]:
    """
    Constructs the complete transformation sequence for Cloudinary export.
    """
    if profile not in PROFILES:
        raise ValueError(f"Unknown export profile: '{profile}'. Must be one of {list(PROFILES.keys())}")

    W, H = PROFILES[profile]

    # Check policy for generative fill
    if fill == "generative":
        allowed, reason = policy_allows_genfill(job.module)
        if not allowed:
            raise PermissionError(f"Policy denied: {reason}")

    transforms: List[Dict[str, Any]] = []

    # 1. Base Canvas Padding with selected fill
    if fill == "generative":
        transforms.append({
            "crop": "pad",
            "width": W,
            "height": H,
            "gravity": "center",
            "background": "gen_fill"
        })
    elif fill == "solid":
        transforms.append({
            "crop": "pad",
            "width": W,
            "height": H,
            "gravity": "center",
            "background": "rgb:0b0f14"
        })
    else:  # blur (default)
        transforms.append({
            "crop": "pad",
            "width": W,
            "height": H,
            "gravity": "center",
            "background": "blurred:400:15"
        })

    # Source resolution
    src_w = 800
    src_h = 600
    if job.calibration:
        src_w = job.calibration.width_px or 800
        src_h = job.calibration.height_px or 600

    # 2. Annotation bounding boxes and labels
    if annotated and job.findings:
        transforms.extend(annotation_layers_on_canvas(job.findings, (src_w, src_h), (W, H)))

    # 3. In-image label if generative fill is used
    if fill == "generative":
        transforms.extend([
            {
                "overlay": {
                    "font_family": "Arial",
                    "font_size": 14,
                    "font_weight": "bold",
                    "text": "Background extended by AI (display only)"
                },
                "color": "white",
                "background": "rgb:3b0764e0"
            },
            {"flags": "layer_apply", "gravity": "south_east", "x": 30, "y": 30}
        ])

    # 4. Slide Chrome
    transforms.extend(slide_chrome(job, profile, (W, H)))

    return transforms


def export_url(
    job: JobResult,
    view: str = "raw",
    profile: str = "slide_16x9",
    fill: str = "blur",
    annotated: bool = True,
    base_public_id: Optional[str] = None
) -> str:
    """
    Returns signed delivery URL with export profile transformations applied.
    """
    if fill == "generative":
        cld_call("gen_fill", lambda: None)  # Guard budget and track daily usage

    transforms = build_export_transform(job, view, profile, fill=fill, annotated=annotated)

    pid = base_public_id or (job.assets.get("raw") or {}).get("public_id")
    if not pid:
        pid = f"spectrotrace/{job.module}/{job.job_id}"

    return signed_url(pid, transformation=transforms)


# -------------------------------------------------------------------------
# Offline / Local Export Generator (Pillow Fallback)
# -------------------------------------------------------------------------
def generate_local_export(
    job: JobResult,
    source_img_bytes: Optional[bytes] = None,
    source_b64: Optional[str] = None,
    profile: str = "slide_16x9",
    fill: str = "blur",
    annotated: bool = True
) -> str:
    """
    Generates presentation export locally using Pillow.
    Ensures testing and offline operation work seamlessly without internet or cloud keys.
    Returns a data:image/png;base64 URL.
    """
    if profile not in PROFILES:
        profile = "slide_16x9"

    W, H = PROFILES[profile]

    # Policy check for local generative fill attempt
    if fill == "generative":
        allowed, reason = policy_allows_genfill(job.module)
        if not allowed:
            raise PermissionError(f"Policy denied: {reason}")

    # Load source image
    base_img: Optional[Image.Image] = None
    if source_img_bytes:
        base_img = Image.open(io.BytesIO(source_img_bytes)).convert("RGB")
    elif source_b64 and "," in source_b64:
        raw_b64 = source_b64.split(",", 1)[1]
        base_img = Image.open(io.BytesIO(base64.b64decode(raw_b64))).convert("RGB")
    else:
        # Fallback dark placeholder canvas
        base_img = Image.new("RGB", (800, 600), color=(15, 23, 42))

    sw, sh = base_img.size

    # Fit image preserving aspect ratio
    s = min(W / sw, H / sh)
    fw = max(1, round(sw * s))
    fh = max(1, round(sh * s))
    fitted_img = base_img.resize((fw, fh), Image.Resampling.LANCZOS)
    off_x = (W - fw) // 2
    off_y = (H - fh) // 2

    # Background canvas
    if fill == "solid":
        canvas = Image.new("RGB", (W, H), color=(11, 15, 20))
    elif fill == "generative":
        # Local simulation of extended background with a deep ambient glow
        canvas = base_img.resize((W, H), Image.Resampling.BILINEAR).filter(ImageFilter.GaussianBlur(radius=30))
    else:  # blur (default)
        canvas = base_img.resize((W, H), Image.Resampling.BILINEAR).filter(ImageFilter.GaussianBlur(radius=50))

    # Paste fitted image onto canvas
    canvas.paste(fitted_img, (off_x, off_y))
    draw = ImageDraw.Draw(canvas, "RGBA")

    # Render bounding box annotations
    if annotated and job.findings:
        for f in job.findings:
            cx, cy, cw, ch = to_canvas(f.region_px, (sw, sh), (W, H))
            color_info = RISK_COLORS.get(f.risk_level, RISK_COLORS["low"])
            rgb = color_info["rgb"]

            # Translucent box
            draw.rectangle([cx, cy, cx + cw, cy + ch], fill=(*rgb, 60), outline=(*rgb, 220), width=3)

            # Label badge
            label_text = f.short_label or f.label
            badge_w = max(70, len(label_text) * 9 + 12)
            badge_h = 24
            by = max(0, cy - badge_h)
            draw.rounded_rectangle([cx, by, cx + badge_w, by + badge_h], radius=4, fill=(11, 15, 20, 220))
            draw.text((cx + 6, by + 4), label_text, fill=(255, 255, 255, 255))

    # Render presentation chrome
    risk_color = RISK_COLORS.get(job.risk_level, RISK_COLORS["low"])["rgb"]
    risk_label = f" {job.risk_level.upper()} RISK ({job.risk_score}) "

    if profile == "slide_16x9":
        # Header background banner
        draw.rectangle([0, 0, W, 80], fill=(11, 15, 20, 200))
        module_name = job.module.replace("_", " ").title()
        draw.text((40, 26), f"SpectroTrace AI  •  {module_name} Inspection", fill=(255, 255, 255, 255))

        # Risk badge
        draw.rounded_rectangle([W - 240, 22, W - 40, 58], radius=6, fill=(*risk_color, 240))
        draw.text((W - 225, 28), risk_label, fill=(255, 255, 255, 255))

        # Footer strip
        draw.rectangle([0, H - 60, W, H], fill=(11, 15, 20, 200))
        kpi_str = f"Findings: {len(job.findings)}    |    Status: {job.status.upper()}    |    Review State: {job.review_state.upper()}"
        draw.text((40, H - 42), kpi_str, fill=(148, 163, 184, 255))
        draw.text((W - 320, H - 42), f"Run ID: {job.job_id[:18]}", fill=(148, 163, 184, 255))

    elif profile == "mobile_9x16":
        # Mobile top risk badge
        draw.rounded_rectangle([W // 2 - 160, 50, W // 2 + 160, 110], radius=8, fill=(*risk_color, 240))
        draw.text((W // 2 - 120, 68), risk_label, fill=(255, 255, 255, 255))

        # Mobile bottom footer
        draw.rectangle([0, H - 100, W, H], fill=(11, 15, 20, 220))
        draw.text((W // 2 - 180, H - 65), f"SpectroTrace • {len(job.findings)} anomalies detected", fill=(255, 255, 255, 255))

    # In-image label if generative fill was selected
    if fill == "generative":
        lbl = "Background extended by AI (display only)"
        draw.rounded_rectangle([W - 380, H - 110, W - 30, H - 75], radius=6, fill=(59, 7, 100, 220))
        draw.text((W - 365, H - 98), lbl, fill=(216, 180, 254, 255))

    buf = io.BytesIO()
    canvas.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
