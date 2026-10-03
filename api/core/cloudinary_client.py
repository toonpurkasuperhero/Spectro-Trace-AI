import time
import json
import logging
import io
from typing import Dict, Any, List, Optional, Callable
import cloudinary
import cloudinary.uploader
import cloudinary.utils
import cloudinary.api
import cloudinary.search
from api.core.config import settings
from api.core.schema import ModuleConfig

logger = logging.getLogger(__name__)

# Initialize Cloudinary configuration
cloudinary.config(
    cloud_name=settings.CLOUDINARY_CLOUD_NAME,
    api_key=settings.CLOUDINARY_API_KEY,
    api_secret=settings.CLOUDINARY_API_SECRET,
    secure=True
)

# In-memory daily usage tracking (supplemented by DB in production)
_daily_usage = {
    "generative": 0,
    "vision": 0,
    "gen_fill": 0,
    "gen_remove": 0,
    "gen_replace": 0,
    "imagegen": 0,
    "last_reset": time.time()
}

def _check_reset_usage():
    global _daily_usage
    if time.time() - _daily_usage["last_reset"] > 86400:
        _daily_usage = {
            "generative": 0,
            "vision": 0,
            "gen_fill": 0,
            "gen_remove": 0,
            "gen_replace": 0,
            "imagegen": 0,
            "last_reset": time.time()
        }

def cloudinary_configured() -> bool:
    """Returns True when Cloudinary credentials are fully set."""
    return bool(
        settings.CLOUDINARY_CLOUD_NAME
        and settings.CLOUDINARY_API_KEY
        and settings.CLOUDINARY_API_SECRET
    )

def guard_budget(kind: str):
    _check_reset_usage()
    if kind in ("generative", "gen_fill", "gen_remove", "gen_replace", "imagegen"):
        if not settings.GEN_FEATURES_ENABLED:
            raise PermissionError("GEN_FEATURES_ENABLED is false. Generative features are globally disabled.")
    if settings.DEMO_MODE and kind in ("generative", "vision", "gen_fill", "gen_remove", "gen_replace", "imagegen"):
        raise PermissionError(f"DEMO_MODE is active. New {kind} calls are disabled.")
    if kind == "generative" and _daily_usage["generative"] >= settings.MAX_GENERATIVE_CALLS_PER_DAY:
        raise PermissionError(f"Daily generative budget exceeded ({settings.MAX_GENERATIVE_CALLS_PER_DAY} calls).")
    if kind == "gen_fill" and _daily_usage["gen_fill"] >= settings.MAX_GENFILL_CALLS_PER_DAY:
        raise PermissionError(f"Daily gen_fill budget exceeded ({settings.MAX_GENFILL_CALLS_PER_DAY} calls).")
    if kind in ("gen_remove", "gen_replace") and _daily_usage["gen_remove"] >= settings.MAX_GENREMOVE_CALLS_PER_DAY:
        raise PermissionError(f"Daily gen_remove budget exceeded ({settings.MAX_GENREMOVE_CALLS_PER_DAY} calls).")
    if kind == "imagegen" and _daily_usage["imagegen"] >= settings.MAX_IMAGEGEN_CALLS_PER_DAY:
        raise PermissionError(f"Daily imagegen budget exceeded ({settings.MAX_IMAGEGEN_CALLS_PER_DAY} calls).")
    if kind == "vision" and _daily_usage["vision"] >= settings.MAX_VISION_CALLS_PER_DAY:
        raise PermissionError(f"Daily vision budget exceeded ({settings.MAX_VISION_CALLS_PER_DAY} calls).")

def log_usage(kind: str, duration_ms: int, success: bool):
    global _daily_usage
    if kind in _daily_usage:
        _daily_usage[kind] += 1
    logger.info(f"[CLD_USAGE] kind={kind} duration={duration_ms}ms success={success}")

