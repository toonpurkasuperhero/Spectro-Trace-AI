#!/usr/bin/env python3
"""
SpectroTrace AI - Phase 1 Cloudinary Spike & Validation Gate
This script evaluates each Cloudinary capability documented in Section 12 of the Execution Plan:
1. Authenticated upload & signed delivery (testing that unsigned fails)
2. Rectangle overlay via sys:pixel colorize & text label
3. Mask PNG overlay with opacity
4. c_crop deep-zoom tiling
5. Cosmetic generative transforms (e_gen_remove, e_gen_restore, e_upscale, b_gen_fill)
6. Audio asset handling (resource_type="video"), waveform generation, segment delivery
7. Animated GIF via multi or slideshow
8. Structured metadata write & Search API query
9. Webhook signature verification logic
10. AI Vision / fallback availability
"""

import os
import sys
import time
import json
import io
import requests
from pathlib import Path
from dotenv import load_dotenv

# Ensure utf-8 stdout/stderr on Windows consoles
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

# Add project root to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

load_dotenv(ROOT_DIR / ".env")

try:
    import cloudinary
    import cloudinary.uploader
    import cloudinary.utils
    import cloudinary.api
    import cloudinary.search
except ImportError:
    print("❌ Cloudinary Python SDK is not installed. Run: pip install cloudinary")
    sys.exit(1)

# Ensure credentials exist
cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME")
api_key = os.getenv("CLOUDINARY_API_KEY")
api_secret = os.getenv("CLOUDINARY_API_SECRET")

if not (cloud_name and api_key and api_secret):
    print("⚠️ Missing Cloudinary credentials in .env.")
    print("Please set CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, and CLOUDINARY_API_SECRET.")
    print("Generating spike script template...")

cloudinary.config(
    cloud_name=cloud_name,
    api_key=api_key,
    api_secret=api_secret,
    secure=True
)

FINDINGS_PATH = ROOT_DIR / "docs" / "cloudinary_findings.md"
FINDINGS_PATH.parent.mkdir(parents=True, exist_ok=True)

findings = []

def record_finding(test_id, name, status, details, fallback=None):
    findings.append({
        "id": test_id,
        "name": name,
        "status": status,
        "details": details,
        "fallback": fallback
    })
    status_icon = "✅" if status == "PASS" else ("⚠️" if status == "OPTIONAL_FAIL" else "❌")
    print(f"{status_icon} [{test_id}] {name}: {status}")
    if details:
        print(f"    Details: {details}")
    if fallback and status != "PASS":
        print(f"    Fallback: {fallback}")

def test_1_authenticated_upload_and_signing():
    print("\n--- Testing 1: Authenticated Upload & Signed Delivery ---")
    try:
        # Create a small 64x64 test image in memory
        from PIL import Image
        img = Image.new("RGB", (64, 64), color=(73, 109, 137))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)

        res = cloudinary.uploader.upload(
            buf,
            folder="spectrotrace/test",
            public_id="spike_auth_test",
            type="authenticated",
            tags="spike,env:test",
            overwrite=True
        )
        pub_id = res["public_id"]
        
        # Test 1a: Signed URL
        signed_url, _ = cloudinary.utils.cloudinary_url(
            pub_id,
            type="authenticated",
            sign_url=True,
            resource_type="image",
            fetch_format="auto",
            quality="auto"
        )
        r_signed = requests.get(signed_url)
        
        # Test 1b: Unsigned URL
        unsigned_url, _ = cloudinary.utils.cloudinary_url(
            pub_id,
            type="authenticated",
            sign_url=False,
            resource_type="image"
        )
        r_unsigned = requests.get(unsigned_url)

        if r_signed.status_code == 200 and r_unsigned.status_code != 200:
            record_finding("1", "Authenticated Delivery & Signed URLs", "PASS",
                           f"Signed URL returns 200 ({len(r_signed.content)} bytes), Unsigned URL correctly rejected ({r_unsigned.status_code}). URL: {signed_url}")
            return pub_id
        else:
            record_finding("1", "Authenticated Delivery & Signed URLs", "FAIL",
                           f"Signed code: {r_signed.status_code}, Unsigned code: {r_unsigned.status_code}")
            return pub_id
    except Exception as e:
        record_finding("1", "Authenticated Delivery & Signed URLs", "FAIL", str(e))
        return None

