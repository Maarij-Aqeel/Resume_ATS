# ATS Resume Parser

LLM-first Applicant Tracking System resume parser targeting **≥95% field-level extraction accuracy**.

Built on FastAPI + Gemini (via OpenRouter) + PostgreSQL (pgvector) + Redis + ARQ. Production-ready architecture with a 5-layer pipeline: extractor → LLM parser → validator → normalizer → semantic matcher.

---

## Architecture

```
Upload (PDF/DOCX/DOC/TXT)
    │
    ▼
 Layer 1: Extractor  (pdfplumber → PyMuPDF → OCR fallback)
    │
    ▼
 Layer 2: Parser (Gemini with JSON mode — re-prompts up to 3x on invalid JSON)
    │
    ▼
 Layer 3: Validator (Pydantic + confidence score)
    │
    ▼
 Layer 4: Normalizer (skills ontology + date normalization)
    │
    ▼
 Layer 5: Matcher (embeddings + pgvector ANN + weighted scoring)
    │
    ▼
 PostgreSQL (parsed_data JSONB + 384-dim embedding)
```

Every layer is independently testable. Async LLM calls, ARQ background workers, and pgvector ANN search give you production-grade throughput.

---

## Quick start

### 1. Clone and configure

```bash
cp .env.example .env
# edit .env and set OPENROUTER_API_KEY
# get a key at: https://openrouter.ai/keys
# Free credits are granted on signup; free Gemini variant is available too.
```

### 2. Start everything

```bash
docker-compose up --build
```

This starts Postgres (with pgvector), Redis, the FastAPI API, the ARQ worker, **and a Streamlit frontend**. Alembic migrations run automatically on API startup.

- **Frontend (recommended for testing):** http://localhost:8501
- **API docs (OpenAPI/Swagger):** http://localhost:8000/docs
- **API root:** http://localhost:8000

### 3. Test everything in the UI (easiest)

Open **http://localhost:8501** — the Streamlit frontend has four tabs:

- **Upload** — drag a PDF/DOCX/DOC/TXT in, parse synchronously or async, view the structured result with confidence score and a card for every section.
- **Resumes** — list, filter by status/confidence, view details, delete.
- **Jobs** — create job descriptions with required skills + years; browse existing ones.
- **Match** — pick a resume + job to score pairwise, OR pick a job to rank top candidates (pgvector ANN under the hood).

The sidebar shows live backend metrics (total parsed, avg confidence, OCR rate, failure count).

### 4. Parse a resume via curl

**Synchronous (recommended for <5 page resumes):**
```bash
curl -X POST http://localhost:8000/api/v1/resumes/upload/sync \
  -F "file=@path/to/resume.pdf"
```

**Asynchronous (returns immediately, parse runs in worker):**
```bash
# Upload
curl -X POST http://localhost:8000/api/v1/resumes/upload \
  -F "file=@path/to/resume.pdf"
# → {"resume_id": "abc-...", "status": "processing"}

# Poll status
curl http://localhost:8000/api/v1/resumes/abc-.../status

# Fetch full result
curl http://localhost:8000/api/v1/resumes/abc-...
```

### 5. Create a job + match

```bash
# Create a job description
curl -X POST http://localhost:8000/api/v1/jobs/ \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Senior Python Engineer",
    "company": "Acme Corp",
    "description": "We need a senior engineer with 5+ years of Python, FastAPI, PostgreSQL, and AWS experience.",
    "required_skills": ["Python", "FastAPI", "PostgreSQL", "AWS"],
    "required_years": 5
  }'
# → {"job_id": "xyz-...", ...}

# Compute a specific match
curl -X POST http://localhost:8000/api/v1/match/resume/<RESUME_ID>/job/<JOB_ID>

# Get top candidates for a job (pgvector ANN + re-ranking)
curl -X POST http://localhost:8000/api/v1/match/job/<JOB_ID>/top-candidates \
  -H "Content-Type: application/json" \
  -d '{"limit": 20, "min_score": 0.5}'
```

---

## Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/resumes/upload` | Async upload — returns resume_id, enqueues parse |
| `POST` | `/api/v1/resumes/upload/sync` | Synchronous upload — returns parsed JSON |
| `GET` | `/api/v1/resumes/{id}` | Full parsed resume |
| `GET` | `/api/v1/resumes/{id}/status` | Parse status + confidence |
| `GET` | `/api/v1/resumes/` | List (filter by status, min_confidence) |
| `DELETE` | `/api/v1/resumes/{id}` | Delete a resume |
| `POST` | `/api/v1/jobs/` | Create job description |
| `GET` | `/api/v1/jobs/{id}` | Job details |
| `POST` | `/api/v1/match/resume/{rid}/job/{jid}` | Score one resume against one job |
| `POST` | `/api/v1/match/job/{id}/top-candidates` | Top-N candidates for a job |
| `POST` | `/api/v1/match/resume/{id}/top-jobs` | Top-N jobs for a resume |
| `GET` | `/api/v1/metrics/accuracy` | Parser accuracy stats |

