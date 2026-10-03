#!/usr/bin/env python3
"""
SpectroTrace AI — Demo Set Pre-Generation & Caching Script (Phase 6)
Pre-generates and caches inspection runs, export profiles, remediation views,
and simulation lab variants for all 4 industrial inspection domains.

Enables seamless presentation during live demonstrations and offline demo mode.
"""

import os
import sys
import json
import time
from pathlib import Path
from typing import Dict, Any
import requests

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

ROOT_DIR = Path(__file__).resolve().parent.parent
API_BASE = "http://localhost:8000"
DOCS_DIR = ROOT_DIR / "docs"

DEMO_RUNS = [
    {
        "module": "print",
        "file": ROOT_DIR / "samples" / "print" / "layer_with_defect.png",
        "mime": "image/png",
        "demo_title": "3D Print Layer Analysis — Micro-Defect & Remediation",
        "features": {
            "remediation": True,
            "simulation": {"scenario": "corrosion", "severity": 3, "variants": 2},
            "export": {"profile": "slide_16x9", "fill": "solid"}
        }
    },
    {
        "module": "thermal",
        "file": ROOT_DIR / "samples" / "thermal" / "sample_radiometric_matrix.csv",
        "mime": "text/csv",
        "demo_title": "Radiometric Thermal Inspection — Transformer & HVAC",
        "features": {
            "remediation": False,  # Blocked by radiometric policy
            "simulation": {"scenario": "weathering", "severity": 2, "variants": 1},
            "export": {"profile": "slide_16x9", "fill": "blur"}
        }
    },
    {
        "module": "specimen",
        "file": ROOT_DIR / "samples" / "specimen" / "sample_he_patch.png",
        "mime": "image/png",
        "demo_title": "Materials / Histology Specimen — Microstructure",
        "features": {
            "remediation": True,
            "simulation": None,  # Blocked on histology
            "export": {"profile": "square_1x1", "fill": "blur"}
        }
    },
    {
        "module": "audio",
        "file": ROOT_DIR / "samples" / "audio" / "sample_forensic_audio.wav",
        "mime": "audio/wav",
        "demo_title": "Forensic Acoustic Signal — Bearing & Electrical Hum",
        "features": {
            "remediation": False,  # Blocked by spectrogram policy
            "simulation": None,   # Blocked by policy
            "export": {"profile": "mobile_9x16", "fill": "solid"}
        }
    }
]

def check_server() -> bool:
    try:
        r = requests.get(f"{API_BASE}/healthz", timeout=3)
        return r.status_code == 200
    except Exception:
        return False

