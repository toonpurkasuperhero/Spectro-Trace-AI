import json
import time
import io
import base64
import logging
import numpy as np
import cv2
from contextlib import asynccontextmanager
from typing import Dict, Any, Optional, List
from PIL import Image, ImageDraw, ImageFont
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from api.core.config import settings
from api.core.schema import JobResult, Finding
from api.core.cloudinary_client import (
    sign_upload,
    signed_url,
    mark_done,
    search_runs,
    verify_webhook_signature,
    get_usage_summary,
    upload_asset,
    build_all_views,
    cloudinary_configured,
)
from api.core.jobs import (
    create_or_get_job,
    get_job,
    list_jobs,
    update_job_stage,
    finish_job,
    job_event_generator,
    check_stuck_jobs
)
from api.modules.registry import get_module_config
from api.modules.thermal import process_thermal_pipeline
from api.modules.audio import process_audio_pipeline
from api.modules.print_defect import process_print_pipeline
from api.modules.specimen import process_specimen_pipeline
from api.core.exports import export_url, generate_local_export, PROFILES
from api.core.gen_policy import (
    policy_allows_genfill,
    rule_for_remediation,
    policy_allows_simulation,
    SIMULATION_SCENARIOS,
    GENERATIVE_BANNER_TEXT
)
from api.core.genviews import (
    remediation_url,
    generate_local_remediation,
    check_remediation_readiness,
    expand_box
)
from api.core.imagegen import (
    get_allowed_models,
    create_simulation_record,
    get_simulation,
    list_job_simulations,
    run_simulation_job
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("spectrotrace")

# ── Local image helpers — used ONLY when Cloudinary is not configured (dev mode) ─

def pil_to_b64(img, max_dim: int = 800) -> str:
    """Convert PIL Image or numpy array to a base64 PNG data URL."""
    if isinstance(img, np.ndarray):
        if img.dtype != np.uint8:
            vmin, vmax = img.min(), img.max()
            if vmax > vmin:
                img = ((img - vmin) / (vmax - vmin) * 255).astype(np.uint8)
            else:
                img = np.zeros_like(img, dtype=np.uint8)
        if img.ndim == 2:
            img = Image.fromarray(img, mode="L").convert("RGB")
        elif img.ndim == 3 and img.shape[2] == 4:
            img = Image.fromarray(img, mode="RGBA")
        else:
            img = Image.fromarray(img)
    elif not isinstance(img, Image.Image):
        return ""

    # Composite RGBA onto white so transparency doesn't render as black
    if img.mode == "RGBA":
        background = Image.new("RGB", img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[3])
        img = background
    else:
        img = img.convert("RGB")

    # Downscale for transfer efficiency
    w, h = img.size
    if max(w, h) > max_dim:
        scale = max_dim / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def draw_annotated_b64(img, findings: list, max_dim: int = 800) -> str:
    """Draw bounding boxes + labels for each finding onto a PIL image and return base64."""
    if isinstance(img, np.ndarray):
        if img.dtype != np.uint8:
            vmin, vmax = img.min(), img.max()
            if vmax > vmin:
                img = ((img - vmin) / (vmax - vmin) * 255).astype(np.uint8)
            else:
                img = np.zeros_like(img, dtype=np.uint8)
        if img.ndim == 2:
            img = Image.fromarray(img, mode="L").convert("RGB")
        else:
            img = Image.fromarray(img).convert("RGB")
    elif isinstance(img, Image.Image):
        img = img.convert("RGB")
    else:
        return ""

    # Downscale
    w, h = img.size
    if max(w, h) > max_dim:
        scale = max_dim / max(w, h)
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        scale_factor = scale
    else:
        scale_factor = 1.0

    draw = ImageDraw.Draw(img, "RGBA")
    RISK_COLORS = {
        "high":   (255,  60,  60, 220),
        "medium": (255, 165,   0, 220),
        "low":    ( 80, 220,  80, 220),
    }

    for f in findings:
        x, y, bw, bh = [int(v * scale_factor) for v in f.region_px]
        color = RISK_COLORS.get(getattr(f, "risk_level", "low"), RISK_COLORS["low"])
        # Bounding box
        draw.rectangle([x, y, x + bw, y + bh], outline=color, width=2)
        # Label background + text
        label = getattr(f, "short_label", None) or f.label
        txt_w = max(len(label) * 7, 60)
        ty = max(0, y - 18)
        draw.rectangle([x, ty, x + txt_w, ty + 16], fill=(0, 0, 0, 160))
        draw.text((x + 3, ty + 1), label, fill=color[:3] + (255,))

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()




@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: sweep any stuck jobs remaining from a previous process restart."""
    logger.info("[startup] Running stuck-job sweeper...")
    check_stuck_jobs()
    yield
    logger.info("[shutdown] SpectroTrace API shutting down.")


class ReviewUpdate(BaseModel):
    review_state: str  # "pending" | "approved" | "rejected"


class RemediationRequest(BaseModel):
    finding_ids: Optional[List[str]] = None
    mode: Optional[str] = "region"  # "region" | "prompt"


class SimulationRequest(BaseModel):
    scenario: str
    severity: int = 3
    model: str = "auto"
    variants: int = 1
    user_note: Optional[str] = None


limiter = Limiter(key_func=get_remote_address)
app = FastAPI(
    title="SpectroTrace AI API",
    description="Physical Signal Analytics Engine powered by Classical CV/DSP, Cloudinary, and AI Vision",
    version="1.0.0",
    lifespan=lifespan,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS Middleware - allows localhost, Vercel deployments, and custom domains
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_origin_regex=r"https?://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/healthz")
async def health_check():
    """Liveness probe for cloud deployments (pre-warming cold starts)."""
    check_stuck_jobs()
    return {"status": "healthy", "env": settings.ENV, "demo_mode": settings.DEMO_MODE}

@app.get("/admin/usage")
async def get_admin_usage():
    """
    Returns daily usage metrics, caps, and credit consumption
    across vision, gen_remove, gen_fill, and imagegen calls.
    """
    return get_usage_summary()

@app.post("/uploads/sign")
@limiter.limit("30/minute")
async def sign_direct_upload(request: Request, module: str = Form(...)):
    """
    Mints signed parameters for direct-to-Cloudinary browser uploads.
    Rate limited per client to protect signature issuance.
    """
    config = get_module_config(module)
    if not config:
        raise HTTPException(status_code=400, detail=f"Unsupported module: '{module}'")

    if not settings.CLOUDINARY_API_SECRET:
        # Return mock signed params for offline development
        return {
            "upload_preset": config.upload_preset,
            "type": "authenticated",
            "folder": f"spectrotrace/{module}",
            "tags": f"{config.tag_prefix},module:{module},status:uploaded",
            "signature": "offline_signature_mock",
            "timestamp": int(time.time()),
            "api_key": settings.CLOUDINARY_API_KEY or "mock_key",
            "cloud_name": settings.CLOUDINARY_CLOUD_NAME or "mock_cloud"
        }

    return sign_upload(config)

@app.post("/webhooks/cloudinary")
async def cloudinary_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Cloudinary notification webhook receiver.
    1. Verifies HMAC signature & rejects stale timestamps (>1hr).
    2. Enforces self-trigger loop prevention: ignores 'generated' tag or 'spectrotrace/derived' folder.
    3. Triggers background job pipeline idempotently.
    """
    body_bytes = await request.body()
    body_str = body_bytes.decode("utf-8")

    # In production with Cloudinary configured, verify headers
    if settings.CLOUDINARY_API_SECRET:
        ts_header = request.headers.get("X-Cld-Timestamp")
        sig_header = request.headers.get("X-Cld-Signature")
        if not (ts_header and sig_header):
            raise HTTPException(status_code=401, detail="Missing webhook authentication headers")
        
        if not verify_webhook_signature(body_str, int(ts_header), sig_header):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")

    payload = json.loads(body_str)
    
    # Self-trigger loop check (Rule 18.2)
    tags = payload.get("tags", [])
    folder = payload.get("folder", "")
    if "generated" in tags or "derived" in folder or "spectrotrace/derived" in folder:
        logger.info(f"Ignoring derived/generated asset webhook for {payload.get('public_id')}")
        return {"status": "ignored", "reason": "derived_asset"}

    public_id = payload.get("public_id")
    notification_type = payload.get("notification_type")

    if notification_type == "upload" and public_id:
        job_id = f"job_{public_id.replace('/', '_')}"
        # Determine module from folder or tags
        module_id = "thermal"
        for t in tags:
            if t.startswith("module:"):
                module_id = t.split(":", 1)[1]

        job = create_or_get_job(job_id, module=module_id, cld_public_id=public_id)
        
        # Enqueue background pipeline task
        background_tasks.add_task(run_analysis_pipeline, job_id, module_id, public_id, payload)

    return {"status": "received"}

@app.get("/jobs/{job_id}")
async def get_job_status(job_id: str):
    """Polling fallback endpoint returning full job state and findings."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

@app.patch("/jobs/{job_id}/review")
async def update_review_state(job_id: str, body: ReviewUpdate):
    """
    Updates the review state (pending / approved / rejected) for a job.
    Writes back to the in-memory job record and, when Cloudinary is configured,
    also updates the structured metadata field on the asset.
    """
    valid_states = {"pending", "approved", "rejected"}
    if body.review_state not in valid_states:
        raise HTTPException(status_code=422, detail=f"review_state must be one of {valid_states}")

    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Write to in-memory store
    job.review_state = body.review_state  # type: ignore[attr-defined]

    # Write back to Cloudinary metadata if configured
    if settings.CLOUDINARY_API_SECRET:
        cld_public_id = (job.assets.get("raw") or {}).get("public_id", "")
        if cld_public_id:
            try:
                mark_done(
                    cld_public_id,
                    risk_level=job.risk_level or "low",
                    risk_score=job.risk_score or 0,
                    review_state=body.review_state,
                )
            except Exception as e:
                logger.warning(f"Could not write review state to Cloudinary: {e}")

    return {"job_id": job_id, "review_state": body.review_state}

@app.get("/jobs/{job_id}/exports")
async def get_job_export(
    job_id: str,
    profile: str = "slide_16x9",
    fill: str = "blur",
    view: str = "annotated",
    annotated: bool = True
):
    """
    Export Profiles (Feature C): Presentation-ready formats (16:9, 9:16, 1:1).
    All rendering via Cloudinary — c_pad + b_gen_fill/b_blurred/rgb, text overlays, slide chrome.
    Requires Cloudinary credentials. Returns 503 when not configured.
    """
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if profile not in PROFILES:
        raise HTTPException(status_code=422, detail=f"Invalid profile '{profile}'. Must be one of {list(PROFILES.keys())}")

    if fill not in ("blur", "solid", "generative"):
        raise HTTPException(status_code=422, detail="fill must be 'blur', 'solid', or 'generative'")

    # Policy check for generative fill
    if fill == "generative":
        submode = "*"
        if job.calibration and getattr(job.calibration, "kind", None) == "thermal":
            submode = "radiometric"
        elif job.calibration and hasattr(job.calibration, "encoding") and isinstance(job.calibration.encoding, dict):
            submode = job.calibration.encoding.get("mode", "*")
        allowed, reason = policy_allows_genfill(job.module, mode=submode)
        if not allowed:
            raise HTTPException(status_code=403, detail=f"Policy restriction: {reason}")


    if not cloudinary_configured():
        raise HTTPException(
            status_code=503,
            detail="Export Profiles require Cloudinary credentials. Set CLOUDINARY_CLOUD_NAME, "
                   "CLOUDINARY_API_KEY, and CLOUDINARY_API_SECRET in .env."
        )

    # Resolve public_id — job now always has a real Cloudinary public_id when creds were set at upload time
    cld_pid = job.assets.get("cld_public_id")
    if not cld_pid:
        # Older jobs: try to extract from raw view URL
        raw_views = job.assets.get("views", {})
        raw_url = raw_views.get("raw", "") if isinstance(raw_views, dict) else ""
        if raw_url and "/authenticated/" in raw_url:
            # Extract public_id segment after the signature
            try:
                cld_pid = raw_url.split("/authenticated/")[-1].split("?")[0].split("/s--")[0]
                # strip leading signature slug if present
                if "/" in cld_pid and "--" in cld_pid.split("/")[0]:
                    cld_pid = "/".join(cld_pid.split("/")[1:])
            except Exception:
                cld_pid = None

    if not cld_pid:
        raise HTTPException(
            status_code=422,
            detail="Cannot resolve Cloudinary public_id for this job. Re-upload the file with Cloudinary credentials configured."
        )

    try:
        url = export_url(job, view=view, profile=profile, fill=fill, annotated=annotated, base_public_id=cld_pid)
        return {
            "job_id": job_id,
            "profile": profile,
            "fill": fill,
            "view": view,
            "export_url": url,
            "is_generative": fill == "generative",
            "label": "Background extended by AI (display only)" if fill == "generative" else None,
            "cloudinary": True,
        }
    except PermissionError as pe:
        raise HTTPException(status_code=403, detail=str(pe))
    except Exception as e:
        logger.error(f"Export generation error for {job_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Export failed: {e}")

@app.get("/jobs/{job_id}/views")
async def get_job_views(job_id: str):
    """Returns available views and evaluates policy readiness for Remediation View."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    views = dict(job.assets.get("views", {}))

    submode = "*"
    if job.calibration and hasattr(job.calibration, "encoding") and isinstance(job.calibration.encoding, dict):
        raw_m = job.calibration.encoding.get("mode", "*")
        submode = "materials" if "material" in raw_m.lower() else ("histology" if "histol" in raw_m.lower() else raw_m)

    eligible_ids = []
    blocked_details = []
    for f in job.findings:
        rule = rule_for_remediation(job.module, submode, f.label)
        if rule.allowed:
            eligible_ids.append(f.id)
        else:
            blocked_details.append({"id": f.id, "label": f.label, "reason": rule.reason})

    remediation_allowed = len(eligible_ids) > 0
    reason = None
    if not remediation_allowed:
        if blocked_details:
            reason = blocked_details[0]["reason"]
        else:
            reason = f"No defect findings available for remediation on module '{job.module}'"

    return {
        "job_id": job_id,
        "module": job.module,
        "views": views,
        "remediation_status": {
            "allowed": remediation_allowed,
            "eligible_finding_ids": eligible_ids,
            "blocked_findings": blocked_details,
            "reason": reason,
        }
    }

@app.post("/jobs/{job_id}/remediation")
async def generate_remediation(job_id: str, body: Optional[RemediationRequest] = None):
    """
    Feature A: Remediation View via Cloudinary e_gen_remove.
    Removes defect region(s) and returns a signed, labeled URL.
    Requires Cloudinary credentials. Returns 503 when not configured.
    """
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if not cloudinary_configured():
        raise HTTPException(
            status_code=503,
            detail="Remediation View requires Cloudinary credentials. Set CLOUDINARY_* in .env."
        )

    finding_ids = body.finding_ids if body else None
    mode = (body.mode if body else "region") or "region"

    submode = "*"
    if job.calibration and hasattr(job.calibration, "encoding") and isinstance(job.calibration.encoding, dict):
        raw_m = job.calibration.encoding.get("mode", "*")
        submode = "materials" if "material" in raw_m.lower() else ("histology" if "histol" in raw_m.lower() else raw_m)

    # Resolve Cloudinary public_id
    cld_pid = job.assets.get("cld_public_id")
    if not cld_pid:
        raw_views = job.assets.get("views", {})
        raw_url = raw_views.get("raw", "") if isinstance(raw_views, dict) else ""
        if raw_url:
            for marker in ("/upload/", "/authenticated/"):
                if marker in raw_url:
                    try:
                        part = raw_url.split(marker)[-1].split("?")[0]
                        parts = part.split("/")
                        while parts and (parts[0].startswith("s--") or parts[0].startswith("v") and parts[0][1:].isdigit()):
                            parts = parts[1:]
                        cld_pid = "/".join(parts)
                        break
                    except Exception:
                        pass

    if not cld_pid:
        raise HTTPException(
            status_code=422,
            detail="Cannot resolve Cloudinary public_id. Re-upload with Cloudinary credentials configured."
        )

    try:
        url, allowed_findings, blocked = remediation_url(
            public_id=cld_pid,
            findings=job.findings,
            module=job.module,
            mode=submode,
            finding_ids=finding_ids,
            remove_mode=mode
        )
        readiness = check_remediation_readiness(url)

        # Fallback to local inpainting + Cloudinary upload if Cloudinary URL doesn't resolve
        if readiness == "failed":
            logger.info("Cloudinary e_gen_remove readiness check failed. Generating local inpainting + upload.")
            try:
                data_url, allowed_findings, blocked = generate_local_remediation(
                    job, finding_ids=finding_ids
                )
                b64_data = data_url.split(",", 1)[-1]
                rem_bytes = base64.b64decode(b64_data)
                rem_pid = upload_asset(
                    rem_bytes,
                    module_id=job.module,
                    job_id=f"{job_id}_remediation",
                    resource_type="image",
                    filename=f"{job_id}_remediation.png"
                )
                url = signed_url(rem_pid)
                readiness = "ready"
            except Exception as fb_err:
                logger.warning(f"Local remediation fallback upload failed: {fb_err}")

        # Record in job provenance
        if job.provenance:
            step_entry = {
                "step": "e_gen_remove",
                "feature": "remediation",
                "regions": [list(f.region_px) for f in allowed_findings],
                "purpose": "display only",
                "policy_version": "gen-policy-1",
                "asset": cld_pid,
                "findings_remediated": [f.id for f in allowed_findings]
            }
            prov_steps = getattr(job.provenance, "generative_steps", [])
            prov_steps.append(step_entry)

        return {
            "job_id": job_id,
            "status": readiness,
            "remediation_url": url,
            "label": "AI-generated illustration (display only)",
            "allowed_finding_ids": [f.id for f in allowed_findings],
            "blocked_findings": [{"id": f.id, "label": f.label, "reason": r} for f, r in blocked],
            "cloudinary": True,
        }
    except PermissionError as pe:
        raise HTTPException(status_code=403, detail=str(pe))
    except Exception as e:

        logger.error(f"Remediation error for {job_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Remediation failed: {e}")


@app.get("/sim/models")
async def list_simulation_models():
    """
    Feature B: Returns allowlisted simulation model families and tiers
    based on server verification and config.
    """
    return {
        "models": get_allowed_models(),
        "scenarios": SIMULATION_SCENARIOS,
        "default_tier": settings.SIM_DEFAULT_TIER,
        "allow_premium": settings.SIM_ALLOW_PREMIUM
    }

@app.post("/jobs/{job_id}/simulations")
async def trigger_simulation(
    job_id: str,
    body: SimulationRequest,
    background_tasks: BackgroundTasks
):
    """
    Feature B: Simulation Lab via Cloudinary Image Generation API.
    Enqueues an async multi-variant simulation using image-to-image generation.
    Requires Cloudinary credentials + IMAGE_GEN_BASE. Returns 503 when not configured.
    """
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if not cloudinary_configured():
        raise HTTPException(
            status_code=503,
            detail="Simulation Lab requires Cloudinary credentials. Set CLOUDINARY_* in .env."
        )

    # 1. Validate scenario exists in catalog
    if body.scenario not in SIMULATION_SCENARIOS:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown scenario '{body.scenario}'. Must be one of {list(SIMULATION_SCENARIOS.keys())}"
        )

    # 2. Validate policy for this module/mode and scenario
    submode = "*"
    if job.calibration and hasattr(job.calibration, "encoding") and isinstance(job.calibration.encoding, dict):
        submode = job.calibration.encoding.get("mode", "*")

    allowed, reason = policy_allows_simulation(job.module, mode=submode, scenario=body.scenario)
    if not allowed:
        raise HTTPException(status_code=403, detail=f"Policy restriction: {reason}")

    # 3. Validate model against server allowlist
    allowed_models = [m["id"] for m in get_allowed_models()]
    if body.model not in allowed_models:
        raise HTTPException(
            status_code=422,
            detail=f"Model '{body.model}' is not in the allowlist. Allowed: {allowed_models}"
        )

    # 4. Validate variants cap
    if body.variants < 1 or body.variants > 3:
        raise HTTPException(status_code=422, detail="Variants must be between 1 and 3.")

    # 5. Resolve Cloudinary public_id for image reference
    cld_pid = job.assets.get("cld_public_id")

    # 6. Create simulation record & enqueue worker
    sim_rec = create_simulation_record(
        job_id=job_id,
        scenario=body.scenario,
        severity=body.severity,
        model_id=body.model,
        variants=body.variants
    )
    # Attach resolved public_id so run_simulation_job can build a proper reference URL
    if cld_pid:
        sim_rec["cld_public_id"] = cld_pid

    background_tasks.add_task(
        run_simulation_job,
        sim_rec["id"],
        job,
        body.scenario,
        body.severity,
        body.model,
        body.variants,
        body.user_note
    )

    return sim_rec