---

## Configuration

All configuration is via environment variables (see `.env.example`):

| Variable | Default | Purpose |
|---|---|---|
| `OPENROUTER_API_KEY` | **required** | OpenRouter key — https://openrouter.ai/keys |
| `DATABASE_URL` | postgres asyncpg URL | Postgres connection |
| `REDIS_URL` | `redis://redis:6379` | Redis for ARQ |
| `LLM_MODEL` | `google/gemini-2.0-flash-exp:free` | OpenRouter model ID in `vendor/model` form. Gemini options: `google/gemini-2.0-flash-exp:free` (free, rate-limited), `google/gemini-2.0-flash-001` (cheap), `google/gemini-2.5-flash`, `google/gemini-2.5-pro` |
| `LLM_TEMPERATURE` | `0.0` | Deterministic — do not change for production |
| `LLM_MAX_TOKENS` | `4096` | Max output tokens |
| `LLM_MAX_RETRIES` | `3` | Re-prompt attempts on invalid JSON |
| `MAX_FILE_SIZE_MB` | `10` | Upload size cap |
| `MIN_CONFIDENCE_FOR_AUTO_ACCEPT` | `0.70` | Below this → `review_needed` |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | 384-dim sentence-transformer |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | (optional) | Textract OCR (falls back to Tesseract) |

---

## Testing

### Unit tests
```bash
pytest tests/unit/
```

### Accuracy benchmark

1. Place 20 manually verified `(resume_file, ground_truth_json)` pairs in `tests/accuracy/fixtures/`:
   ```
   tests/accuracy/fixtures/
     alice.pdf
     alice.gt.json
     bob.docx
     bob.gt.json
     ...
   ```
   Each `*.gt.json` must match the `ResumeSchema` shape (see `app/models/schemas.py`).

2. Run the benchmark:
   ```bash
   pytest tests/accuracy/ --benchmark
   ```

3. Target thresholds (test fails if below):
   | Field | Target |
   |---|---|
   | name | 98% |
   | email | 99% |
   | phone | 95% |
   | skills (F1) | 90% |
   | experience count | 95% |
   | experience dates | 92% |
   | education | 95% |
   | title | 90% |
   | **overall** | **95%** |

---

## Key design decisions

- **LLM-first, deterministic post-processing** — Gemini at `temperature=0.0` via OpenRouter with `response_format={"type": "json_object"}` produces the structured extraction; Pydantic + regex + ontology lookups enforce validity.
- **Why OpenRouter** — aggregates Gemini/Claude/Llama/GPT access behind one key + one OpenAI-compatible API; pay-as-you-go billing + a free Gemini tier. Swap models by changing `LLM_MODEL` in `.env` without touching code.
- **Re-prompt loop** — on invalid JSON, the model sees the exact error and retries (up to 3×).
- **Skill ontology** — 995 alias entries normalize `reactjs`/`React.js`/`React JS` → `React`. Raw LLM output has inconsistent skill names; normalization is not optional.
- **Waterfall extraction** — pdfplumber → PyMuPDF → OCR (Textract, Tesseract fallback). Column-aware text ordering preserves reading order in multi-column PDFs.
- **Confidence scoring + review queue** — resumes below 0.70 confidence are flagged `review_needed` rather than silently accepted.
- **pgvector ANN** — top-candidates uses an IVFFlat cosine index. Re-ranking with the full weighted-score formula happens client-side on a small candidate set.

---

## Project layout

```
app/
  main.py                         FastAPI entry point
  config.py                       pydantic-settings
  api/routes/
    resumes.py                    upload, get, list, delete
    jobs.py                       job CRUD
    match.py                      score + top-N
    metrics.py                    parser accuracy stats
  pipeline/
    extractor.py                  Layer 1 — file → raw text
    parser.py                     Layer 2 — LLM parse
    validator.py                  Layer 3 — Pydantic + confidence
    normalizer.py                 Layer 4 — skills + dates
    matcher.py                    Layer 5 — semantic match
    runner.py                     end-to-end orchestration
  models/
    schemas.py                    Pydantic DTOs
    db.py                         SQLAlchemy ORM
  services/
    llm.py                        OpenRouter client (Gemini) + JSON mode + re-prompt
    ocr.py                        Textract / Tesseract
    embeddings.py                 fastembed (ONNX, no torch)
  workers/parse_worker.py         ARQ background worker
  utils/
    text_cleaner.py               quality validation
    date_parser.py                YYYY-MM normalization
    skill_ontology.py             skill normalization
frontend/
  streamlit_app.py                4-tab UI (upload / resumes / jobs / match)
  Dockerfile
  requirements.txt
data/
  skills_ontology.json            995 aliases + categories
alembic/
  versions/0001_initial.py        schema + pgvector indexes
tests/
  unit/                           schema, ontology, dates
  accuracy/                       benchmark + fixtures
docker-compose.yml
Dockerfile
```