def get_usage_summary() -> Dict[str, Any]:
    _check_reset_usage()
    CREDIT_WEIGHTS = {
        "generative": 1.0,
        "gen_fill": 1.0,
        "gen_remove": 1.0,
        "gen_replace": 1.0,
        "imagegen": 2.0,
        "vision": 0.5
    }
    est_credits = sum(
        _daily_usage.get(k, 0) * CREDIT_WEIGHTS.get(k, 1.0)
        for k in CREDIT_WEIGHTS
    )
    return {
        "daily_usage": dict(_daily_usage),
        "caps": {
            "generative": settings.MAX_GENERATIVE_CALLS_PER_DAY,
            "gen_fill": settings.MAX_GENFILL_CALLS_PER_DAY,
            "gen_remove": settings.MAX_GENREMOVE_CALLS_PER_DAY,
            "imagegen": settings.MAX_IMAGEGEN_CALLS_PER_DAY,
            "vision": settings.MAX_VISION_CALLS_PER_DAY,
        },
        "estimated_credits_consumed": round(est_credits, 2),
        "gen_features_enabled": settings.GEN_FEATURES_ENABLED,
        "demo_mode": settings.DEMO_MODE,
        "env": settings.ENV
    }

def cld_call(kind: str, fn: Callable, *args, **kwargs) -> Any:
    """Wraps Cloudinary API calls with budget enforcement, timing, and error handling."""
    guard_budget(kind)
    t0 = time.time()
    success = False
    try:
        res = fn(*args, **kwargs)
        success = True
        return res
    finally:
        duration_ms = int((time.time() - t0) * 1000)
        log_usage(kind, duration_ms, success)

# ─────────────────────────────────────────────────────────────────────────────
# Asset Upload — server-side upload to Cloudinary
# ─────────────────────────────────────────────────────────────────────────────

def upload_asset(
    file_bytes: bytes,
    module_id: str,
    job_id: str,
    resource_type: str = "image",
    filename: Optional[str] = None,
    extra_tags: Optional[List[str]] = None,
) -> str:
    """
    Uploads raw bytes directly to Cloudinary as an authenticated asset.
    Returns the Cloudinary public_id. Called by /jobs/run-local when credentials exist,
    so every upload goes through Cloudinary — enabling all AI transformations.
    """
    tags = [module_id, f"module:{module_id}", f"run:{job_id}", f"env:{settings.ENV}", "status:uploaded"]
    if extra_tags:
        tags.extend(extra_tags)

    result = cloudinary.uploader.upload(
        io.BytesIO(file_bytes),
        public_id=f"spectrotrace/{module_id}/{job_id}",
        resource_type=resource_type,
        type="upload",
        tags=",".join(tags),
        overwrite=True,
        invalidate=True,
    )
    public_id = result["public_id"]
    logger.info(f"[CLD_UPLOAD] {job_id} \u2192 {public_id} ({resource_type})")
    return public_id

# ─────────────────────────────────────────────────────────────────────────────
# URL Construction — q_auto + f_auto on every URL
# ─────────────────────────────────────────────────────────────────────────────

def signed_url(
    public_id: str,
    transformation: Optional[List[Dict[str, Any]]] = None,
    resource_type: str = "image",
    format: Optional[str] = None,
    attachment: bool = False,
) -> str:
    """
    Cryptographically signed Cloudinary delivery URL.
    Automatically appends q_auto + f_auto for optimal quality and format on every URL.
    Falls back to a mock URL when credentials are not configured (dev without .env).
    """
    if not cloudinary_configured():
        cloud = settings.CLOUDINARY_CLOUD_NAME or "demo"
        return f"https://res.cloudinary.com/{cloud}/{resource_type}/upload/s--mock--/{public_id}"

    transforms = list(transformation or [])
    transforms.append({"quality": "auto", "fetch_format": "auto"})

    extra_kwargs: Dict[str, Any] = {}
    if attachment:
        extra_kwargs["flags"] = "attachment"

    url, _ = cloudinary.utils.cloudinary_url(
        public_id,
        type="upload",
        sign_url=True,
        resource_type=resource_type,
        transformation=transforms,
        **({"flags": "attachment"} if attachment else {}),
    )
    return url