def main():
    print("================================================================")
    print("       SpectroTrace AI — Demo Caching & Pre-warming (Phase 6)    ")
    print("================================================================")

    if not check_server():
        print(f"❌ Server at {API_BASE} is not reachable. Launch FastAPI first:")
        print("   python -m uvicorn api.main:app --reload --port 8000")
        sys.exit(1)

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    manifest = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%SZ", time.gmtime()),
        "env": "demo",
        "runs": []
    }

    for item in DEMO_RUNS:
        filepath = item["file"]
        module = item["module"]
        print(f"\n🚀 Processing Demo Run: [{module.upper()}] {item['demo_title']}")

        if not filepath.exists():
            print(f"  ⚠️ Sample file not found: {filepath}. Skipping.")
            continue

        with open(filepath, "rb") as f:
            files = {"file": (filepath.name, f.read(), item["mime"])}
            data = {"module": module}
            res = requests.post(f"{API_BASE}/jobs/run-local", files=files, data=data)

        if res.status_code != 200:
            print(f"  ❌ Job creation failed: {res.text}")
            continue

        job_id = res.json()["job_id"]
        print(f"  ✓ Job registered: {job_id}. Waiting for analysis pipeline...")

        # Poll until done
        job_done = False
        for _ in range(25):
            time.sleep(0.4)
            j_resp = requests.get(f"{API_BASE}/jobs/{job_id}").json()
            if j_resp.get("status") in ("done", "done_partial"):
                job_done = True
                break

        if not job_done:
            print(f"  ❌ Job processing timed out.")
            continue

        findings_count = len(j_resp.get("findings", []))
        print(f"  ✓ Pipeline complete: {findings_count} findings, risk: {j_resp.get('risk_level')}")

        run_manifest: Dict[str, Any] = {
            "job_id": job_id,
            "module": module,
            "title": item["demo_title"],
            "risk_level": j_resp.get("risk_level"),
            "risk_score": j_resp.get("risk_score"),
            "findings_count": findings_count,
            "cached_features": {}
        }

        # 1. Pre-warm Remediation View
        if item["features"].get("remediation"):
            print("  ⏳ Pre-warming Feature A: Remediation View...")
            rem_resp = requests.post(f"{API_BASE}/jobs/{job_id}/remediation")
            if rem_resp.status_code == 200:
                rem_data = rem_resp.json()
                run_manifest["cached_features"]["remediation"] = {
                    "status": rem_data.get("status"),
                    "allowed_findings": rem_data.get("allowed_finding_ids"),
                    "label": rem_data.get("label"),
                    "cached": True
                }
                print(f"    ✓ Remediation ready ({len(rem_data.get('allowed_finding_ids', []))} regions infilled)")
            else:
                print(f"    ⚠️ Remediation policy note: {rem_resp.status_code} {rem_resp.text}")

        # 2. Pre-warm Simulation Lab
        sim_cfg = item["features"].get("simulation")
        if sim_cfg:
            print(f"  ⏳ Pre-warming Feature B: Simulation Lab ({sim_cfg['scenario']})...")
            sim_req = {
                "scenario": sim_cfg["scenario"],
                "severity": sim_cfg["severity"],
                "model": "auto",
                "variants": sim_cfg["variants"],
                "user_note": "Demo Pre-warmed Scenario"
            }
            sim_resp = requests.post(f"{API_BASE}/jobs/{job_id}/simulations", json=sim_req)
            if sim_resp.status_code == 200:
                sim_id = sim_resp.json()["id"]
                # Poll simulation
                for _ in range(30):
                    time.sleep(0.4)
                    s_data = requests.get(f"{API_BASE}/simulations/{sim_id}").json()
                    if s_data.get("status") in ("done", "done_partial"):
                        run_manifest["cached_features"]["simulation"] = {
                            "sim_id": sim_id,
                            "scenario": sim_cfg["scenario"],
                            "variants": len(s_data.get("variants", [])),
                            "model_used": s_data.get("model_used"),
                            "status": s_data.get("status")
                        }
                        print(f"    ✓ Simulation ready ({len(s_data.get('variants', []))} variants, model: {s_data.get('model_used')})")
                        break
            else:
                print(f"    ⚠️ Simulation policy response: {sim_resp.status_code}")

        # 3. Pre-warm Export Profile
        exp_cfg = item["features"].get("export")
        if exp_cfg:
            print(f"  ⏳ Pre-warming Feature C: Export Profile ({exp_cfg['profile']})...")
            exp_resp = requests.get(
                f"{API_BASE}/jobs/{job_id}/exports",
                params={"profile": exp_cfg["profile"], "fill": exp_cfg["fill"], "annotated": "true"}
            )
            if exp_resp.status_code == 200:
                run_manifest["cached_features"]["export"] = {
                    "profile": exp_cfg["profile"],
                    "fill": exp_cfg["fill"],
                    "cached": True
                }
                print(f"    ✓ Export presentation ready ({exp_cfg['profile']})")

        manifest["runs"].append(run_manifest)

    # Save manifest
    manifest_path = DOCS_DIR / "demo_cache_manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print("\n================================================================")
    print(f"✅ Demo cache generated successfully! Manifest saved to:")
    print(f"   {manifest_path}")
    print("================================================================")

if __name__ == "__main__":
    main()