---

## Troubleshooting

- **OCR always firing** — the waterfall goes to OCR when pdfplumber+PyMuPDF both return low-quality text. Check `quality_score` in the logs; increase `MIN_TEXT_LENGTH` if your resumes are short.
- **Low confidence scores** — confidence is computed from field coverage (see `compute_confidence` in `validator.py`). If you're missing phone numbers across many resumes, the Gemini system prompt may need domain-specific tuning.
- **`.doc` files failing** — requires LibreOffice in the container. Verify with `docker-compose exec api libreoffice --version`.
- **pgvector errors** — ensure the image is `pgvector/pgvector:pg15`, not vanilla postgres.
- **OpenRouter rate limits** — the `:free` Gemini variants have strict caps (usually ~20 RPM, ~200/day). If you hit them, switch `LLM_MODEL` to a paid variant (`google/gemini-2.0-flash-001` is very cheap). All `:free` models count against a shared free-tier pool.
- **Truncated JSON** — response was cut off (usually `Unterminated string` error). Bump `LLM_MAX_TOKENS` in `.env`. Gemini 2.x supports up to ~65k output tokens.
- **Model not found errors on OpenRouter** — check https://openrouter.ai/models for the current slug; model IDs change (`:free` suffixes come and go).

---

## Cleanup & Uninstall

All Docker artifacts (images, containers, volumes) live inside Docker Desktop's VM, **not** in your normal filesystem. Use these commands to reclaim disk space.

### Daily / quick

```bash
docker-compose down          # stop services, keep images + postgres data (fast restart)
```

### Wipe postgres data, keep images

```bash
docker-compose down -v       # also removes the postgres_data volume
```

### Wipe everything for this project

```bash
docker-compose down -v --rmi all    # stops, removes volumes AND deletes the built images
```

### See what Docker is using

```bash
docker system df
```

Sample output:
```
TYPE            TOTAL     ACTIVE    SIZE      RECLAIMABLE
Images          3         1         4.8GB     2.1GB (43%)
Containers      4         0         20MB      20MB (100%)
Volumes         1         0         350MB     350MB (100%)
```

### Nuclear — reclaim space from ALL Docker projects on your machine

```bash
docker system prune -a --volumes
```

Asks for confirmation, then deletes every stopped container, unused image, unused network, and unused volume across every Docker project. Use when your disk is tight.

### Uninstall Docker Desktop completely

```bash
brew uninstall --cask docker
rm -rf ~/Library/Containers/com.docker.docker
rm -rf ~/Library/Application\ Support/Docker\ Desktop
rm -rf ~/.docker
```

This reclaims the full Docker Desktop VM (typically 5–15 GB). You can reinstall anytime with `brew install --cask docker`.

---

## Deploy for Free

The stack has three moving pieces: FastAPI, PostgreSQL+pgvector, Redis. The worker is optional — **if you only use the `/upload/sync` endpoint, you can skip Redis + the worker entirely**, which makes free deployment dramatically easier.

Below are two paths, easiest first.

### Option A — Render.com (simplest, 5-minute deploy)

Free tier: 1 web service (sleeps after 15 min inactivity; cold start ~30s), 1 Postgres instance free for 90 days (then $7/mo), no Redis on free tier. For this project, drop the worker and use only `/upload/sync`.

1. **Sign up**: https://render.com (GitHub sign-in; no credit card).

2. **Push your code to GitHub** (Render deploys from a repo):
   ```bash
   git init && git add . && git commit -m "initial"
   gh repo create ats-parser --public --source=. --push   # or manual GitHub UI
   ```