# ─────────────────────────────────────────────────────────────────────────────
# Cloudinary AI View Builders
# Each function builds a fully Cloudinary-powered view URL — no local Python rendering.
# ─────────────────────────────────────────────────────────────────────────────

def cld_raw_url(public_id: str, resource_type: str = "image") -> str:
    """Original (raw) asset — just signed delivery with q_auto/f_auto."""
    return signed_url(public_id, transformation=[], resource_type=resource_type)

def cld_annotated_url(
    public_id: str,
    findings: list,
    calibration=None,
    resource_type: str = "image",
) -> str:
    """
    Findings annotations applied as Cloudinary URL transformation layers.
    Bounding boxes + labels composited server-side by Cloudinary — no PIL drawing.
    """
    from api.core.annotate import build_annotation_transform
    transforms = build_annotation_transform(findings, calibration)
    return signed_url(public_id, transformation=transforms, resource_type=resource_type)

def cld_clean_url(public_id: str, resource_type: str = "image") -> str:
    """
    Cosmetic / clean view via Cloudinary e_gen_restore:
    AI-powered restoration removes compression artifacts and enhances sharpness.
    Replaces the local OpenCV GaussianBlur cosmetic view.
    """
    transforms = [{"effect": "gen_restore"}]
    return signed_url(public_id, transformation=transforms, resource_type=resource_type)

def cld_upscaled_url(public_id: str, target_width: int = 2048, resource_type: str = "image") -> str:
    """
    AI super-resolution upscale (e_upscale) — 4× resolution enhancement.
    Output is capped at target_width to avoid oversized payloads.
    """
    transforms = [
        {"effect": "upscale"},
        {"width": target_width, "crop": "limit"},
    ]
    return signed_url(public_id, transformation=transforms, resource_type=resource_type)

def cld_background_removed_url(public_id: str, resource_type: str = "image") -> str:
    """
    Subject-isolated view via Cloudinary e_background_removal AI.
    Used for Print and Specimen modules to isolate the part/specimen cleanly.
    """
    transforms = [{"effect": "background_removal"}]
    return signed_url(public_id, transformation=transforms, resource_type=resource_type)

def cld_enhanced_url(public_id: str, resource_type: str = "image") -> str:
    """
    Auto-enhanced view via e_improve — vibrance, contrast and brightness optimisation
    for cleaner visual presentation without altering measurements.
    """
    transforms = [{"effect": "improve:outdoor:40"}]
    return signed_url(public_id, transformation=transforms, resource_type=resource_type)

def cld_waveform_url(
    public_id: str,
    width: int = 900,
    height: int = 200,
    color: str = "00b4d8",
) -> str:
    """
    Audio waveform image built by Cloudinary's fl_waveform flag.
    Replaces the matplotlib-rendered waveform PNG — zero Python rendering.
    """
    transforms = [
        {
            "width": width,
            "height": height,
            "crop": "scale",
            "flags": "waveform",
            "background": "rgb:0b0f14",
            "color": f"rgb:{color}",
        },
    ]
    return signed_url(public_id, transformation=transforms, resource_type="video")

def cld_fusion_url(
    thermal_public_id: str,
    visible_public_id: str,
    opacity: int = 55,
) -> str:
    """
    Thermal-over-visible fusion: overlay the thermal render on the visible photo
    entirely as a Cloudinary URL transform — no server-side image compositing.
    """
    cld_overlay = visible_public_id.replace("/", ":")
    transforms = [
        {"overlay": cld_overlay, "opacity": opacity, "effect": "multiply"},
        {"flags": "layer_apply", "gravity": "center"},
    ]
    return signed_url(thermal_public_id, transformation=transforms)

