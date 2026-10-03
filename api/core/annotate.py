from typing import List, Dict, Any, Optional
from api.core.schema import Finding, Calibration
from api.core.cloudinary_client import signed_url

COLOR_MAP = {
    "high": "red",
    "medium": "orange",
    "low": "yellow"
}

def build_annotation_transform(
    findings: List[Finding],
    cal: Optional[Calibration] = None,
    opacity: int = 40,
    overlay_asset: str = "sys:pixel"
) -> List[Dict[str, Any]]:
    """
    Builds Cloudinary URL transformation array to composite bounding box overlays
    and labels without server-side image re-rendering.
    """
    transforms = []
    
    max_w = cal.width_px if cal else 9999
    max_h = cal.height_px if cal else 9999

    for f in findings:
        x, y, w, h = f.region_px
        
        # Clamp within image bounds
        x = max(0, min(x, max_w - 1))
        y = max(0, min(y, max_h - 1))
        w = max(1, min(w, max_w - x))
        h = max(1, min(h, max_h - y))
        
        color = COLOR_MAP.get(f.risk_level, "yellow")

        # 1. Overlay rectangle (using colorized 1x1 sys:pixel asset scaled to w, h)
        transforms.extend([
            {
                "overlay": overlay_asset,
                "width": w,
                "height": h,
                "crop": "scale",
                "effect": "colorize:100",
                "color": color,
                "opacity": opacity
            },
            {
                "flags": "layer_apply",
                "gravity": "north_west",
                "x": x,
                "y": y
            }
        ])

        # 2. Text label with background pill
        label_text = f.short_label or f.label
        transforms.extend([
            {
                "overlay": {
                    "font_family": "Arial",
                    "font_size": 14,
                    "font_weight": "bold",
                    "text": label_text
                },
                "color": "white",
                "background": "rgb:000000a0"
            },
            {
                "flags": "layer_apply",
                "gravity": "north_west",
                "x": x,
                "y": max(y - 20, 0)
            }
        ])

    return transforms

def annotated_url(
    base_public_id: str,
    findings: List[Finding],
    cal: Optional[Calibration] = None,
    opacity: int = 40,
    overlay_asset: str = "sys:pixel"
) -> str:
    """
    Returns signed URL with all finding annotations layered dynamically.
    """
    transform = build_annotation_transform(findings, cal, opacity=opacity, overlay_asset=overlay_asset)
    return signed_url(base_public_id, transformation=transform)

def fused_url(
    base_public_id: str,
    overlay_public_id: str,
    opacity: int = 50
) -> str:
    """
    Generates URL for opacity-fused images (e.g., thermal render over visible photo).
    """
    # Cloudinary overlay syntax uses colon for folder separation
    cld_overlay_id = overlay_public_id.replace("/", ":")
    transform = [
        {"overlay": cld_overlay_id, "opacity": opacity},
        {"flags": "layer_apply", "gravity": "center"}
    ]
    return signed_url(base_public_id, transformation=transform)


def draw_annotated_pil(render_img, findings: List[Finding]) -> "Image.Image":
    """
    Draws bounding boxes and risk-colored labels onto a PIL Image copy.
    Returns a new PIL Image — the original is not modified.
    Used by build_all_views for the hybrid annotated view (local PIL → CLD upload).
    """
    from PIL import Image as PILImage, ImageDraw as PILDraw, ImageFont as PILFont
    import numpy as np

    # Accept numpy arrays or PIL Images
    if hasattr(render_img, 'mode'):
        img = render_img.convert("RGB")
    else:
        img = PILImage.fromarray(np.array(render_img)).convert("RGB")

    draw = PILDraw.Draw(img, "RGBA")

    RISK_COLORS = {
        "high":   (239, 68,  68,  200),   # red
        "medium": (245, 158, 11,  200),   # amber
        "low":    (34,  197, 94,  200),   # green
    }
    TEXT_BG   = (15,  23,  42,  210)      # dark navy
    TEXT_COL  = (244, 244, 245, 255)      # near-white

    try:
        font = PILFont.truetype("arial.ttf", 13)
    except Exception:
        font = PILFont.load_default()

    for f in findings:
        if not f.region_px or len(f.region_px) < 4:
            continue
        x, y, w, h = int(f.region_px[0]), int(f.region_px[1]), int(f.region_px[2]), int(f.region_px[3])
        color = RISK_COLORS.get(f.risk_level, RISK_COLORS["low"])

        # Semi-transparent fill
        draw.rectangle([x, y, x + w, y + h], outline=color[:3], width=2, fill=(*color[:3], 40))

        # Label pill
        label = (f.short_label or f.label or "finding")[:30]
        bbox = font.getbbox(label)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        lx, ly = x, max(0, y - th - 8)
        draw.rectangle([lx, ly, lx + tw + 10, ly + th + 6], fill=TEXT_BG)
        draw.text((lx + 5, ly + 3), label, fill=TEXT_COL, font=font)

    return img
