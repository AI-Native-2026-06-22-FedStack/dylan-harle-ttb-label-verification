# TTB Label Verification App

A proof-of-concept web app that compares submitted alcohol beverage application data against uploaded label images. The app extracts visible label text with a vision model, compares each field, and returns a clear APPROVED or NEEDS REVIEW result for a single label or a batch of labels.

This is a prototype helper for review workflows. It is not an official TTB compliance determination.

## Live Demo

- Frontend: https://frontend-gamma-silk-13.vercel.app
- Backend health: https://backend-rho-amber-37.vercel.app/health
- Last verified: 2026-07-10. Both URLs returned HTTP 200.

## Features

- Single-label verification
- Batch upload verification
- Exact case-sensitive government warning check
- Fuzzy and normalized comparison for all other fields
- Field-by-field PASS/FAIL results with an overall verdict
- Friendly validation errors for missing fields, wrong file types, and unreadable images
- Accessible UI basics: large readable text, labeled controls, keyboard focus states, status announcements, and large tap targets

## How It Works

The frontend collects the expected application data and one or more label images. The FastAPI backend validates the form and image uploads, preprocesses label images, asks the OpenAI vision model to extract visible text, and compares extracted values against the submitted fields.

The app is stateless and does not use a database. Uploaded images and extracted values are processed only for the request/response cycle.

## Tech Stack / Vision Model

- Backend: Python 3.12, FastAPI, Pillow, pillow-heif, RapidFuzz, OpenAI API, Vercel Python runtime
- Frontend: React, Vite, Vitest, Testing Library, Vercel static hosting
- Vision model: `gpt-5.4-mini`
- Model verification: `uv run python scripts/check_vision_model.py` checks `OPENAI_VISION_MODEL` against the OpenAI Models API using the configured `OPENAI_API_KEY`.
- Last model verification attempt: 2026-07-10. The check reached OpenAI but could not complete because the configured key lacks the `api.model.read` scope required by the Models API.

Main backend endpoints:

- `GET /health`
- `POST /verify`
- `POST /verify/batch`

## API Examples

The examples below use the current API contract implemented in this repository.

Single-label verification:

```bash
curl -X POST "https://backend-rho-amber-37.vercel.app/verify" \
  -F "image=@sample.jpg" \
  -F "brand_name=Acme Cellars" \
  -F "class_type=Red Wine" \
  -F "producer=Acme Winery LLC" \
  -F "country_of_origin=United States" \
  -F "abv=13.5%" \
  -F "net_contents=750 mL" \
  -F "government_warning=GOVERNMENT WARNING: (1) ACCORDING TO THE SURGEON GENERAL, WOMEN SHOULD NOT DRINK ALCOHOLIC BEVERAGES DURING PREGNANCY BECAUSE OF THE RISK OF BIRTH DEFECTS. (2) CONSUMPTION OF ALCOHOLIC BEVERAGES IMPAIRS YOUR ABILITY TO DRIVE A CAR OR OPERATE MACHINERY, AND MAY CAUSE HEALTH PROBLEMS."
```

Batch verification with one application record per image:

```bash
curl -X POST "https://backend-rho-amber-37.vercel.app/verify/batch" \
  -F "images=@label-1.jpg" \
  -F "images=@label-2.jpg" \
  -F 'applications=[
    {
      "brand_name": "Acme Cellars",
      "class_type": "Red Wine",
      "producer": "Acme Winery LLC",
      "country_of_origin": "United States",
      "abv": "13.5%",
      "net_contents": "750 mL",
      "government_warning": "GOVERNMENT WARNING: (1) ACCORDING TO THE SURGEON GENERAL, WOMEN SHOULD NOT DRINK ALCOHOLIC BEVERAGES DURING PREGNANCY BECAUSE OF THE RISK OF BIRTH DEFECTS. (2) CONSUMPTION OF ALCOHOLIC BEVERAGES IMPAIRS YOUR ABILITY TO DRIVE A CAR OR OPERATE MACHINERY, AND MAY CAUSE HEALTH PROBLEMS."
    },
    {
      "brand_name": "Acme Cellars Reserve",
      "class_type": "Red Wine",
      "producer": "Acme Winery LLC",
      "country_of_origin": "United States",
      "abv": "14.0%",
      "net_contents": "750 mL",
      "government_warning": "GOVERNMENT WARNING: (1) ACCORDING TO THE SURGEON GENERAL, WOMEN SHOULD NOT DRINK ALCOHOLIC BEVERAGES DURING PREGNANCY BECAUSE OF THE RISK OF BIRTH DEFECTS. (2) CONSUMPTION OF ALCOHOLIC BEVERAGES IMPAIRS YOUR ABILITY TO DRIVE A CAR OR OPERATE MACHINERY, AND MAY CAUSE HEALTH PROBLEMS."
    }
  ]'
```