3. **Create a Postgres database** in Render dashboard → New → PostgreSQL → Free tier. Render's free Postgres doesn't have pgvector preinstalled, so **use [Neon](https://neon.tech) instead** — free forever, pgvector is one click:
   - Sign up at neon.tech → Create Project → in SQL Editor run: `CREATE EXTENSION vector;`
   - Copy the `postgresql://...` connection string.
   - Convert to asyncpg form: replace `postgresql://` with `postgresql+asyncpg://`.

4. **Create a Web Service** in Render dashboard → New → Web Service → connect your GitHub repo → Docker runtime. Set:
   - **Build Command**: (leave blank; uses Dockerfile)
   - **Start Command**: `alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Environment variables**:
     ```
     GOOGLE_API_KEY=<your gemini key>
     DATABASE_URL=postgresql+asyncpg://<neon connection string>
     LLM_MODEL=gemini-2.5-flash
     ```

5. **Deploy**. First build takes 10–15 min (installs LibreOffice, Tesseract, sentence-transformers). After that you'll get a URL like `https://ats-parser.onrender.com`.

6. **Test**:
   ```bash
   curl -X POST https://ats-parser.onrender.com/api/v1/resumes/upload/sync \
     -F "file=@/path/to/resume.pdf"
   ```

**Caveats**:
- Service sleeps after 15 minutes → first request takes ~30s to wake.
- No async `/upload` endpoint (no Redis). Use `/upload/sync` only.
- Free Postgres on Render dies at 90 days — use Neon to avoid this.

### Option B — Google Cloud Run + Neon + Upstash (most generous free tier)

For a more robust free setup — higher quotas, no idle sleep, forever-free Postgres + Redis — but requires a bit more ops.

| Component | Service | Free tier |
|---|---|---|
| FastAPI API | **Google Cloud Run** | 2M requests/month, 360K GB-seconds memory, 180K vCPU-seconds |
| PostgreSQL + pgvector | **Neon** | 0.5 GB storage, pgvector built-in, never expires |
| Redis | **Upstash** | 10K commands/day, 256 MB, never expires |
| LLM | **Gemini API** | 15 requests/min on `gemini-2.5-flash` |

1. **Neon**: sign up, create project, enable pgvector (`CREATE EXTENSION vector;`), copy connection string.

2. **Upstash**: sign up at upstash.com → Create Redis Database (free tier, TLS) → copy the `rediss://` connection URL.

3. **Google Cloud**: sign up (requires credit card for verification but free tier doesn't charge). Enable the Cloud Run API. Install `gcloud` CLI, `gcloud auth login`, `gcloud config set project <your-project>`.

4. **Deploy API**:
   ```bash
   gcloud run deploy ats-parser \
     --source . \
     --region us-central1 \
     --memory 2Gi \
     --cpu 1 \
     --timeout 300 \
     --allow-unauthenticated \
     --set-env-vars \
       GOOGLE_API_KEY=<your_key>,\
       DATABASE_URL=postgresql+asyncpg://<neon_url>,\
       REDIS_URL=rediss://<upstash_url>,\
       LLM_MODEL=gemini-2.5-flash
   ```

5. **Run migrations once** (Cloud Run doesn't run them on boot like docker-compose does):
   ```bash
   gcloud run jobs create ats-migrate \
     --image <your-image-from-step-4> \
     --region us-central1 \
     --set-env-vars DATABASE_URL=postgresql+asyncpg://<neon_url> \
     --command alembic --args upgrade,head
   gcloud run jobs execute ats-migrate --region us-central1
   ```

6. **Worker (optional)** — deploy the same image as a second Cloud Run service with a different start command, or use [Cloud Run Jobs](https://cloud.google.com/run/docs/create-jobs) triggered by Cloud Scheduler. If you don't need async parsing, skip this.

**Caveats**:
- Cloud Run cold-starts the sentence-transformer model on first request (~5s overhead). Use `--min-instances 1` to eliminate this (but that leaves the free tier).
- You'll need a Google Cloud account with billing enabled (free tier doesn't charge, but billing must be set up).

### Option C — Skip the deploy, share via `ngrok` (demo/testing only)

For showing someone the running app without deploying anywhere:

```bash
docker-compose up
# In another terminal:
brew install ngrok
ngrok http 8000
```

Ngrok gives you a `https://<random>.ngrok-free.app` URL that tunnels to your local API. Free tier: 1 active tunnel, random URL each session. Not for production, fine for demos.

### Recommendation

- **Just want it live ASAP, don't need async** → Option A (Render + Neon).
- **Want the most headroom on free tier, willing to configure 3 services** → Option B (Cloud Run + Neon + Upstash).
- **Just want to show someone it works** → Option C (ngrok).

All three keep Gemini as the LLM — its free tier (15 RPM on `gemini-2.5-flash`) is enough for personal use; if you're parsing hundreds of resumes an hour you'll need a paid Gemini tier regardless of where you host.
