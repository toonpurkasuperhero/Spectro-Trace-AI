#!/usr/bin/env python3
"""
Evaluation Harness for Module B: Thermal Energy Loss & HVAC Leak Radiometry
Generates synthetic benchmark set of 30 thermal images with ground-truth anomalies
and compares our Radiometric CV + Vision pipeline against the naive baseline (hottest 5% threshold).
"""

import sys
from pathlib import Path

# Add project root to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT_DIR))

import numpy as np
from api.modules.thermal import analyze_thermal_radiometry

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

def evaluate_thermal(n_samples: int = 30):
    np.random.seed(42)

    tp_cv, fp_cv, fn_cv = 0, 0, 0
    tp_base, fp_base, fn_base = 0, 0, 0

    for i in range(n_samples):
        # 100x100 temperature array with ambient ~20.0 C
        arr = np.random.normal(20.0, 0.8, (100, 100)).astype(np.float32)
        has_anomaly = (i % 2 == 0)

        gt_box = None
        if has_anomaly:
            # Inject hotspot of Delta T = 15..35 C
            rx = np.random.randint(15, 70)
            ry = np.random.randint(15, 70)
            size = np.random.randint(10, 20)
            arr[ry:ry+size, rx:rx+size] += np.random.uniform(15.0, 35.0)
            gt_box = (rx, ry, size, size)

        # 1. Pipeline evaluation (CV + Radiometric Delta T threshold)
        findings, _, _ = analyze_thermal_radiometry(arr, ambient_ref_c=20.0, delta_t_threshold=8.0)
        detected_cv = len(findings) > 0

        if has_anomaly:
            if detected_cv:
                tp_cv += 1
            else:
                fn_cv += 1
        else:
            if detected_cv:
                fp_cv += 1

        # 2. Baseline evaluation: Naive "hottest 5% of pixels" threshold
        top_5_pct = np.percentile(arr, 95)
        # Baseline flags anomaly if max temperature exceeds top 5% by a standard deviation
        detected_base = bool(np.max(arr) > (top_5_pct + 2.5))
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

    print("\n## Module B Evaluation Results (Thermal Radiometry)")
    print(f"| Approach | Samples | Precision | Recall | F1 Score | Baseline Type |")
    print(f"|---|---|---|---|---|---|")
    print(f"| **SpectroTrace CV + Vision** | {n_samples} | **{precision_cv:.1%}** | **{recall_cv:.1%}** | **{f1_cv:.2f}** | Radiometric ΔT + Morphological CC |")
    print(f"| Naive Baseline | {n_samples} | {precision_base:.1%} | {recall_base:.1%} | {f1_base:.2f} | Hottest-5% Percentile Threshold |")

    return {
        "precision_cv": precision_cv,
        "recall_cv": recall_cv,
        "precision_base": precision_base,
        "recall_base": recall_base
    }

if __name__ == "__main__":
    evaluate_thermal()
