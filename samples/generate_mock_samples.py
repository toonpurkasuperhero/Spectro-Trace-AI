#!/usr/bin/env python3
"""
Generates synthetic sample fixtures for the 4 modules:
- Thermal: temperature matrix CSV & Ironbow RGB image
- Audio: clean voice sine, 50Hz hum anomaly, and splice artifact WAV
- Print: golden reference layer & simulated defect layer
- Specimen: simulated H&E stained patch
"""

import os
import sys
import math
import struct
import wave
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

SAMPLES_DIR = Path(__file__).resolve().parent

def generate_thermal_sample():
    thermal_dir = SAMPLES_DIR / "thermal"
    thermal_dir.mkdir(parents=True, exist_ok=True)
    
    # 640x480 temperature grid in Celsius
    # Background 20.0 C with a 72.5 C hotspot (simulated air leak / overheating electrical component)
    arr = np.full((480, 640), 20.0, dtype=np.float32)
    # Add noise
    noise = np.random.normal(0, 0.5, (480, 640))
    arr += noise

    # Hotspot at (x=240..320, y=180..260)
    y, x = np.ogrid[:480, :640]
    dist_sq = (x - 280)**2 + (y - 220)**2
    hotspot = np.exp(-dist_sq / (2 * 25**2)) * 52.5
    arr += hotspot

    # Save CSV
    np.savetxt(thermal_dir / "sample_radiometric_matrix.csv", arr, delimiter=",", fmt="%.2f")

    # Save normalized ironbow pseudo-color render
    norm = np.clip((arr - 15.0) / (75.0 - 15.0), 0.0, 1.0)
    import matplotlib.cm as cm
    ironbow_rgba = cm.inferno(norm)
    img = Image.fromarray((ironbow_rgba[:, :, :3] * 255).astype(np.uint8))
    img.save(thermal_dir / "sample_thermal_render.png")
    print("✅ Generated sample thermal matrix and render in samples/thermal/")

def generate_audio_sample():
    audio_dir = SAMPLES_DIR / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)

    sr = 16000
    duration = 5.0
    total_samples = int(sr * duration)

    # 440 Hz fundamental tone + 50 Hz hum artifact between seconds 1.5 and 3.5
    samples = []
    for i in range(total_samples):
        t = i / sr
        # Base tone
        val = 0.4 * math.sin(2.0 * math.pi * 440.0 * t)
        # Injected 50Hz hum anomaly in window [1.5, 3.5]
        if 1.5 <= t <= 3.5:
            val += 0.35 * math.sin(2.0 * math.pi * 50.0 * t)
        # Background white noise
        val += np.random.normal(0, 0.02)
        
        sample_int = int(np.clip(val, -1.0, 1.0) * 32767.0)
        samples.append(sample_int)

    wav_path = audio_dir / "sample_forensic_audio.wav"
    with wave.open(str(wav_path), 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sr)
        for s in samples:
            wav.writeframes(struct.pack('<h', s))
    print("✅ Generated sample forensic audio WAV in samples/audio/")

def generate_print_sample():
    print_dir = SAMPLES_DIR / "print"
    print_dir.mkdir(parents=True, exist_ok=True)

    # Golden reference layer
    golden = Image.new("RGB", (512, 512), color=(40, 40, 40))
    from PIL import ImageDraw
    draw_g = ImageDraw.Draw(golden)
    draw_g.rectangle([100, 100, 412, 412], outline=(220, 220, 220), width=8)
    golden.save(print_dir / "layer_golden_ref.png")

    # Actual layer with stringing / under-extrusion anomaly
    actual = golden.copy()
    draw_a = ImageDraw.Draw(actual)
    # Defect: stringing artifact
    draw_a.line([120, 150, 390, 380], fill=(180, 180, 180), width=3)
    draw_a.line([130, 200, 380, 220], fill=(160, 160, 160), width=2)
    # Void / crack gap
    draw_a.rectangle([250, 96, 270, 106], fill=(40, 40, 40))
    actual.save(print_dir / "layer_with_defect.png")
    print("✅ Generated sample print layers in samples/print/")

def generate_specimen_sample():
    specimen_dir = SAMPLES_DIR / "specimen"
    specimen_dir.mkdir(parents=True, exist_ok=True)

    # Simulated H&E stain (pink eosin cytoplasm background + purple hematoxylin nuclei)
    img = Image.new("RGB", (512, 512), color=(235, 195, 210))
    draw = ImageDraw.Draw(img)

    # Draw simulated nuclei
    np.random.seed(42)
    for _ in range(120):
        nx = int(np.random.uniform(20, 492))
        ny = int(np.random.uniform(20, 492))
        r = int(np.random.uniform(4, 9))
        draw.ellipse([nx - r, ny - r, nx + r, ny + r], fill=(70, 25, 100))

    img.save(specimen_dir / "sample_he_patch.png")
    print("✅ Generated sample specimen H&E patch in samples/specimen/")

if __name__ == "__main__":
    generate_thermal_sample()
    generate_audio_sample()
    generate_print_sample()
    generate_specimen_sample()