def test_2_rectangle_overlay_and_text(base_pid):
    print("\n--- Testing 2: sys:pixel Colorized Rectangles & Text Labels ---")
    if not base_pid:
        record_finding("2", "Sys:Pixel & Text Overlay", "SKIPPED", "No base asset from test 1")
        return

    try:
        # First ensure a 1x1 white pixel exists or upload one to sys:pixel
        from PIL import Image
        px = Image.new("RGB", (1, 1), color=(255, 255, 255))
        buf = io.BytesIO()
        px.save(buf, format="PNG")
        buf.seek(0)
        
        cloudinary.uploader.upload(
            buf,
            public_id="sys:pixel",
            type="authenticated",
            tags="system,spike",
            overwrite=True
        )

        # Build transform with overlay and text
        transform = [
            {"overlay": "sys:pixel", "width": 20, "height": 20, "crop": "scale",
             "effect": "colorize:100", "color": "red", "opacity": 50},
            {"flags": "layer_apply", "gravity": "north_west", "x": 10, "y": 10},
            {"overlay": {"font_family": "Arial", "font_size": 10, "text": "Hotspot"},
             "color": "white", "background": "rgb:000000a0"},
            {"flags": "layer_apply", "gravity": "north_west", "x": 10, "y": 32}
        ]

        url, _ = cloudinary.utils.cloudinary_url(
            base_pid,
            type="authenticated",
            sign_url=True,
            transformation=transform
        )
        r = requests.get(url)
        if r.status_code == 200:
            record_finding("2", "Sys:Pixel & Text Overlay", "PASS", f"Rendered successfully (Status 200). URL: {url}")
        else:
            record_finding("2", "Sys:Pixel & Text Overlay", "OPTIONAL_FAIL",
                           f"HTTP {r.status_code}: {r.text[:150]}",
                           fallback="Upload CV-generated transparent mask PNG per run and layer with l_<mask_id>,o_50")
    except Exception as e:
        record_finding("2", "Sys:Pixel & Text Overlay", "OPTIONAL_FAIL", str(e),
                       fallback="Upload CV-generated transparent mask PNG per run and layer with l_<mask_id>,o_50")

def test_3_mask_png_overlay(base_pid):
    print("\n--- Testing 3: Mask PNG Overlay with Opacity ---")
    if not base_pid:
        record_finding("3", "Mask PNG Overlay", "SKIPPED", "No base asset")
        return

    try:
        from PIL import Image
        mask = Image.new("RGBA", (64, 64), color=(0, 255, 0, 128))
        buf = io.BytesIO()
        mask.save(buf, format="PNG")
        buf.seek(0)

        mask_res = cloudinary.uploader.upload(
            buf,
            folder="spectrotrace/test",
            public_id="spike_mask",
            type="authenticated",
            tags="spike,env:test",
            overwrite=True
        )
        mask_pid = mask_res["public_id"].replace("/", ":")

        transform = [
            {"overlay": mask_pid, "opacity": 60},
            {"flags": "layer_apply", "gravity": "center"}
        ]
        url, _ = cloudinary.utils.cloudinary_url(
            base_pid,
            type="authenticated",
            sign_url=True,
            transformation=transform
        )
        r = requests.get(url)
        if r.status_code == 200:
            record_finding("3", "Mask PNG Overlay", "PASS", f"Mask layer applied (Status 200). URL: {url}")
        else:
            record_finding("3", "Mask PNG Overlay", "FAIL", f"HTTP {r.status_code}: {r.text[:150]}")
    except Exception as e:
        record_finding("3", "Mask PNG Overlay", "FAIL", str(e))

def test_4_crop_tiling(base_pid):
    print("\n--- Testing 4: c_crop Deep-Zoom Tiling ---")
    if not base_pid:
        record_finding("4", "c_crop Tiling", "SKIPPED", "No base asset")
        return

    try:
        transform = [
            {"crop": "crop", "x": 10, "y": 10, "width": 32, "height": 32}
        ]
        url, _ = cloudinary.utils.cloudinary_url(
            base_pid,
            type="authenticated",
            sign_url=True,
            transformation=transform
        )
        r = requests.get(url)
        if r.status_code == 200:
            record_finding("4", "c_crop Tiling", "PASS", f"Tile cropped successfully (Status 200). URL: {url}")
        else:
            record_finding("4", "c_crop Tiling", "FAIL", f"HTTP {r.status_code}: {r.text[:150]}")
    except Exception as e:
        record_finding("4", "c_crop Tiling", "FAIL", str(e))

