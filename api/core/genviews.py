"""
SpectroTrace AI — Generative Views Engine (Feature A: Remediation View)
Provides region-based generative defect removal (e_gen_remove), URL transformation builders,
in-image label overlays, readiness checking, and high-fidelity local inpainting fallbacks.

Design Principles:
- POLICY BEFORE PROMPT: Default deny, checked against central policy engine.
- INTEGRITY: Remediation views are labeled display aids; NEVER fed back into CV/DSP/analysis.
- OUTSIDE-ROI PRESERVATION: Edits are strictly confined to padded defect bounds.
"""

import io
import time
import base64
import logging
from typing import Tuple, List, Dict, Any, Optional
from PIL import Image, ImageDraw, ImageFont
import numpy as np
import cv2
import requests

from api.core.schema import Finding, JobResult
from api.core.gen_policy import (
    rule_for_remediation,
    GenRule,
    GENERATIVE_BANNER_TEXT,
    WATERMARK_TEXT,
)
from api.core.cloudinary_client import signed_url, guard_budget, cld_call
from api.core.config import settings

logger = logging.getLogger(__name__)

# Default padding percentage applied to bounding box (12%)
DEFAULT_PAD_PCT = 0.12


def expand_box(
    box: Tuple[int, int, int, int],
    pad_pct: float = DEFAULT_PAD_PCT,
    src_w: int = 1024,
    src_h: int = 1024
) -> Tuple[int, int, int, int]:
    """
    Expands bounding box [x, y, w, h] by pad_pct in each direction,
    clamping strictly within source image dimensions [0, 0, src_w, src_h].
    """
    x, y, w, h = box
    pad_x = w * pad_pct
    pad_y = h * pad_pct

    nx = max(0, int(round(x - pad_x)))
    ny = max(0, int(round(y - pad_y)))
    nw = min(src_w - nx, int(round(w + 2 * pad_x)))
    nh = min(src_h - ny, int(round(h + 2 * pad_y)))

    # Ensure strictly positive dimension
    nw = max(1, nw)
    nh = max(1, nh)

    return (nx, ny, nw, nh)


def label_layer(
    text: str = "Illustrative: defect removed",
    gravity: str = "south_west",
    x: int = 16,
    y: int = 16
) -> List[Dict[str, Any]]:
    """
    Constructs a Cloudinary overlay text layer to ensure every generated
    remediation view is self-describing and cannot be cropped out accidentally.
    """
    # Sanitize label text for Cloudinary URL formatting
    sanitized = text.replace(",", "%2C").replace("/", "%2F")
    return [
        {
            "overlay": {
                "font_family": "Arial",
                "font_size": 20,
                "font_weight": "bold",
                "text": sanitized,
            },
            "color": "white",
            "background": "rgb:000000c0",
        },
        {"flags": "layer_apply", "gravity": gravity, "x": x, "y": y},
    ]


def remediation_transform(
    finding: Finding,
    rule: GenRule,
    src_w: int,
    src_h: int,
    pad_pct: float = DEFAULT_PAD_PCT,
    mode: str = "region"
) -> List[Dict[str, Any]]:
    """
    Generates Cloudinary transformation segment for removing a defect.
    Prefers region-based removal (e_gen_remove:region_((...))) using CV bounding box.
    Fallback: prompt-based removal.
    """
    if mode == "region":
        x, y, w, h = expand_box(finding.region_px, pad_pct, src_w, src_h)
        return [{"effect": f"gen_remove:region_((x_{x};y_{y};w_{w};h_{h}))"}]
    else:
        prompt = rule.prompt or "the defect"
        sanitized_prompt = prompt.replace(" ", "_")
        return [{"effect": f"gen_remove:prompt_{sanitized_prompt}"}]


def remediation_url(
    public_id: str,
    findings: List[Finding],
    module: str,
    mode: str = "*",
    src_w: int = 1024,
    src_h: int = 1024,
    finding_ids: Optional[List[str]] = None,
    pad_pct: float = DEFAULT_PAD_PCT,
    remove_mode: str = "region"
) -> Tuple[str, List[Finding], List[Tuple[Finding, str]]]:
    """
    Constructs a cryptographically signed Cloudinary delivery URL for the Remediation View.
    Filters findings by policy and requested IDs.
    Returns: (signed_url, allowed_findings, blocked_findings)
    """
    # 1. Budget check
    guard_budget("gen_remove")

    # 2. Filter findings by requested IDs
    candidate_findings = findings
    if finding_ids is not None:
        target_set = set(finding_ids)
        candidate_findings = [f for f in findings if f.id in target_set]

    allowed_pairs: List[Tuple[Finding, GenRule]] = []
    blocked_findings: List[Tuple[Finding, str]] = []

    for f in candidate_findings:
        rule = rule_for_remediation(module, mode, f.label)
        if rule.allowed:
            allowed_pairs.append((f, rule))
        else:
            blocked_findings.append((f, rule.reason or "Generative remediation prohibited by policy"))

    if not allowed_pairs:
        raise PermissionError(
            "No selected findings are eligible for generative remediation under current policy."
        )

    # 3. Build chained transformations
    t: List[Dict[str, Any]] = []
    for f, r in allowed_pairs:
        t.extend(remediation_transform(f, r, src_w, src_h, pad_pct=pad_pct, mode=remove_mode))

    # Append self-describing label layer
    primary_label = allowed_pairs[0][1].label if allowed_pairs else "AI-generated illustration"
    t.extend(label_layer(primary_label))

    # 4. Sign and return
    url = signed_url(public_id, transformation=t)
    allowed_list = [f for f, _ in allowed_pairs]
    return url, allowed_list, blocked_findings


