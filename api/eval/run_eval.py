#!/usr/bin/env python3
"""
run_eval.py — Unified evaluation runner for all four SpectroTrace modules.

Usage:
    python api/eval/run_eval.py [--module thermal|audio|print|specimen|all] [--output results.md]

Outputs a precision/recall table vs. baseline and writes to docs/eval_results.md.
"""
import argparse
import sys
import time
from pathlib import Path

# Ensure project root on path so api.* imports work
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


# ── Wrapper adapters (normalise each module's return format) ──────────────────

def run_thermal_eval() -> dict:
    from api.eval.eval_thermal import evaluate_thermal
    r = evaluate_thermal()
    return {
        "metrics":  {"precision": r["precision_cv"],   "recall": r["recall_cv"],
                     "extra": "Radiometric ΔT + CC"},
        "baseline": {"precision": r["precision_base"], "recall": r["recall_base"]},
    }

def run_audio_eval() -> dict:
    from api.eval.eval_audio import evaluate_audio
    r = evaluate_audio()
    return {
        "metrics":  {"precision": r["precision_dsp"],  "recall": r["recall_dsp"],
                     "extra": "Welch PSD hum + flux splice"},
        "baseline": {"precision": r["precision_base"], "recall": r["recall_base"]},
    }

def run_print_eval() -> dict:
    from api.eval.eval_print import evaluate_print
    r = evaluate_print()
    return {
        "metrics":  {"precision": r["precision_cv"],   "recall": r["recall_cv"],
                     "extra": "ORB align + SSIM + morph"},
        "baseline": {"precision": r["precision_base"], "recall": r["recall_base"]},
    }

def run_specimen_eval() -> dict:
    from api.eval.eval_specimen import evaluate_specimen
    r = evaluate_specimen()
    return {
        "metrics":  {"precision": r["precision_cv"],   "recall": r["recall_cv"],
                     "extra": "Reinhard + watershed density"},
        "baseline": {"precision": r["precision_base"], "recall": r["recall_base"]},
    }


# ── Module registry ───────────────────────────────────────────────────────────

MODULE_RUNNERS = {
    "thermal": run_thermal_eval,
    "audio":   run_audio_eval,
    "print":   run_print_eval,
    "specimen": run_specimen_eval,
}

MODULE_LABELS = {
    "thermal": "B — Thermal Radiometry",
    "audio":   "D — Forensic Audio",
    "print":   "A — Print Defect",
    "specimen": "C — SpecimenTrace",
}


# ── Formatting ────────────────────────────────────────────────────────────────

def _f1(p: float, r: float) -> float:
    return 2 * p * r / (p + r) if (p + r) > 0 else 0.0

def format_row(name: str, metrics: dict, baseline: dict) -> str:
    p,  r  = metrics["precision"],  metrics["recall"]
    bp, br = baseline["precision"], baseline["recall"]
    f1_  = _f1(p,  r)
    f1_b = _f1(bp, br)
    pa   = "▲" if p > bp else ("▼" if p < bp else "=")
    ra   = "▲" if r > br else ("▼" if r < br else "=")
    extra = metrics.get("extra", "")
    return (
        f"| {name} | {p:.2f} {pa} | {r:.2f} {ra} | {f1_:.2f} | "
        f"{bp:.2f} | {br:.2f} | {f1_b:.2f} | {extra} |"
    )


# ── Main runner ───────────────────────────────────────────────────────────────

def run(modules: list, output_path: Path) -> None:
    header = [
        "# SpectroTrace AI — Evaluation Results",
        "",
        f"> Generated: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}",
        "",
        "## Summary Table",
        "",
        "| Module | Precision ↕ | Recall ↕ | F1 | Base P | Base R | Base F1 | Method |",
        "|--------|-------------|----------|----|--------|--------|---------|--------|",
    ]
    rows: list[str] = []

    for mod in modules:
        runner = MODULE_RUNNERS.get(mod)
        if not runner:
            print(f"  [SKIP] Unknown module: {mod}")
            continue

        label = MODULE_LABELS[mod]
        print(f"\n=== {label} ===")
        t0 = time.time()
        try:
            result = runner()
            elapsed = time.time() - t0
            m = result["metrics"]
            print(
                f"  precision={m['precision']:.3f}  "
                f"recall={m['recall']:.3f}  "
                f"({elapsed:.1f}s)"
            )
            rows.append(format_row(label, result["metrics"], result["baseline"]))
        except Exception as exc:
            import traceback; traceback.print_exc()
            rows.append(f"| {label} | ERROR | — | — | — | — | — | {exc} |")

    footer = [
        "",
        "## CV only vs. CV + Vision",
        "",
        "The vision layer classifies each CV-detected region and adds an explanation.",
        "Primary gain: **false-positive reduction** via artifact labels",
        "(`reflection_artifact`, `tissue_fold`, `dust_artifact`, `normal`).",
        "All physical measurements (ΔT, crack length, nuclei count) come from CV only.",
        "",
        "## Notes",
        "",
        "- ▲/▼/= compare SpectroTrace vs. baseline for each metric.",
        "- Fixtures are synthetic (numpy arrays / soundfile WAV) for dependency-free CI.",
        "- Pass `pytest -m cloud` with real credentials to test Cloudinary integration.",
        "- **Disclaimer:** specimen results are for research/screening only — not a diagnostic device.",
    ]

    all_lines = header + rows + footer
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(all_lines) + "\n", encoding="utf-8")
    print(f"\n\u2705  Results written to {output_path}")
    print("\n" + "\n".join(header[5:] + rows))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run SpectroTrace evaluation suite")
    parser.add_argument(
        "--module",
        choices=list(MODULE_RUNNERS.keys()) + ["all"],
        default="all",
        help="Which module to evaluate (default: all)",
    )
    parser.add_argument(
        "--output",
        default="docs/eval_results.md",
        help="Output markdown file path (default: docs/eval_results.md)",
    )
    args = parser.parse_args()
    mods = list(MODULE_RUNNERS.keys()) if args.module == "all" else [args.module]
    run(mods, Path(args.output))


if __name__ == "__main__":
    main()