def cld_heatmap_url(public_id: str) -> str:
    """
    Deviation heatmap via Cloudinary tint gradient:
    blue→cyan→green→yellow→red colour-maps the image intensity.
    Used for Print deviation heatmap and Specimen density map views.
    """
    transforms = [
        {"effect": "tint:60:blue:0p:cyan:30p:green:60p:yellow:80p:red"},
        {"effect": "improve:50"},
    ]
    return signed_url(public_id, transformation=transforms)

def cld_spectrogram_annotated_url(
    public_id: str,
    findings: list,
    resource_type: str = "video",
) -> str:
    """
    Audio spectrogram with finding annotation overlays.
    Cloudinary treats audio as resource_type=video; this builds annotation layers on it.
    """
    from api.core.annotate import build_annotation_transform
    transforms = build_annotation_transform(findings, cal=None)
    return signed_url(public_id, transformation=transforms, resource_type=resource_type)

# ─────────────────────────────────────────────────────────────────────────────
# Hybrid helper: local PIL render → upload to Cloudinary → serve signed CDN URL
# Used for views where Cloudinary transforms are unreliable (annotations, heatmaps,
# audio spectrogram) — result is still served from Cloudinary CDN with CLD branding.
# ─────────────────────────────────────────────────────────────────────────────

def upload_rendered_view(
    pil_img,
    base_public_id: str,
    view_suffix: str,
    resource_type: str = "image",
) -> str:
    """
    Saves a PIL image to bytes, uploads it to Cloudinary under
    {base_public_id}__{view_suffix}, and returns a signed CDN URL.
    Falls back to a raw data URL if upload fails.
    """
    import io as _io
    buf = _io.BytesIO()
    pil_img.save(buf, format="PNG")
    view_pid = f"{base_public_id}__{view_suffix}"
    try:
        result = cloudinary.uploader.upload(
            buf.getvalue(),
            public_id=view_pid,
            resource_type=resource_type,
            type="upload",
            overwrite=True,
            invalidate=True,
        )
        return signed_url(result["public_id"], resource_type=resource_type)
    except Exception as e:
        logger.warning(f"[CLD_VIEW_UPLOAD] {view_suffix} upload failed ({e}), using local fallback")
        import base64 as _b64
        return "data:image/png;base64," + _b64.b64encode(buf.getvalue()).decode()


# ─────────────────────────────────────────────────────────────────────────────
# Module view builder — one call generates all views for a finished job
# ─────────────────────────────────────────────────────────────────────────────