def check_remediation_readiness(url: str, timeout: float = 8.0) -> str:
    """
    Checks if a generative derived Cloudinary asset is ready.
    Returns: 'ready' | 'pending' | 'failed'
    """
    if not url or "mock" in url or url.startswith("data:"):
        return "ready"

    try:
        resp = requests.head(url, timeout=timeout, allow_redirects=True)
        if resp.status_code == 200:
            return "ready"
        elif resp.status_code in (202, 423):
            # Cloudinary processing in background
            return "pending"
        elif resp.status_code == 404:
            return "pending"
        else:
            return "failed"
    except Exception as e:
        logger.warning(f"Error checking remediation readiness: {e}")
        return "pending"


def generate_local_remediation(
    job: JobResult,
    source_b64: Optional[str] = None,
    finding_ids: Optional[List[str]] = None,
    pad_pct: float = DEFAULT_PAD_PCT,
) -> Tuple[str, List[Finding], List[Tuple[Finding, str]]]:
    """
    Offline / local fallback implementation of Remediation View.
    Uses Telea inpainting on the defect regions and stamps an authentic AI-generated label banner.
    Ensures 100% testability and offline developer experience without live cloud credits.
    """
    # 1. Policy check
    module = job.module
    mode = "*"
    if job.calibration and hasattr(job.calibration, "encoding"):
        mode = job.calibration.encoding.get("mode", "*")

    candidate_findings = job.findings
    if finding_ids is not None:
        target_set = set(finding_ids)
        candidate_findings = [f for f in job.findings if f.id in target_set]

    allowed_pairs: List[Tuple[Finding, GenRule]] = []
    blocked_findings: List[Tuple[Finding, str]] = []

    for f in candidate_findings:
        rule = rule_for_remediation(module, mode, f.label)
        if rule.allowed:
            allowed_pairs.append((f, rule))
        else:
            blocked_findings.append((f, rule.reason or "Generative remediation prohibited by policy"))

    if not allowed_pairs:
        raise PermissionError(
            "No selected findings are eligible for generative remediation under current policy."
        )

    # 2. Extract base image
    if not source_b64:
        views = job.assets.get("views", {})
        if isinstance(views, dict):
            source_b64 = views.get("raw") or views.get("clean") or views.get("annotated")
        if not source_b64:
            source_b64 = job.assets.get("spectrogram") or job.assets.get("waveform_b64")

    if not source_b64:
        raise ValueError("Job does not contain a valid source image for local remediation.")

    # Decode base64 image
    data_part = source_b64.split(",", 1)[-1] if "," in source_b64 else source_b64
    img_bytes = base64.b64decode(data_part)
    pil_img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    src_w, src_h = pil_img.size

    # Convert to OpenCV BGR
    img_bgr = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

    # 3. Create defect inpainting mask
    mask = np.zeros((src_h, src_w), dtype=np.uint8)

    for f, _ in allowed_pairs:
        x, y, w, h = expand_box(f.region_px, pad_pct=pad_pct, src_w=src_w, src_h=src_h)
        # Mark defect region on mask (white on black)
        mask[y:y+h, x:x+w] = 255

    # 4. Perform high-fidelity inpainting
    remediated_bgr = cv2.inpaint(img_bgr, mask, inpaintRadius=5, flags=cv2.INPAINT_TELEA)
    remediated_rgb = cv2.cvtColor(remediated_bgr, cv2.COLOR_BGR2RGB)

    # Strict ROI preservation invariant: ensure pixels outside defect mask remain strictly identical
    final_arr = np.array(pil_img).copy()
    mask_3d = np.repeat(mask[:, :, np.newaxis] > 0, 3, axis=2)
    final_arr[mask_3d] = remediated_rgb[mask_3d]
    result_pil = Image.fromarray(final_arr)

    # 5. Draw in-image watermark label layer
    draw = ImageDraw.Draw(result_pil, "RGBA")
    primary_label = allowed_pairs[0][1].label if allowed_pairs else "AI-generated illustration"
    label_text = f"AI-REMEDIATED · {primary_label.upper()} · DISPLAY ONLY"

    try:
        font = ImageFont.truetype("arial.ttf", 16)
    except Exception:
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), label_text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]

    # Draw dark pill banner at bottom-left
    pad = 8
    bx0, by0 = 16, src_h - th - pad * 2 - 16
    bx1, by1 = bx0 + tw + pad * 2, src_h - 16

    draw.rounded_rectangle([bx0, by0, bx1, by1], radius=6, fill=(15, 23, 42, 220))
    draw.text((bx0 + pad, by0 + pad), label_text, fill=(255, 255, 255, 255), font=font)

    # 6. Encode to base64
    buf = io.BytesIO()
    result_pil.save(buf, format="PNG")
    data_url = f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode()}"

    allowed_list = [f for f, _ in allowed_pairs]
    return data_url, allowed_list, blocked_findings
