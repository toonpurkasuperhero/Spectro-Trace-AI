# SpectroTrace AI

> **One pipeline, four domains, one config file each.**
> Any physical signal is measured losslessly in the backend, then turned into a secure, searchable, annotated, deep-zoomable visual workspace by Cloudinary.

[![CI](https://github.com/your-org/spectrotrace/actions/workflows/ci.yml/badge.svg)](https://github.com/your-org/spectrotrace/actions/workflows/ci.yml)

---

## Modules

| ID | Name | Domain |
|----|------|--------|
| A | **Micro-Defect & Stress-Map Vision** | Additive manufacturing (3D printing) |
| B | **Thermal Energy Loss & HVAC Leak Radiometry** | Civil / building inspection |
| C | **SpecimenTrace-AI** | Materials science / histopathology |
| D | **SpectroTrace AI** — Forensic Speech & Audio | Bio-acoustics / audio forensics |

---

## Architecture

```
Browser (Next.js) ──sign──► FastAPI ──webhook──► Cloudinary
                                                     │
                    ◄──SSE stages──          ◄──pipeline runs, overlays, metadata
```

**Stack:**

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js (App Router), Tailwind CSS, Lucide Icons |
| Backend | FastAPI, Pydantic, SlowAPI (rate limiting) |
| CV / Signal | NumPy, OpenCV, scikit-image, SciPy, librosa, Matplotlib |
| Cloud | Cloudinary (upload presets, webhooks, URL transforms, Search API) |
| Vision AI | Gemini via `LLM_API_KEY` (swappable provider interface) |
| Database | SQLite (dev) / Postgres (prod via `DATABASE_URL`) |

---

## Local Setup

### Prerequisites

- Python 3.11+
- Node.js 20+
- ffmpeg + libsndfile (audio processing)

```bash
# macOS
brew install ffmpeg libsndfile

# Ubuntu / Debian
sudo apt-get install -y ffmpeg libsndfile1
```

### 1. Clone & configure

```bash
git clone https://github.com/your-org/spectrotrace.git
cd spectrotrace
cp .env.example .env
# Edit .env and fill in your credentials
```

Required `.env` values:

| Key | Description |
|-----|-------------|
| `CLOUDINARY_CLOUD_NAME` | Your Cloudinary cloud name |
| `CLOUDINARY_API_KEY` | Cloudinary API key |
| `CLOUDINARY_API_SECRET` | Cloudinary API secret |
| `LLM_API_KEY` | Google AI Studio key (`AIzaSy...` format) |
| `NEXT_PUBLIC_CLD_CLOUD_NAME` | Same cloud name for the frontend |

### 2. Backend

```bash
pip install -r api/requirements.txt
cd api
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

API docs: http://localhost:8000/docs

### 3. Frontend

```bash
cd web
npm install
npm run dev
```

Dashboard: http://localhost:3000

---

## Usage

1. **Dashboard** (`/`) — Upload a file, pick a module, watch the pipeline run live via SSE.
2. **Upload** (`/upload`) — Dedicated upload page with calibration inputs and synthetic sample quick-start.
3. **Run detail** (`/runs/[id]`) — View raw / annotated / cosmetic views, findings panel, provenance, bandwidth card.
4. **History** (`/history`) — Review queue powered by Cloudinary Search API. Approve / reject runs.

---

## Running Tests

```bash
# Unit tests (no cloud credentials needed)
python -m pytest api/tests/ -v -m "not cloud"

# Cloud integration tests (requires real Cloudinary credentials)
python -m pytest api/tests/ -v -m cloud

# Evaluation suite (all four modules)
python api/eval/run_eval.py

# Single module eval
python api/eval/run_eval.py --module thermal
```

Results are written to `docs/eval_results.md`.

---

## Cloudinary Setup (one-time)

Before first run, create these in the Cloudinary console:

**Upload Presets** (Settings → Upload → Upload presets):

| Preset name | Module | Signing mode |
|-------------|--------|-------------|
| `st_print` | A — Print | Signed |
| `st_thermal` | B — Thermal | Signed |
| `st_specimen` | C — Specimen | Signed |
| `st_audio` | D — Audio | Signed |

**Structured Metadata Fields** (Settings → Metadata):

| Field ID | Type |
|----------|------|
| `risk_level` | Enum: `low`, `medium`, `high` |
| `risk_score` | Integer |
| `review_state` | Enum: `pending`, `approved`, `rejected` |

**Upload a 1×1 white pixel asset** as `sys/pixel` for overlay colorize support:

```bash
python -c "
from PIL import Image; import cloudinary, cloudinary.uploader
cloudinary.config(cloud_name='YOUR_CLOUD', api_key='KEY', api_secret='SECRET')
img = Image.new('RGBA', (1,1), (255,255,255,255))
img.save('/tmp/pixel.png')
cloudinary.uploader.upload('/tmp/pixel.png', public_id='sys/pixel', overwrite=True)
print('Done')
"
```

---

## Docker

```bash
docker build -f api/Dockerfile -t spectrotrace-api .
docker run -p 8000:8000 --env-file .env spectrotrace-api
```

---

## CI/CD

GitHub Actions CI (`.github/workflows/ci.yml`) runs on every push:

- `pytest` (unit tests, no cloud)
- `ruff` linting
- `tsc --noEmit` for the Next.js app
- Docker build + healthz smoke-test

---

## Budget & Safety

- `MAX_GENERATIVE_CALLS_PER_DAY` / `MAX_VISION_CALLS_PER_DAY` — daily caps
- `DEMO_MODE=true` — blocks all new generative & vision calls; serves only cached results
- `ENV=dev` — generative transforms are opt-in by default

---

## Generative AI Features (Display & Presentation Layer)

SpectroTrace AI strictly isolates **deterministic measurement** from **generative display aids**:
- **Feature A — Remediation View (`e_gen_remove` / Inpainting):** Illustrative defect-free previews with region-based defect removal, in-image watermark labels, and an interactive split compare slider.
- **Feature B — Simulation Lab (Image Generation API):** Hypothetical scenario stress-testing (`corrosion`, `humidity`, `thermal_cycling`, `weathering`) evaluated via edge-map SSIM geometry retention metrics.
- **Feature C — Export Profiles (`c_pad` + `b_gen_fill` / blur / solid):** Converts sensor views into presentation-ready formats (16:9 Slide, 9:16 Mobile Alert, 1:1 Report) with canvas coordinate scaling and metadata chrome.

### Claims Table & Communication Guidelines

| Say | Don't say |
|---|---|
| "Remediation view: an illustration of what a defect-free result could look like" | "Digital twin", "repaired part", "reconstruction of the true surface" |
| "Simulation Lab: AI illustrations of hypothetical scenarios, tied to the parent inspection" | "Predicts degradation", "stress-tests the part", "physics simulation" |
| "Export profiles with deterministic blur by default; generative fill optional and labeled" | "AI adapts every sensor image to any format" |
| "Models available through Cloudinary's Image Generation API, shown as reported by the API" | Naming models that the API does not list |
| "Policy blocks generative edits on tissue findings, thermal measurements, and spectrograms" | "Safe for medical use" |

---

## Real vs. Roadmap

| Feature | Status |
|---------|--------|
| Radiometric CV, audio DSP, print defect CV, histology CV | ✅ Real |
| Cloudinary upload, overlays, Search API, signed URLs | ✅ Real |
| Vision AI classification (Gemini) | ✅ Real (opt-in, swappable) |
| Feature A: Remediation View (region remove + compare slider) | ✅ Real — policy-guarded |
| Feature B: Simulation Lab (async scenario synthesizer + edge SSIM) | ✅ Real — allowlisted |
| Feature C: Export Profiles (16:9, 9:16, 1:1 + canvas math) | ✅ Real — blur / solid / gen fill |
| Usage tracking & credit caps (`GET /admin/usage`) | ✅ Real |
| Asset retention & simulation cleanup (`cleanup_assets.py`) | ✅ Real |
| FLIR radiometric JPEG extraction (exiftool) | 🗺 Roadmap — CSV/NPY input works now |
| Multi-tenant auth, per-tenant folders | 🗺 Roadmap |
| Edge device SDK (Raspberry Pi / ESP32) | 🗺 Roadmap |
| HIPAA compliance | 🗺 Roadmap (legal + process, not just a feature) |

---

## Disclaimers

- **SpecimenTrace (Module C):** for research and education only. Not a diagnostic device. Never use real patient data.
- **SpectroTrace Audio (Module D):** audio anomaly screening heuristics, not a certified deepfake detector.
- All sample data is public and de-identified.

---

## License

MIT