Successful single-label response shape:

```json
{
  "overall_verdict": "APPROVED",
  "results": [
    {
      "field": "brand_name",
      "status": "PASS",
      "expected": "Acme Cellars",
      "found": "ACME CELLARS",
      "match_type": "fuzzy_token_set_ratio",
      "score": 100.0,
      "message": "Fuzzy score 100.00; threshold 90.00."
    }
  ],
  "latency_ms": 1200
}
```

Successful batch response shape:

```json
{
  "summary": {
    "total": 2,
    "passed": 1,
    "needs_review": 1
  },
  "items": [
    {
      "index": 0,
      "filename": "label-1.jpg",
      "status": "APPROVED",
      "result": {
        "overall_verdict": "APPROVED",
        "results": [],
        "latency_ms": 1200
      },
      "error": null,
      "latency_ms": 1200
    }
  ],
  "latency_ms": 1500
}
```

Error response shape:

```json
{
  "error": {
    "code": "missing_required_field",
    "message": "Please upload a label image.",
    "latency_ms": 0
  }
}
```

## Comparison Rules

| Field | Strategy | Passing rule |
| --- | --- | --- |
| `brand_name` | Fuzzy token-set match | Score must be at least `90`. |
| `class_type` | Fuzzy token-set match | Score must be at least `88`. |
| `producer` | Fuzzy token-set match | Score must be at least `90`. |
| `country_of_origin` | Canonical country synonym and prefix normalization | Values must resolve to the same canonical country; examples include `USA` and `United States`. |
| `abv` | Numeric normalization | Difference must be `0.1` or less; supports `%`, `Alc./Vol.`, and proof such as `90 Proof` equals `45%`. |
| `net_contents` | Unit normalization to mL | Difference must be `1 mL` or less; supports `mL`, `L`, `cL`, `fl oz`, `fluid ounce(s)`, and `oz`. |
| `government_warning` | Exact case-sensitive wording and punctuation after whitespace folding | Text must match the required warning exactly except for visual line wrapping or repeated whitespace. FAIL results include the extracted warning in `found` for reviewer override. |

## Local Requirements

- Python 3.12
- `uv`
- Node.js 20 or newer
- npm
- OpenAI API key

## Backend Setup

```bash
cd backend
cp .env.example .env
```

Edit `backend/.env` and set:

