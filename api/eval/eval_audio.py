#!/usr/bin/env python3
"""
Evaluation Harness for Module D: Forensic Speech & Audio Diagnostics
Generates a benchmark suite of 40 audio clips (clean, 50/60 Hz hum, splice anomalies)
and evaluates detection precision and recall against a naive energy threshold baseline.
"""

import sys
import io
import math
import struct
import wave
from pathlib import Path
import numpy as np

# Ensure project root in sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

from api.modules.audio import load_audio, compute_mel_spectrogram, analyze_audio_forensics

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

def generate_eval_clip(clip_type: str, duration: float = 2.0, sr: int = 16000) -> bytes:
    buf = io.BytesIO()
    total_samples = int(sr * duration)
    with wave.open(buf, 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sr)

        samples = []
        for i in range(total_samples):
            t = i / sr
            # Clean fundamental signal
            val = 0.25 * math.sin(2.0 * math.pi * 300.0 * t) + 0.15 * math.sin(2.0 * math.pi * 600.0 * t)

            if clip_type == "hum":
                # Injected 50 or 60 Hz hum
                hum_f = 50.0 if (i % 2 == 0) else 60.0
                val += 0.35 * math.sin(2.0 * math.pi * hum_f * t)
            elif clip_type == "splice":
                # Discontinuity at t = 1.0s
                if 0.98 <= t <= 1.02:
                    val = 0.9
            # Background noise
            val += np.random.normal(0, 0.015)

            samples.append(int(np.clip(val, -1.0, 1.0) * 32767.0))

        for s in samples:
            wav.writeframes(struct.pack('<h', s))

    return buf.getvalue()

def evaluate_audio(n_clips: int = 40):
    np.random.seed(42)

    tp_dsp, fp_dsp, fn_dsp = 0, 0, 0
    tp_base, fp_base, fn_base = 0, 0, 0

    types = ["clean", "hum", "splice", "hum"]

    for i in range(n_clips):
        clip_type = types[i % len(types)]
        is_anomalous = (clip_type != "clean")

        raw_wav = generate_eval_clip(clip_type)
        y, sr, duration = load_audio(raw_wav)
        mel_spec_db, _, _ = compute_mel_spectrogram(y, sr=sr)

        # 1. SpectroTrace DSP Pipeline (Welch hum + Spectral flux)
        findings, cal, stats = analyze_audio_forensics(y, sr, mel_spec_db, duration)
        detected_dsp = len(findings) > 0

        if is_anomalous:
            if detected_dsp:
                tp_dsp += 1
            else:
                fn_dsp += 1
        else:
            if detected_dsp:
                fp_dsp += 1

        # 2. Naive Baseline (Simple Root-Mean-Square Energy threshold)
        rms = np.sqrt(np.mean(y ** 2))
        detected_base = bool(rms > 0.28)

        if is_anomalous:
            if detected_base:
                tp_base += 1
            else:
                fn_base += 1
        else:
            if detected_base:
                fp_base += 1

    precision_dsp = tp_dsp / max(tp_dsp + fp_dsp, 1)
    recall_dsp = tp_dsp / max(tp_dsp + fn_dsp, 1)
    f1_dsp = 2 * (precision_dsp * recall_dsp) / max(precision_dsp + recall_dsp, 1e-6)

    precision_base = tp_base / max(tp_base + fp_base, 1)
    recall_base = tp_base / max(tp_base + fn_base, 1)
    f1_base = 2 * (precision_base * recall_base) / max(precision_base + recall_base, 1e-6)

    print("\n## Module D Evaluation Results (Audio Forensics)")
    print(f"| Approach | Samples | Precision | Recall | F1 Score | Baseline Type |")
    print(f"|---|---|---|---|---|---|")
    print(f"| **SpectroTrace DSP + Vision** | {n_clips} | **{precision_dsp:.1%}** | **{recall_dsp:.1%}** | **{f1_dsp:.2f}** | Welch PSD Hum + Spectral Flux Discontinuity |")
    print(f"| Naive Baseline | {n_clips} | {precision_base:.1%} | {recall_base:.1%} | {f1_base:.2f} | Raw RMS Energy Threshold |")

    return {
        "precision_dsp": precision_dsp,
        "recall_dsp": recall_dsp,
        "precision_base": precision_base,
        "recall_base": recall_base
    }

if __name__ == "__main__":
    evaluate_audio()