@app.get("/simulations/{sim_id}")
async def get_simulation_status(sim_id: str):
    """Returns live status, metadata, and generated variant URLs for a simulation."""
    sim = get_simulation(sim_id)
    if not sim:
        raise HTTPException(status_code=404, detail="Simulation not found")
    return sim

@app.get("/jobs/{job_id}/simulations")
async def list_simulations_for_job(job_id: str):
    """Lists all historical and current simulation runs linked to the parent job."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    sims = list_job_simulations(job_id)
    return {"job_id": job_id, "simulations": sims}

@app.get("/jobs/{job_id}/events")
async def job_events_stream(job_id: str):
    """Server-Sent Events (SSE) stream for live stage progression."""
    return StreamingResponse(
        job_event_generator(job_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

@app.post("/jobs/run-local")
async def run_local_job(
    background_tasks: BackgroundTasks,
    module: str = Form("thermal"),
    file: UploadFile = File(...),
):
    """
    Direct upload endpoint. When Cloudinary credentials are configured:
    - Image/audio files are uploaded to Cloudinary immediately.
    - Raw data files (CSV/TSV thermal matrices) cannot be uploaded as images;
      the pipeline renders them to PNG first, then uploads the render to Cloudinary.
    Without credentials, falls back to local Python rendering for dev.
    """
    content = await file.read()
    job_id = f"local_{int(time.time() * 1000)}"
    fname_lower = (file.filename or "").lower()
    resource_type = "video" if module == "audio" else "image"

    # Raw data files (CSV/TSV) can't be uploaded as images — defer to pipeline
    is_raw_data = fname_lower.endswith((".csv", ".tsv", ".txt")) and module == "thermal"

    public_id: str
    if cloudinary_configured() and not is_raw_data:
        try:
            real_pid = upload_asset(
                file_bytes=content,
                module_id=module,
                job_id=job_id,
                resource_type=resource_type,
                filename=file.filename,
            )
            logger.info(f"[run-local] Cloudinary upload succeeded: {real_pid}")
            public_id = real_pid
        except Exception as upload_err:
            logger.error(f"[run-local] Cloudinary upload failed: {upload_err}")
            raise HTTPException(
                status_code=502,
                detail=f"Cloudinary upload failed: {upload_err}. Check CLOUDINARY_* credentials.",
            )
    else:
        # Placeholder id — execute_direct_analysis will upload the rendered image
        public_id = f"spectrotrace/{module}/{job_id}"
        if is_raw_data:
            logger.info(f"[run-local] CSV/raw data file — render-first upload deferred to pipeline.")
        else:
            logger.warning("[run-local] Cloudinary not configured — using local rendering fallback.")

    create_or_get_job(job_id, module=module, cld_public_id=public_id)
    background_tasks.add_task(
        execute_direct_analysis,
        job_id,
        module,
        public_id,
        content,
        file.filename,
    )
    return {"job_id": job_id, "status": "queued", "cloudinary": cloudinary_configured()}


@app.get("/history")
async def get_history(module: Optional[str] = None, risk: Optional[str] = None):
    """
    Retrieves history and review queue. Queries Cloudinary Search API when configured,
    or falls back to in-memory jobs.
    """
    if settings.CLOUDINARY_API_KEY and settings.CLOUDINARY_API_SECRET:
        try:
            return search_runs(module=module, risk=risk)
        except Exception as e:
            logger.warning(f"Search API error: {e}. Falling back to local store.")
    
    # Fallback to local jobs
    all_jobs = list_jobs()
    if module:
        all_jobs = [j for j in all_jobs if j.module == module]
    if risk:
        all_jobs = [j for j in all_jobs if j.risk_level == risk]
    return {"resources": [j.model_dump() for j in all_jobs]}

async def execute_direct_analysis(
    job_id: str,
    module_id: str,
    public_id: str,
    raw_bytes: bytes,
    filename: str
):
    """
    Pipeline execution for direct uploads.
    When Cloudinary is configured (public_id is a real CLD id), all views are
    constructed as Cloudinary AI transform URLs — no local PIL/OpenCV rendering.
    Without credentials, falls back to base64 local rendering for dev.
    """
    use_cld = cloudinary_configured()
    # actual_cld_pid tracks the real uploaded public_id — may differ from the
    # initial placeholder assigned to CSV/raw-data files before rendering.
    actual_cld_pid = public_id

    def upload_render_if_needed(pil_img: "Image.Image", job_id: str, module: str) -> str:
        """
        Upload a rendered PIL image to Cloudinary when the initial public_id was a
        placeholder (e.g. for CSV thermal files that can't be uploaded as images directly).
        Returns the real public_id after upload.
        """
        nonlocal actual_cld_pid
        import io as _io
        buf = _io.BytesIO()
        pil_img.save(buf, format="PNG")
        try:
            real_pid = upload_asset(
                file_bytes=buf.getvalue(),
                module_id=module,
                job_id=job_id,
                resource_type="image",
                filename=f"{job_id}_render.png",
            )
            actual_cld_pid = real_pid
            logger.info(f"[pipeline] Deferred render uploaded to Cloudinary: {real_pid}")
            return real_pid
        except Exception as up_err:
            logger.error(f"[pipeline] Deferred render upload failed: {up_err}")
            return actual_cld_pid

    def make_views(
        render_img=None,
        findings=None,
        cal=None,
        clean_img=None,
        resource_type="image",
        heatmap_img=None,
        spectrogram_img=None,
        waveform_img=None,
    ):
        """Build view URL dict — Cloudinary AI transforms when configured, base64 locally."""
        from PIL import Image as _PILImage
        p_render = render_img
        if p_render is not None and not hasattr(p_render, 'save'):
            p_render = _PILImage.fromarray(np.array(p_render))
        p_heat = heatmap_img
        if p_heat is not None and not hasattr(p_heat, 'save'):
            p_heat = _PILImage.fromarray(np.array(p_heat))
        p_spec = spectrogram_img
        if p_spec is not None and not hasattr(p_spec, 'save'):
            p_spec = _PILImage.fromarray(np.array(p_spec))
        p_wave = waveform_img
        if p_wave is not None and not hasattr(p_wave, 'save'):
            p_wave = _PILImage.fromarray(np.array(p_wave))

        if use_cld:
            return build_all_views(
                public_id=actual_cld_pid,
                module_id=module_id,
                findings=findings,
                calibration=cal,
                resource_type=resource_type,
                render_img=p_render,
                heatmap_img=p_heat,
                spectrogram_img=p_spec,
                waveform_img=p_wave,
            )

        # Local fallback (dev without Cloudinary)
        raw_b64 = pil_to_b64(p_render) if p_render is not None else ""
        ann_b64 = draw_annotated_b64(p_render, findings) if p_render is not None else ""
        cln_b64 = pil_to_b64(clean_img if clean_img is not None else p_render) if p_render is not None else ""
        return {"raw": raw_b64, "annotated": ann_b64, "clean": cln_b64}

    # Store cld_public_id so export/remediation endpoints can resolve it without parsing URLs
    job_ref = get_job(job_id)
    if job_ref and use_cld:
        job_ref.assets["cld_public_id"] = public_id

    try:
        update_job_stage(job_id, "encoding")
        time.sleep(0.1)

        update_job_stage(job_id, "measuring")
        is_csv = filename.lower().endswith(".csv")

        if module_id == "thermal":
            findings, cal, render_img, stats, prov = process_thermal_pipeline(
                raw_bytes, is_csv=is_csv
            )

            update_job_stage(job_id, "vision")
            time.sleep(0.1)
            update_job_stage(job_id, "publishing")

            high_count = sum(1 for f in findings if f.risk_level == "high")
            overall_risk = "high" if high_count > 0 else ("medium" if findings else "low")
            risk_score = min(100, int(stats.get("total_heat_loss_index", 0) * 2))

            job = get_job(job_id)
            if job:
                job.calibration = cal
                job.findings = findings
                job.provenance = prov
                job.risk_level = overall_risk
                job.risk_score = risk_score
                if use_cld:
                    # For CSV thermal files: render_img is produced locally but was never
                    # uploaded to Cloudinary. Upload it now so all view URLs resolve.
                    if actual_cld_pid == public_id:  # still the placeholder
                        upload_render_if_needed(render_img, job_id, module_id)
                    job.assets["cld_public_id"] = actual_cld_pid
                    job.assets["views"] = make_views(render_img, findings, cal)
                else:
                    render_arr = np.array(render_img)
                    blurred_arr = cv2.GaussianBlur(render_arr, (15, 15), 0)
                    clean_img = Image.fromarray(blurred_arr)
                    job.assets["views"] = make_views(render_img, findings, cal, clean_img=clean_img)

            finish_job(
                job_id, status="done",
                summary=f"Identified {len(findings)} thermal anomalies. Max temp: {stats.get('max_temp_c')}°C."
            )

        elif module_id == "audio":
            findings, cal, vision_img, human_spec, waveform, stats, prov = process_audio_pipeline(
                raw_bytes
            )

            update_job_stage(job_id, "vision")
            time.sleep(0.1)
            update_job_stage(job_id, "publishing")

            high_count = sum(1 for f in findings if f.risk_level == "high")
            overall_risk = "high" if high_count > 0 else ("medium" if findings else "low")
            risk_score = 80 if stats.get("hum_detected") else (50 if findings else 10)

            ext = (filename or "").lower().rsplit(".", 1)[-1]
            mime_map = {"wav": "audio/wav", "mp3": "audio/mpeg", "ogg": "audio/ogg",
                        "flac": "audio/flac", "aac": "audio/aac", "m4a": "audio/mp4"}
            audio_mime = mime_map.get(ext, "audio/wav")
            audio_b64_src = f"data:{audio_mime};base64," + base64.b64encode(raw_bytes).decode()

            spec_img = human_spec if human_spec is not None else vision_img
            if spec_img is not None and not hasattr(spec_img, 'save'):
                spec_img = Image.fromarray(np.array(spec_img))

            job = get_job(job_id)
            if job:
                job.calibration = cal
                job.findings = findings
                job.provenance = prov
                job.risk_level = overall_risk
                job.risk_score = risk_score
                job.assets["audio_src"] = audio_b64_src

                if use_cld:
                    views = make_views(
                        render_img=spec_img,
                        findings=findings,
                        cal=cal,
                        resource_type="video",
                        spectrogram_img=spec_img,
                        waveform_img=waveform,
                    )
                    job.assets["views"] = views
                    job.assets["spectrogram"] = views.get("raw") or views.get("waveform", "")

                else:
                    spec_render = spec_img
                    job.assets["waveform_b64"] = pil_to_b64(waveform) if waveform is not None else ""
                    job.assets["spectrogram"] = pil_to_b64(spec_render) if spec_render is not None else ""
                    job.assets["views"] = {
                        "raw": pil_to_b64(spec_render) if spec_render is not None else "",
                        "annotated": draw_annotated_b64(
                            vision_img if vision_img is not None else spec_render, findings
                        ) if (vision_img is not None or spec_render is not None) else "",
                        "clean": pil_to_b64(human_spec if human_spec is not None else spec_render) if (human_spec is not None or spec_render is not None) else "",
                    }

            finish_job(
                job_id, status="done",
                summary=f"Forensic audio analysis: {len(findings)} anomalies detected. Hum: {stats.get('hum_detected')}, SNR: {stats.get('snr_db')} dB."
            )

        elif module_id == "print":
            findings, cal, original_img, heatmap_img, stats, prov = process_print_pipeline(raw_bytes)

            update_job_stage(job_id, "vision")
            time.sleep(0.1)
            update_job_stage(job_id, "publishing")

            high_count = sum(1 for f in findings if f.risk_level == "high")
            overall_risk = "high" if high_count > 0 or stats.get("print_halt_recommended") else ("medium" if findings else "low")
            risk_score = stats.get("severity_score", 0)

            job = get_job(job_id)
            if job:
                job.calibration = cal
                job.findings = findings
                job.provenance = prov
                job.risk_level = overall_risk
                job.risk_score = risk_score
                if use_cld:
                    # Cloudinary: annotated, gen_restore clean, tint heatmap, background_removal, upscaled
                    job.assets["cld_public_id"] = actual_cld_pid
                    job.assets["views"] = make_views(original_img, findings, cal, heatmap_img=heatmap_img)
                else:
                    orig_pil = Image.fromarray(original_img)
                    heat_rgba = heatmap_img if heatmap_img.mode == "RGBA" else heatmap_img.convert("RGBA")
                    heat_rgba = heat_rgba.resize(orig_pil.size, Image.LANCZOS)
                    composite = orig_pil.copy().convert("RGB")
                    composite.paste(heat_rgba, mask=heat_rgba.split()[3])
                    job.assets["views"] = {
                        "raw": pil_to_b64(orig_pil),
                        "annotated": draw_annotated_b64(composite, findings),
                        "clean": pil_to_b64(composite),
                    }

            finish_job(
                job_id, status="done",
                summary=f"Layer {stats.get('layer_index')}: {len(findings)} defects detected. Halt recommended: {stats.get('print_halt_recommended')}."
            )

        elif module_id == "specimen":
            fname_l = (filename or "").lower()
            spec_mode = "materials" if any(k in fname_l for k in ("metal", "crack", "void", "micro", "mat", "weld", "alloy", "steel")) else "histology"
            findings, cal, norm_img, stats, prov = process_specimen_pipeline(raw_bytes, sub_mode=spec_mode)
            if cal and hasattr(cal, "encoding") and isinstance(cal.encoding, dict):
                cal.encoding["mode"] = spec_mode

            update_job_stage(job_id, "vision")
            time.sleep(0.1)
            update_job_stage(job_id, "publishing")

            high_count = sum(1 for f in findings if f.risk_level == "high")
            overall_risk = "high" if high_count > 0 else ("medium" if findings else "low")
            risk_score = min(100, len(findings) * 10)

            job = get_job(job_id)
            if job:
                job.calibration = cal
                job.findings = findings
                job.provenance = prov
                job.risk_level = overall_risk
                job.risk_score = risk_score
                if use_cld:
                    job.assets["cld_public_id"] = actual_cld_pid
                    job.assets["views"] = make_views(norm_img, findings, cal)
                else:
                    job.assets["views"] = make_views(norm_img, findings, cal)

            finish_job(
                job_id, status="done",
                summary=f"Specimen analysis ({stats.get('mode')}): {len(findings)} findings. Density: {stats.get('cellular_density_per_mm2', 0)}/mm²."
            )


        else:
            finish_job(job_id, status="failed", error=f"Module {module_id} not yet supported.")

    except Exception as e:
        logger.error(f"Job {job_id} failed: {e}", exc_info=True)
        finish_job(job_id, status="failed", error=str(e))

async def run_analysis_pipeline(job_id: str, module_id: str, public_id: str, payload: Dict[str, Any]):
    """Background task handler for Cloudinary webhook-triggered jobs."""
    # In webhook path, fetch original asset and run analysis
    update_job_stage(job_id, "encoding")
    # Will download signed asset from Cloudinary and run module pipeline
    logger.info(f"Pipeline started for {job_id} on asset {public_id}")
