"""
Feature B Acceptance Tests — Simulation Lab (Phase 4)
Tests:
1. Static guard: analysis modules NEVER import imagegen.
2. Model allowlist: server rejects unknown model families with 422.
3. Policy enforcement: blocks histology, audio, and thermal radiometric renders.
4. Deterministic prompt builder and input sanitation.
5. Edge-map fidelity SSIM metric.
6. Simulation state machine, multi-variant generation, and metadata linking.
"""

import os
import glob
import io
import time
import base64
import pytest
import numpy as np
import cv2
from PIL import Image
from fastapi.testclient import TestClient

from api.main import app
from api.core.schema import JobResult, Finding
from api.core.jobs import create_or_get_job
from api.core.imagegen import (
    get_allowed_models,
    sanitize_text,
    build_simulation_prompt,
    measure_edge_fidelity_ssim,
    apply_simulation_synthesis,
    run_simulation_job,
    create_simulation_record,
    get_simulation,
    PROMPT_VERSION,
)
from api.core.gen_policy import policy_allows_simulation, SIMULATION_SCENARIOS

client = TestClient(app)


def test_static_guard_no_analysis_import():
    """
    Integrity Rule: Analysis packages must NEVER import imagegen.
    Simulation outputs must never feed back into CV, vision, or deterministic measurement.
    """
    modules_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "modules"))
    core_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "core"))

    files_to_check = glob.glob(os.path.join(modules_dir, "*.py"))
    files_to_check.append(os.path.join(core_dir, "vision.py"))
    files_to_check.append(os.path.join(core_dir, "calibration.py"))

    for filepath in files_to_check:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
            assert "imagegen" not in content, (
                f"Violation of integrity invariant: {os.path.basename(filepath)} imports imagegen!"
            )


def test_model_allowlist():
    """Verifies that only server-allowlisted model families can be requested."""
    models = get_allowed_models()
    model_ids = [m["id"] for m in models]
    assert "auto" in model_ids
    assert "flux" in model_ids

    # Unverified models outside allowlist must not appear
    assert "dall-e-3" not in model_ids
    assert "midjourney" not in model_ids


def test_prompt_sanitization_and_template():
    """Validates prompt construction, length limiting, and malicious character removal."""
    dirty_note = "Check this http://malicious.org/hack?p=1; DROP TABLE users; \n\n newline"
    clean_note = sanitize_text(dirty_note, max_len=80)
    assert "http" not in clean_note
    assert "\n" not in clean_note
    assert "DROP TABLE" in clean_note

    job = JobResult(
        job_id="test_sim_prompt",
        module="print",
        status="done",
        findings=[]
    )

    prompt, version = build_simulation_prompt(
        job,
        scenario_id="corrosion",
        severity=4,
        user_note="saline environment"
    )

    assert "heavy rust and oxidation" in prompt
    assert "3D-printed" in prompt
    assert "saline environment" in prompt
    assert version == PROMPT_VERSION


def test_policy_simulation_rejection():
    """Ensures medical histology, audio, and thermal radiometric thermograms are rejected."""
    # Audio rejected
    allowed_aud, reason_aud = policy_allows_simulation("audio", scenario="corrosion")
    assert allowed_aud is False
    assert "audio" in reason_aud.lower()

    # Histology specimen rejected
    allowed_hist, reason_hist = policy_allows_simulation("specimen", mode="histology", scenario="corrosion")
    assert allowed_hist is False
    assert "histology" in reason_hist.lower()

    # Materials specimen allowed
    allowed_mat, _ = policy_allows_simulation("specimen", mode="materials", scenario="corrosion")
    assert allowed_mat is True

    # Thermal visible allowed, radiometric denied
    allowed_therm_vis, _ = policy_allows_simulation("thermal", mode="visible", scenario="humidity")
    assert allowed_therm_vis is True

    allowed_therm_rad, reason_therm = policy_allows_simulation("thermal", mode="radiometric", scenario="humidity")
    assert allowed_therm_rad is False
    assert "radiometric" in reason_therm.lower()


