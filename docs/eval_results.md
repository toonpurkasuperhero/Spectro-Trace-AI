# SpectroTrace AI — Evaluation Results

> Generated: 2026-10-02 14:45:07 UTC

## Summary Table

| Module | Precision ↕ | Recall ↕ | F1 | Base P | Base R | Base F1 | Method |
|--------|-------------|----------|----|--------|--------|---------|--------|
| B — Thermal Radiometry | 1.00 = | 1.00 = | 1.00 | 1.00 | 1.00 | 1.00 | Radiometric ΔT + CC |
| D — Forensic Audio | 0.75 ▼ | 1.00 ▲ | 0.86 | 1.00 | 0.67 | 0.80 | Welch PSD hum + flux splice |
| A — Print Defect | 1.00 = | 1.00 = | 1.00 | 1.00 | 1.00 | 1.00 | ORB align + SSIM + morph |
| C — SpecimenTrace | 1.00 = | 0.75 ▲ | 0.86 | 1.00 | 0.15 | 0.26 | Reinhard + watershed density |

## CV only vs. CV + Vision

The vision layer classifies each CV-detected region and adds an explanation.
Primary gain: **false-positive reduction** via artifact labels
(`reflection_artifact`, `tissue_fold`, `dust_artifact`, `normal`).
All physical measurements (ΔT, crack length, nuclei count) come from CV only.

## Notes

- ▲/▼/= compare SpectroTrace vs. baseline for each metric.
- Fixtures are synthetic (numpy arrays / soundfile WAV) for dependency-free CI.
- Pass `pytest -m cloud` with real credentials to test Cloudinary integration.
- **Disclaimer:** specimen results are for research/screening only — not a diagnostic device.