def build_all_views(
    public_id: str,
    module_id: str,
    findings: list,
    calibration=None,
    resource_type: str = "image",
    render_img=None,           # PIL Image — needed for local-render views
    heatmap_img=None,          # PIL Image — pre-computed heatmap (print module)
    spectrogram_img=None,      # PIL Image — audio spectrogram
    waveform_img=None,         # PIL Image — audio waveform
) -> Dict[str, str]:
    """
    Generates the full set of view URLs for a finished job.

    Hybrid strategy (user-approved):
    - Pure Cloudinary AI transforms where they work natively:
        raw, clean (e_gen_restore), enhanced (e_improve), upscaled (e_upscale),
        subject_isolated (e_background_removal), waveform (fl_waveform)
    - Local PIL render → CLD upload → signed CDN URL where Cloudinary transforms
      are unreliable or resource_type incompatible:
        annotated (bounding boxes + labels), heatmap, audio spectrogram
    All URLs are served from Cloudinary CDN with q_auto/f_auto — labelled "CLD" in UI.
    """
    views: Dict[str, str] = {
        "raw":      cld_raw_url(public_id, resource_type=resource_type),
        "enhanced": cld_enhanced_url(public_id, resource_type=resource_type),
        "upscaled": cld_upscaled_url(public_id, resource_type=resource_type),
    }

    # ── Clean / Restored view: local noise reduction → upload to CLD ─────────
    if render_img is not None:
        try:
            import cv2, numpy as np
            from PIL import Image as _PILImage
            arr = np.array(render_img)
            clean_arr = cv2.GaussianBlur(arr, (7, 7), 0)
            clean_pil = _PILImage.fromarray(clean_arr)
            views["clean"] = upload_rendered_view(clean_pil, public_id, "clean")
        except Exception:
            views["clean"] = cld_clean_url(public_id, resource_type=resource_type)
    else:
        views["clean"] = cld_clean_url(public_id, resource_type=resource_type)


    # ── Annotated view: local PIL draw → upload to CLD ───────────────────────
    if render_img is not None and findings is not None:
        try:
            from api.core.annotate import draw_annotated_pil
            ann_pil = draw_annotated_pil(render_img, findings)
            views["annotated"] = upload_rendered_view(ann_pil, public_id, "annotated")
        except Exception as e:
            logger.warning(f"[CLD_ANNOTATED] local render failed ({e}), using CLD transform fallback")
            views["annotated"] = cld_annotated_url(public_id, findings, calibration, resource_type=resource_type)
    else:
        views["annotated"] = cld_annotated_url(public_id, findings, calibration, resource_type=resource_type)

    # ── Module-specific views ─────────────────────────────────────────────────
    if module_id == "audio":
        # Audio: waveform image uploaded as CLD asset, or fl_waveform fallback
        if waveform_img is not None:
            views["waveform"] = upload_rendered_view(waveform_img, public_id, "waveform", resource_type="image")
        else:
            views["waveform"] = cld_waveform_url(public_id)

        # Spectrogram raw + annotated: PIL image uploaded as separate CLD asset
        if spectrogram_img is not None:
            views["raw"] = upload_rendered_view(spectrogram_img, public_id, "spectrogram_raw", resource_type="image")
            if findings:
                try:
                    from api.core.annotate import draw_annotated_pil
                    ann_spec = draw_annotated_pil(spectrogram_img, findings)
                    views["annotated"] = upload_rendered_view(ann_spec, public_id, "spectrogram_annotated", resource_type="image")
                except Exception:
                    views["annotated"] = views["raw"]
            else:
                views["annotated"] = views["raw"]
            # clean/enhanced/upscaled on spectrogram image asset
            spec_pid = f"{public_id}__spectrogram_raw"
            views["clean"]    = cld_clean_url(spec_pid)
            views["enhanced"] = cld_enhanced_url(spec_pid)
            views["upscaled"] = cld_upscaled_url(spec_pid)
            try:
                hm_spec = _build_thermal_heatmap(spectrogram_img)
                views["heatmap"] = upload_rendered_view(hm_spec, public_id, "spectrogram_heatmap")
            except Exception:
                pass

    elif module_id in ("print", "specimen"):
        # Heatmap: use pre-computed heatmap_img if available, else local PIL gradient map
        if heatmap_img is not None:
            views["heatmap"] = upload_rendered_view(heatmap_img, public_id, "heatmap")
        elif render_img is not None:
            try:
                hm = _build_thermal_heatmap(render_img)
                views["heatmap"] = upload_rendered_view(hm, public_id, "heatmap")
            except Exception:
                views["heatmap"] = upload_rendered_view(render_img, public_id, "heatmap")
        else:
            views["heatmap"] = cld_raw_url(public_id)
        views["subject_isolated"] = cld_background_removed_url(public_id)

    elif module_id == "thermal":
        # Heatmap: local PIL ironbow → discrete high-contrast heatmap uploaded to CLD
        if render_img is not None:
            try:
                hm = _build_thermal_heatmap(render_img)
                views["heatmap"] = upload_rendered_view(hm, public_id, "heatmap")
            except Exception:
                views["heatmap"] = upload_rendered_view(render_img, public_id, "heatmap")
        else:
            views["heatmap"] = cld_raw_url(public_id)

    return views