```text
OPENAI_API_KEY=
ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

Paste your OpenAI key after `OPENAI_API_KEY=` in the local `.env` file only.

Install dependencies, run tests, and start the backend:

```bash
uv sync
uv run pytest
uv run uvicorn api.index:app --reload --port 8000
```

If `uv` is installed but not available on your shell `PATH`, use:

```bash
python -m uv sync
python -m uv run pytest
python -m uv run uvicorn api.index:app --reload --port 8000
```

On Windows Command Prompt, use `copy .env.example .env` instead of `cp .env.example .env`.

Health check:

```text
http://127.0.0.1:8000/health
```

## Frontend Setup

Open a second terminal:

```bash
cd frontend
cp .env.example .env.local
npm install
npm run dev
```

On Windows Command Prompt, use `copy .env.example .env.local` instead of `cp .env.example .env.local`.

For local development, `frontend/.env.local` should contain:

```text
VITE_API_BASE_URL=http://localhost:8000
```

Open:

```text
http://localhost:5173
```

## Environment Variables

Backend:

| Variable | Required | Default | Purpose |
| --- | --- | --- | --- |
| `APP_ENV` | No | `local` | Names the runtime environment returned by `/health`. |
| `ALLOWED_ORIGINS` | Yes in production | `http://localhost:5173,http://127.0.0.1:5173` | Comma-separated CORS allowlist. Production should be restricted to the deployed frontend URL. |
| `OPENAI_API_KEY` | Yes | None | OpenAI API key used by the vision extractor. Never commit this value. |
| `OPENAI_VISION_MODEL` | Yes | None | Vision-capable model used for extraction. Production currently uses `gpt-5.4-mini`. |
| `OPENAI_IMAGE_DETAIL` | No | `high` | Image detail sent to the provider. |
| `OPENAI_VISION_TIMEOUT_SECONDS` | No | `3.8` | Provider timeout used to protect the 5-second target. |
| `OPENAI_MAX_IMAGE_LONG_EDGE` | No | `1280` | Maximum image long edge after backend preprocessing. |
| `OPENAI_JPEG_QUALITY` | No | `85` | First JPEG quality attempted during preprocessing. |
| `OPENAI_MIN_JPEG_QUALITY` | No | `82` | Lower JPEG quality fallback during preprocessing. |
| `OPENAI_MAX_PROCESSED_BYTES` | No | `2097152` | Maximum processed image size sent to the provider. |
| `OPENAI_MAX_IMAGE_PIXELS` | No | `20000000` | Maximum decoded image pixel count accepted by backend preprocessing. |
| `BATCH_CONCURRENCY` | No | `3` | Maximum concurrent batch item verifications, clamped between `1` and `10`. |

Frontend:

| Variable | Required | Default | Purpose |
| --- | --- | --- | --- |
| `VITE_API_BASE_URL` | Yes | `http://localhost:8000` in `.env.example` | Backend base URL used by the browser app. |

Real secrets must stay in local `.env` files or hosting-provider environment variables only. Do not commit API keys.

## Deployment

The backend and frontend are deployed as separate Vercel projects from this repository. The deploy contract is versioned in `backend/vercel.json` and `frontend/vercel.json`.

Backend project:

- Root directory: `backend`
- Framework preset: FastAPI
- Runtime config: `backend/vercel.json`
- Production environment variables include `OPENAI_API_KEY`, `APP_ENV=production`, `ALLOWED_ORIGINS=https://frontend-gamma-silk-13.vercel.app`, `OPENAI_VISION_MODEL=gpt-5.4-mini`, and the OpenAI/image tuning variables from `backend/.env.example`
- `OPENAI_API_KEY` is configured only in Vercel Project Settings or local `.env`; it is not stored in `vercel.json`
- Startup logs include `APP_ENV`, resolved `ALLOWED_ORIGINS`, and resolved `OPENAI_VISION_MODEL` so reviewers can audit config without exposing secrets

Frontend project:

- Root directory: `frontend`
- Framework preset: Vite
- Runtime config: `frontend/vercel.json`
- Build command: `npm run build`
- Output directory: `dist`
- Production environment variable: `VITE_API_BASE_URL=https://backend-rho-amber-37.vercel.app`

After changing production environment variables, redeploy the affected Vercel project.

Before deployment, verify the model name is available to the provider:

```bash
cd backend
uv run python scripts/check_vision_model.py
```

## Performance

Target: a single-label verification should return in under 5 seconds.

Measured live performance on 2026-07-10 against `https://backend-rho-amber-37.vercel.app` with `--speed-runs 5`:

| Metric | p50 | p95 |
| --- | ---: | ---: |
| Server latency | 2120 ms | 2252 ms |
| Wall latency | 2323 ms | 2459 ms |

The full live checklist passed, including valid label, mismatch, case-only match, warning failures, batch summary, and single-label latency under 5 seconds. The first valid-label request in the run took `4431 ms` server time and `4974 ms` wall time, likely including Vercel cold-start overhead.

To refresh the measurements, rerun:

```bash
cd backend
uv run python scripts/phase6_live_check.py https://backend-rho-amber-37.vercel.app --speed-runs 5
```

Record the `single_label_speed_summary` `server_latency_ms.p50`, `server_latency_ms.p95`, `wall_latency_ms.p50`, and `wall_latency_ms.p95` values here with the run count, date, and backend URL. The first request on Vercel may include cold-start latency.

## Tradeoffs

