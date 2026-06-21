# TTB Label Verification App

A proof-of-concept web app that compares submitted alcohol beverage application data against uploaded label images. The app extracts visible label text with a vision model, compares each field, and returns a clear PASS or NEEDS REVIEW result for a single label or a batch of labels.

This is a prototype helper for review workflows. It is not an official TTB compliance determination.

## Live Demo

- Frontend: https://frontend-gamma-silk-13.vercel.app
- Backend health: https://backend-rho-amber-37.vercel.app/health

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

Main backend endpoints:

- `GET /health`
- `POST /verify`
- `POST /verify/batch`

## Local Requirements

- Python 3.12
- `uv`
- Node.js 20 or newer
- npm
- OpenAI API key

## Backend Setup

```powershell
cd backend
copy .env.example .env
```

Edit `backend/.env` and set:

```text
OPENAI_API_KEY=
ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

Paste your OpenAI key after `OPENAI_API_KEY=` in the local `.env` file only.

Install dependencies, run tests, and start the backend:

```powershell
uv sync
uv run pytest
uv run uvicorn api.index:app --reload --port 8000
```

If `uv` is installed but not available on your PowerShell `PATH`, use:

```powershell
python -m uv sync
python -m uv run pytest
python -m uv run uvicorn api.index:app --reload --port 8000
```

Health check:

```text
http://127.0.0.1:8000/health
```

## Frontend Setup

Open a second terminal:

```powershell
cd frontend
copy .env.example .env.local
npm.cmd install
npm.cmd run dev
```

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

- `APP_ENV`
- `ALLOWED_ORIGINS`
- `OPENAI_API_KEY`
- `OPENAI_VISION_MODEL`
- `OPENAI_IMAGE_DETAIL`
- `OPENAI_VISION_TIMEOUT_SECONDS`
- `OPENAI_MAX_IMAGE_LONG_EDGE`
- `OPENAI_JPEG_QUALITY`
- `OPENAI_MIN_JPEG_QUALITY`
- `OPENAI_MAX_PROCESSED_BYTES`
- `OPENAI_MAX_IMAGE_PIXELS`

Frontend:

- `VITE_API_BASE_URL`

Real secrets must stay in local `.env` files or hosting-provider environment variables only. Do not commit API keys.

## Deployment

The backend and frontend are deployed as separate Vercel projects from this repository.

Backend project:

- Root directory: `backend`
- Framework preset: Other
- Production environment variables include `OPENAI_API_KEY`, `APP_ENV=production`, `ALLOWED_ORIGINS`, and the OpenAI/image tuning variables from `backend/.env.example`

Frontend project:

- Root directory: `frontend`
- Framework preset: Vite
- Build command: `npm run build`
- Output directory: `dist`
- Production environment variable: `VITE_API_BASE_URL=https://backend-rho-amber-37.vercel.app`

After changing production environment variables, redeploy the affected Vercel project.

## Tools Used

- Python 3.12
- FastAPI
- uv
- pytest
- React
- Vite
- OpenAI API
- Pillow
- RapidFuzz
- Vercel

## Assumptions

- The user manually enters the expected application data.
- Uploaded labels are JPEG, PNG, or WebP images within the app's size limits.
- The app is intended for proof-of-concept review, not production regulatory use.
- Free-tier hosting may have occasional cold-start or network latency variance.

## Limitations

- Vision extraction can misread blurry, cropped, angled, low-contrast, or otherwise imperfect labels.
- The app does not persist uploads, results, or user sessions.
- There is no authentication or database.
- The model output can vary between requests, especially on marginal images.
- The configured OpenAI free-tier quota may stop repeated live tests after about 50 model requests per day. When that happens, the app may return HTTP `502` with error code `extraction_unavailable` and message `Label extraction is temporarily unavailable. Please try again.` The underlying provider error is an OpenAI `429 RateLimitError` / `rate_limit_exceeded` response such as `Rate limit reached ... on requests per day (RPD): Limit 50, Used 50, Requested 1. Please try again later.`
- A reviewer should manually inspect any NEEDS REVIEW result.

## Verification

Local backend tests:

```powershell
cd backend
uv run pytest
```

Frontend production build:

```powershell
cd frontend
npm.cmd run build
```

Live checklist against the deployed backend:

```powershell
cd backend
uv run python scripts\phase6_live_check.py https://backend-rho-amber-37.vercel.app --speed-runs 5
```

Expected result: the checklist passes, including valid label, mismatches, case-only match, ABV and unit normalization, government warning scenarios, imperfect image handling, wrong file type, empty submit, batch summary, and single-label latency under 5 seconds.

If repeated live checklist runs suddenly fail with `extraction_unavailable`, check whether the OpenAI request-per-day limit has been reached before treating it as an application failure.

## Secret Audit

Before submitting or pushing, confirm only example env files are tracked:

```powershell
git ls-files | rg "(^|/)\.env($|\.)"
```

Expected tracked files:

```text
backend/.env.example
frontend/.env.example
```

Confirm local env and Vercel files are ignored:

```powershell
git check-ignore -v backend/.env frontend/.env.local backend/.vercel frontend/.vercel
```

Scan tracked files for likely committed secrets:

```powershell
git grep -n -I -E "sk-[A-Za-z0-9_-]{20,}" -- .
git grep -n -I -E "OPENAI_API_KEY=[A-Za-z0-9_./+=-]+" -- .
git grep -n -I -E "(api[_-]?key|secret|token)[[:space:]]*[:=]" -- .
```

Generic code references to environment variable names are acceptable. Real key values are not.