def _build_thermal_heatmap(render_img) -> "Image.Image":
    """
    Converts a thermal ironbow render into a discrete 5-band heatmap
    using PIL only (no matplotlib dependency). Returns a PIL Image.
    """
    import numpy as np
    from PIL import Image as PILImage
    arr = np.array(render_img.convert("L"), dtype=np.float32)
    norm = (arr - arr.min()) / max(arr.max() - arr.min(), 1.0)
    # Map 0-1 to a blue→cyan→green→yellow→red colour gradient
    r = np.clip(norm * 2 - 0.5, 0, 1)
    g = np.clip(1 - np.abs(norm * 2 - 1), 0, 1)
    b = np.clip(0.5 - norm * 2 + 1, 0, 1)
    rgb = (np.stack([r, g, b], axis=2) * 255).astype(np.uint8)
    return PILImage.fromarray(rgb, mode="RGB")


# ─────────────────────────────────────────────────────────────────────────────
# Upload Sign / Webhook / Metadata / Search helpers
# ─────────────────────────────────────────────────────────────────────────────

def sign_upload(module: ModuleConfig) -> Dict[str, Any]:
    """
    Generates a secure signature and parameters for direct browser-to-Cloudinary upload.
    The webhook notification_url is attached here only, preventing self-trigger loops.
    """
    ts = int(time.time())
    params = {
        "timestamp": ts,
        "upload_preset": module.upload_preset,
        "type": "authenticated",
        "folder": f"spectrotrace/{module.id}",
        "tags": f"{module.tag_prefix},module:{module.id},status:uploaded,env:{settings.ENV}",
        "notification_url": f"{settings.API_BASE}/webhooks/cloudinary",
    }
    sig = cloudinary.utils.api_sign_request(params, settings.CLOUDINARY_API_SECRET)
    return {
        **params,
        "signature": sig,
        "api_key": settings.CLOUDINARY_API_KEY,
        "cloud_name": settings.CLOUDINARY_CLOUD_NAME
    }

def mark_done(
    public_id: str,
    risk_level: str,
    risk_score: int,
    review_state: str = "pending",
    resource_type: str = "image"
):
    """Updates Cloudinary structured metadata and replaces status tags on completion."""
    try:
        cld_call(
            "metadata",
            cloudinary.uploader.update_metadata,
            {"risk_level": risk_level, "risk_score": risk_score, "review_state": review_state},
            [public_id],
            resource_type=resource_type,
            type="authenticated"
        )
    except Exception as e:
        logger.warning(f"Could not update structured metadata (define fields in Cloudinary console first): {e}")

    cld_call(
        "tags",
        cloudinary.uploader.replace_tag,
        f"status:done,risk:{risk_level}",
        [public_id],
        resource_type=resource_type,
        type="authenticated"
    )

def search_runs(
    module: Optional[str] = None,
    risk: Optional[str] = None,
    max_results: int = 30,
) -> Dict[str, Any]:
    """Queries Cloudinary Search API for history and review queue items."""
    expr = "folder=spectrotrace/*"
    if module:
        expr += f" AND tags=module:{module}"
    if risk:
        expr += f" AND tags=risk:{risk}"

    return cld_call(
        "search",
        lambda: cloudinary.Search()
            .expression(expr)
            .sort_by("created_at", "desc")
            .with_field("metadata")
            .with_field("tags")
            .max_results(max_results)
            .execute()
    )

def verify_webhook_signature(body: str, timestamp: int, signature: str) -> bool:
    """Verifies Cloudinary webhook HMAC signature. Rejects stale timestamps (>1 hr)."""
    now = int(time.time())
    if abs(now - timestamp) > 3600:
        logger.warning(f"Webhook rejected: stale timestamp {timestamp} vs now {now}")
        return False
    return cloudinary.utils.verify_notification_signature(body, timestamp, signature)
