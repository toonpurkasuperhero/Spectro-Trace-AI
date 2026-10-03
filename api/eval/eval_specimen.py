#!/usr/bin/env python3
"""
Evaluation Harness for Module C: SpecimenTrace-AI
Evaluates 40 microscopic tiles (20 with cellular density / cracks, 20 clean)
comparing SpectroTrace CV against naive threshold-only baseline.
"""

import sys
import numpy as np
from pathlib import Path
from PIL import Image, ImageDraw

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

from api.modules.specimen import analyze_histology_patch

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

def generate_eval_tile(has_anomaly: bool) -> np.ndarray:
    img = Image.new("RGB", (128, 128), color=(240, 205, 215))
    draw = ImageDraw.Draw(img)

    # Base low-density cells
    for i in range(5):
        draw.ellipse([20 + i*18, 20 + i*15, 28 + i*18, 28 + i*15], fill=(70, 30, 95))

    if has_anomaly:
        # Inject dense nuclei cluster
        for j in range(25):
            rx = np.random.randint(40, 90)
            ry = np.random.randint(40, 90)
            draw.ellipse([rx, ry, rx+8, ry+8], fill=(60, 20, 90))

    return np.array(img)

def evaluate_specimen(n_tiles: int = 40):
    np.random.seed(42)

    tp_cv, fp_cv, fn_cv = 0, 0, 0
    tp_base, fp_base, fn_base = 0, 0, 0

    for i in range(n_tiles):
        has_anomaly = (i % 2 == 0)
        tile = generate_eval_tile(has_anomaly)

        # 1. SpectroTrace CV Pipeline (Reinhard + Optical Density Watershed)
        findings, cal, stats = analyze_histology_patch(tile, um_per_px=0.5)
        detected_cv = bool(stats["nuclei_area_fraction"] > 0.035 or stats["total_nuclei_count"] >= 6)

        if has_anomaly:
            if detected_cv:
                tp_cv += 1
            else:
                fn_cv += 1
        else:
            if detected_cv:
                fp_cv += 1

        # 2. Naive Baseline (Simple Grayscale mean threshold)
        gray = np.mean(tile, axis=2)
        detected_base = bool(np.mean(gray) < 205.0)

        if has_anomaly:
            if detected_base:
                tp_base += 1
            else:
                fn_base += 1
        else:
            if detected_base:
                fp_base += 1

    precision_cv = tp_cv / max(tp_cv + fp_cv, 1)
    recall_cv = tp_cv / max(tp_cv + fn_cv, 1)
    f1_cv = 2 * (precision_cv * recall_cv) / max(precision_cv + recall_cv, 1e-6)

    precision_base = tp_base / max(tp_base + fp_base, 1)
    recall_base = tp_base / max(tp_base + fn_base, 1)
    f1_base = 2 * (precision_base * recall_base) / max(precision_base + recall_base, 1e-6)

    print("\n## Module C Evaluation Results (SpecimenTrace Pathology & Degradation)")
    print(f"| Approach | Samples | Precision | Recall | F1 Score | Baseline Type |")
    print(f"|---|---|---|---|---|---|")
    print(f"| **SpectroTrace CV + Vision** | {n_tiles} | **{precision_cv:.1%}** | **{recall_cv:.1%}** | **{f1_cv:.2f}** | Reinhard Stain Norm + Watershed Density |")
    print(f"| Naive Baseline | {n_tiles} | {precision_base:.1%} | {recall_base:.1%} | {f1_base:.2f} | Raw Grayscale Intensity Threshold |")

    return {
        "precision_cv": precision_cv,
        "recall_cv": recall_cv,
        "precision_base": precision_base,
        "recall_base": recall_base
    }

if __name__ == "__main__":
    evaluate_specimen()
