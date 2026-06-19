# TTB Label Verification App

Phase 0 proves the deployment path: a FastAPI backend health endpoint and a React/Vite frontend that calls it. The backend and frontend deploy to Vercel as separate projects from this repository.

## Local Requirements

- Python 3.12, or `uv` allowed to download/use Python 3.12
- `uv`
- Node.js 20 or newer
- npm
- Vercel account for deployment

## Run Locally

Backend:

```powershell
cd backend
uv sync
uv run pytest
uv run uvicorn api.index:app --reload --port 8000
```

If `uv` is installed but not on your PowerShell PATH, use:

```powershell
python -m uv sync
python -m uv run pytest
python -m uv run uvicorn api.index:app --reload --port 8000
```

Health endpoint:

```text
http://127.0.0.1:8000/health
```

Frontend, in a second terminal:

```powershell
cd frontend
copy .env.example .env.local
npm.cmd install
npm.cmd run dev
```

Open:

```text
http://localhost:5173
```

## Deploy To Vercel

Create two Vercel projects from the same GitHub repository.

Backend project:

- Root directory: `backend`
- Framework preset: Other
- Environment variables:

```text
APP_ENV=production
ALLOWED_ORIGINS=https://<your-frontend-project>.vercel.app
```

Frontend project:

- Root directory: `frontend`
- Framework preset: Vite
- Build command: `npm run build`
- Output directory: `dist`
- Environment variables:

```text
VITE_API_BASE_URL=https://<your-backend-project>.vercel.app
```

CLI deploy option:

```powershell
npm.cmd install -g vercel

cd backend
vercel
vercel --prod

cd ..\frontend
vercel
vercel --prod
```

After the frontend deploy URL is known, make sure the backend project's `ALLOWED_ORIGINS` exactly matches that frontend URL, then redeploy the backend if needed.

## Exit Check

- Backend live URL returns HTTP 200 at `/health`.
- Frontend live URL loads.
- Frontend displays the backend health JSON.
- No real secrets are tracked:

```powershell
git ls-files | findstr /i ".env"
```

Expected tracked env files are only:

```text
backend/.env.example
frontend/.env.example
```