- Vercel serverless hosting keeps deployment simple for the proof-of-concept, but cold starts and provider network latency can affect the first request.
- The backend enforces a raw 2 MB upload cap per image. The frontend lets users select broad image files, then downsizes and recompresses browser-decodable photos to JPEG before upload. If a HEIC/HEIF file cannot be decoded in the browser but is already under 2 MB, the frontend sends it directly for backend decoding. Direct API callers using `curl` may send JPEG, PNG, WebP, HEIC, or HEIF files under 2 MB.
- Batch upload is capped at 10 images to keep free-tier runtime and latency predictable.
- The app has no database, authentication, or persistence by design.
- NEEDS REVIEW results are intended for human review; the app surfaces field-level evidence and extracted warning text but does not make final regulatory determinations.

## Approach / Tools

Development used Codex with the project PLAN, REVIEW, EXECUTE cadence: plan the phase, critique it against requirements, then implement the approved scope with tests. Codex generated and edited code and documentation, while the human operator selected priorities, approved scope, and reviewed the resulting behavior. Key tools and libraries include Python 3.12, FastAPI, uv, pytest, React, Vite, Vitest, OpenAI API, Pillow, pillow-heif, RapidFuzz, and Vercel.

## Assumptions

- The user manually enters the expected application data.
- Browser uploads are converted to JPEG when the browser can decode the selected image. Direct API uploads can be JPEG, PNG, WebP, HEIC, or HEIF images within the app's size limits.
- The app is intended for proof-of-concept review, not production regulatory use.
- Free-tier hosting may have occasional cold-start or network latency variance.

## Limitations

- Vision extraction can misread blurry, cropped, angled, low-contrast, or otherwise imperfect labels.
- The app does not persist uploads, results, or user sessions.
- There is no authentication or database.
- The model output can vary between requests, especially on marginal images.
- The configured OpenAI free-tier quota may stop repeated live tests after about 50 model requests per day. When that happens, the app may return HTTP `502` with error code `extraction_unavailable` and message `Label extraction is temporarily unavailable. Please try again.` The underlying provider error is an OpenAI `429 RateLimitError` / `rate_limit_exceeded` response such as `Rate limit reached ... on requests per day (RPD): Limit 50, Used 50, Requested 1. Please try again later.`
- A reviewer should manually inspect any NEEDS REVIEW result.
- Direct API uploads are not compressed by the backend before the 2 MB request cap is enforced. Use the browser UI for automatic client-side preparation, or resize/recompress files before sending them with `curl`. HEIC/HEIF direct uploads are decoded on the backend after upload validation and normalized to JPEG before vision extraction.

## Verification

Local backend tests:

```bash
cd backend
uv run pytest
```

Frontend tests:

```bash
cd frontend
npm test -- --run
```

Frontend production build:

```bash
cd frontend
npm run build
```

Vision model configuration check:

```bash
cd backend
uv run python scripts/check_vision_model.py
```

Live checklist against the deployed backend:

```bash
cd backend
uv run python scripts/phase6_live_check.py https://backend-rho-amber-37.vercel.app --speed-runs 5
```

Expected result after redeploying the current backend: the checklist passes, including valid label, mismatches, case-only match, ABV and unit normalization, government warning scenarios, imperfect image handling, wrong file type, empty submit, batch summary, and single-label latency under 5 seconds.

If repeated live checklist runs suddenly fail with `extraction_unavailable`, check whether the OpenAI request-per-day limit has been reached before treating it as an application failure.

## Secret Audit

Before submitting or pushing, confirm only example env files are tracked:

```bash
git ls-files | rg "(^|/)\.env($|\.)"
```

Expected tracked files:

```text
backend/.env.example
frontend/.env.example
```

Confirm local env and Vercel files are ignored:

```bash
git check-ignore -v backend/.env frontend/.env.local backend/.vercel frontend/.vercel
```

Scan tracked files for likely committed secrets:

```bash
git grep -n -I -E "sk-[A-Za-z0-9_-]{20,}" -- .
git grep -n -I -E "OPENAI_API_KEY=[A-Za-z0-9_./+=-]+" -- .
git grep -n -I -E "(api[_-]?key|secret|token)[[:space:]]*[:=]" -- .
```

Generic code references to environment variable names are acceptable. Real key values are not.