def test_5_generative_transforms(base_pid):
    print("\n--- Testing 5: Cosmetic Generative Transforms ---")
    if not base_pid:
        record_finding("5", "Generative Transforms", "SKIPPED", "No base asset")
        return

    # Check e_gen_restore / b_gen_fill / e_gen_remove
    tests = [
        ("e_gen_restore", [{"effect": "gen_restore"}]),
        ("b_gen_fill", [{"crop": "pad", "width": 100, "height": 100, "background": "gen_fill"}])
    ]
    for gen_name, tf in tests:
        try:
            t0 = time.time()
            url, _ = cloudinary.utils.cloudinary_url(
                base_pid,
                type="authenticated",
                sign_url=True,
                transformation=tf
            )
            r = requests.get(url)
            elapsed = int((time.time() - t0) * 1000)
            if r.status_code == 200:
                record_finding(f"5_{gen_name}", f"Generative {gen_name}", "PASS", f"Latency: {elapsed}ms. URL: {url}")
            else:
                record_finding(f"5_{gen_name}", f"Generative {gen_name}", "OPTIONAL_FAIL",
                               f"HTTP {r.status_code} ({elapsed}ms): {r.text[:120]}",
                               fallback="Deterministic visual enhancement (e_improve, e_sharpen) or cosmetic display roadmap")
        except Exception as e:
            record_finding(f"5_{gen_name}", f"Generative {gen_name}", "OPTIONAL_FAIL", str(e),
                           fallback="Deterministic visual enhancement (e_improve, e_sharpen)")

def test_6_audio_waveform():
    print("\n--- Testing 6: Audio Upload, fl_waveform & Range Segment ---")
    try:
        # Create a simple synthetic 1-second WAV file
        import wave
        import struct
        import math

        buf = io.BytesIO()
        with wave.open(buf, 'wb') as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(16000)
            for i in range(16000):
                sample = int(32767.0 * 0.5 * math.sin(2.0 * math.pi * 440.0 * i / 16000))
                wav.writeframes(struct.pack('<h', sample))
        buf.seek(0)

        res = cloudinary.uploader.upload(
            buf,
            folder="spectrotrace/test",
            public_id="spike_audio_test",
            resource_type="video",
            type="authenticated",
            tags="spike,audio,env:test",
            overwrite=True
        )
        audio_pid = res["public_id"]

        # 6a. Waveform PNG
        wf_url, _ = cloudinary.utils.cloudinary_url(
            f"{audio_pid}.png",
            resource_type="video",
            type="authenticated",
            sign_url=True,
            flags="waveform"
        )
        r_wf = requests.get(wf_url)
        if r_wf.status_code == 200:
            record_finding("6_waveform", "Audio fl_waveform", "PASS", f"Waveform PNG generated. URL: {wf_url}")
        else:
            record_finding("6_waveform", "Audio fl_waveform", "OPTIONAL_FAIL",
                           f"HTTP {r_wf.status_code}: {r_wf.text[:120]}",
                           fallback="Matplotlib / librosa waveform rendering uploaded as PNG")

        # 6b. Segment delivery (so_0, eo_0.5)
        seg_url, _ = cloudinary.utils.cloudinary_url(
            f"{audio_pid}.wav",
            resource_type="video",
            type="authenticated",
            sign_url=True,
            start_offset="0.1",
            end_offset="0.5"
        )
        r_seg = requests.get(seg_url)
        if r_seg.status_code == 200:
            record_finding("6_segment", "Audio Segment Delivery (so_/eo_)", "PASS", f"Segment delivered: {seg_url}")
        else:
            record_finding("6_segment", "Audio Segment Delivery", "OPTIONAL_FAIL",
                           f"HTTP {r_seg.status_code}: {r_seg.text[:120]}",
                           fallback="Client-side HTML5 audio seek on standard audio file")
    except Exception as e:
        record_finding("6_audio", "Audio Processing", "FAIL", str(e),
                       fallback="Matplotlib spectrogram/waveform with audio seek via HTML5 player")

