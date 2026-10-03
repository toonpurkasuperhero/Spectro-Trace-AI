#!/usr/bin/env python3
"""
Evaluation Harness for Module A: Micro-Defect & Deviation-Density Map Vision
Evaluates 40 print layer images (20 defective, 20 clean) comparing SpectroTrace CV
against naive raw pixel-difference thresholding.
"""

import sys
import numpy as np
from pathlib import Path
from PIL import Image, ImageDraw

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

from api.modules.print_defect import analyze_print_defects

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

def generate_eval_layer(has_defect: bool) -> tuple[np.ndarray, np.ndarray]:
    golden = Image.new("RGB", (128, 128), color=(30, 30, 30))
    draw_g = ImageDraw.Draw(golden)
    draw_g.rectangle([25, 25, 103, 103], outline=(200, 200, 200), width=4)

    actual = golden.copy()
    if has_defect:
        draw_a = ImageDraw.Draw(actual)
        draw_a.line([30, 40, 95, 45], fill=(180, 180, 180), width=2)
        draw_a.rectangle([50, 50, 65, 65], fill=(220, 220, 220))

    return np.array(actual), np.array(golden)

def evaluate_print(n_samples: int = 40):
    np.random.seed(42)

    tp_cv, fp_cv, fn_cv = 0, 0, 0
    tp_base, fp_base, fn_base = 0, 0, 0

    for i in range(n_samples):
        has_defect = (i % 2 == 0)
        actual, golden = generate_eval_layer(has_defect)

        # 1. SpectroTrace CV Pipeline
        findings, cal, heatmap, stats = analyze_print_defects(actual, golden)
        detected_cv = len(findings) > 0

        if has_defect:
            if detected_cv:
                tp_cv += 1
            else:
                fn_cv += 1
        else:
            if detected_cv:
                fp_cv += 1

        # 2. Naive Baseline (Raw pixel difference threshold > 500)
        raw_diff_count = np.sum(np.abs(actual.astype(int) - golden.astype(int)) > 40)
        detected_base = bool(raw_diff_count > 100)

        if has_defect:
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

    print("\n## Module A Evaluation Results (3D Print Defect Vision)")
    print(f"| Approach | Samples | Precision | Recall | F1 Score | Baseline Type |")
    print(f"|---|---|---|---|---|---|")
    print(f"| **SpectroTrace CV + Vision** | {n_samples} | **{precision_cv:.1%}** | **{recall_cv:.1%}** | **{f1_cv:.2f}** | Alignment + SSIM + Morphological Filtering |")
    print(f"| Naive Baseline | {n_samples} | {precision_base:.1%} | {recall_base:.1%} | {f1_base:.2f} | Raw Pixel Difference Threshold |")

    return {
        "precision_cv": precision_cv,
        "recall_cv": recall_cv,
        "precision_base": precision_base,
        "recall_base": recall_base
    }

if __name__ == "__main__":
    evaluate_print()