def test_edge_fidelity_ssim():
    """
    Section 7.8 Acceptance Test: Edge-map SSIM between original and simulated.
    """
    orig_img = np.full((200, 200, 3), 128, dtype=np.uint8)
    cv2.rectangle(orig_img, (40, 40), (160, 160), (255, 255, 255), 2)

    # Identical image edge SSIM should be 1.0
    ssim_perfect = measure_edge_fidelity_ssim(orig_img, orig_img)
    assert ssim_perfect >= 0.99

    # Add light corrosion synthesis
    pil_orig = Image.fromarray(orig_img)
    pil_sim = apply_simulation_synthesis(pil_orig, scenario="corrosion", severity=3)
    sim_arr = np.array(pil_sim)

    # The prominent rectangle edges should remain preserved in edge map
    ssim_sim = measure_edge_fidelity_ssim(orig_img, sim_arr)
    assert ssim_sim > 0.60, f"Expected geometric edge fidelity preservation, got SSIM {ssim_sim}"


def test_simulation_api_endpoints():
    """
    End-to-end endpoint tests: /sim/models, POST /jobs/{id}/simulations, GET /simulations/{id}.
    Without Cloudinary credentials, POST returns 503 (Cloudinary required — correct behaviour).
    With Cloudinary, full scenario/model/variant validation and async simulation run.
    """
    from api.core.cloudinary_client import cloudinary_configured

    # 1. Models endpoint always works (no credentials required)
    m_resp = client.get("/sim/models")
    assert m_resp.status_code == 200
    m_data = m_resp.json()
    assert "models" in m_data
    assert "scenarios" in m_data
    assert "corrosion" in m_data["scenarios"]

    # 2. Setup job
    job_id = "test_sim_api_job"
    img = Image.new("RGB", (200, 200), color=(100, 100, 120))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64_img = f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode()}"

    job = create_or_get_job(job_id, module="print", cld_public_id="sample_pid")
    job.assets["views"] = {"raw": b64_img}
    job.assets["cld_public_id"] = "spectrotrace/print/test_sim_api_job"

    if not cloudinary_configured():
        # Without Cloudinary credentials, POST /simulations returns 503
        no_cld_resp = client.post(
            f"/jobs/{job_id}/simulations",
            json={"scenario": "corrosion", "severity": 3, "model": "auto"}
        )
        assert no_cld_resp.status_code == 503
        assert "Cloudinary" in no_cld_resp.json()["detail"]
        return  # Skip Cloudinary-dependent assertions in CI

    # 3. Trigger simulation with invalid model -> 422
    bad_model_resp = client.post(
        f"/jobs/{job_id}/simulations",
        json={"scenario": "corrosion", "severity": 3, "model": "invalid-huggingface-model"}
    )
    assert bad_model_resp.status_code == 422

    # 4. Trigger simulation on disallowed scenario -> 422
    bad_sc_resp = client.post(
        f"/jobs/{job_id}/simulations",
        json={"scenario": "earthquake_collapse", "severity": 3, "model": "auto"}
    )
    assert bad_sc_resp.status_code == 422

    # 5. Trigger valid simulation
    sim_resp = client.post(
        f"/jobs/{job_id}/simulations",
        json={"scenario": "corrosion", "severity": 3, "model": "auto", "variants": 2}
    )
    assert sim_resp.status_code == 200
    sim_data = sim_resp.json()
    sim_id = sim_data["id"]
    assert sim_data["status"] == "queued"
    assert sim_data["scenario"] == "corrosion"

    status_resp = client.get(f"/simulations/{sim_id}")
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert status_data["status"] in ("done", "done_partial", "failed", "generating")

    # 6. List simulations for job
    list_resp = client.get(f"/jobs/{job_id}/simulations")
    assert list_resp.status_code == 200
    assert len(list_resp.json()["simulations"]) >= 1