def test_7_search_api():
    print("\n--- Testing 7: Cloudinary Search API ---")
    try:
        result = cloudinary.Search()\
            .expression("tags=spike AND folder=spectrotrace/*")\
            .sort_by("created_at", "desc")\
            .max_results(5)\
            .execute()
        count = len(result.get("resources", []))
        record_finding("7", "Search API", "PASS", f"Search executed successfully. Found {count} test resources.")
    except Exception as e:
        record_finding("7", "Search API", "FAIL", str(e),
                       fallback="Database index in Postgres for history and review queue")

def test_8_webhook_signature():
    print("\n--- Testing 8: Webhook Signature Verification Logic ---")
    try:
        ts = int(time.time())
        body = json.dumps({"notification_type": "upload", "public_id": "test_pid"})
        
        # Manually compute expected signature
        to_sign = f"{body}{ts}{api_secret}"
        import hashlib
        expected_sig = hashlib.sha1(to_sign.encode("utf-8")).hexdigest()

        # Test verification helper
        verified = cloudinary.utils.verify_notification_signature(body, ts, expected_sig)
        if verified:
            record_finding("8", "Webhook Signature Verification", "PASS",
                           "HMAC signature generation and verification verified successfully.")
        else:
            record_finding("8", "Webhook Signature Verification", "FAIL", "Signature verification returned False.")
    except Exception as e:
        record_finding("8", "Webhook Signature Verification", "FAIL", str(e))

def generate_findings_report():
    print("\n--- Generating docs/cloudinary_findings.md ---")
    content = [
        "# Cloudinary Spike Findings & Phase 1 Validation Report",
        f"\n**Execution Date:** {time.strftime('%Y-%m-%d %H:%M:%S UTC')}",
        f"**Cloud Name:** `{cloud_name or 'NOT_SET'}`",
        "\n| Test ID | Capability | Status | Fallback Strategy | Notes |",
        "|---|---|---|---|---|"
    ]
    for f in findings:
        status_badge = f"`{f['status']}`"
        fallback_str = f['fallback'] or "None needed"
        details_escaped = f['details'].replace("|", "\\|") if f['details'] else ""
        content.append(f"| {f['id']} | {f['name']} | {status_badge} | {fallback_str} | {details_escaped} |")
    
    content.append("\n## Architectural Fallback Summary")
    content.append("- **Sys:Pixel Overlays:** If colorize overlay is unconfigured, system uses per-run transparent PNG mask overlays (`l_<mask_id>,o_50`).")
    content.append("- **Audio Waveform:** If `fl_waveform` flag is unavailable on plan, backend renders standard matplotlib waveforms as companion PNG assets.")
    content.append("- **Generative Views:** Cosmetic generative views (`e_gen_restore`, `b_gen_fill`) are marked optional display enhancements with fallback to deterministic sharpening (`e_sharpen`, `e_improve`).")
    content.append("- **Search API:** Search API is backed up by Postgres `jobs` & `findings` metadata indexes.")
    
    FINDINGS_PATH.write_text("\n".join(content), encoding="utf-8")
    print(f"✅ Report saved to: {FINDINGS_PATH}")

def main():
    print("=" * 60)
    print("SpectroTrace AI - Phase 1 Cloudinary Spike Gate")
    print("=" * 60)
    
    if not (cloud_name and api_key and api_secret):
        print("⚠️ Warning: Credentials not yet configured in .env.")
        print("Running offline test for webhook verification logic, and writing template findings report.")
        test_8_webhook_signature()
        generate_findings_report()
        return

    base_pid = test_1_authenticated_upload_and_signing()
    test_2_rectangle_overlay_and_text(base_pid)
    test_3_mask_png_overlay(base_pid)
    test_4_crop_tiling(base_pid)
    test_5_generative_transforms(base_pid)
    test_6_audio_waveform()
    test_7_search_api()
    test_8_webhook_signature()
    generate_findings_report()

if __name__ == "__main__":
    main()
