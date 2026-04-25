# ATS Resume Parser — Backend

LLM-first Applicant Tracking System resume parser. FastAPI backend + ARQ async worker in one image, targeting **≥95% field-level extraction accuracy** on PDF/DOCX/DOC/TXT/RTF resumes.

**Short description (100 chars max — for the field at the top of Docker Hub):**
> FastAPI + Gemini-via-OpenRouter resume parser. PDF/DOCX/DOC parsing, semantic matching, pgvector ANN.

---

## What's inside

A 5-layer pipeline:

1. **Extractor** — pdfplumber → PyMuPDF → OCR fallback (column-aware ordering for multi-column PDFs)
2. **LLM Parser** — Gemini via OpenRouter, JSON mode, with re-prompt loop on invalid JSON (3 attempts)
3. **Validator** — Pydantic v2 with email/phone/URL/date validators + confidence scoring
4. **Normalizer** — 995-entry skills ontology + `YYYY-MM` date normalization (`Jan 2021`, `Q1 2021`, `Spring 2021`, `Present`)
5. **Matcher** — sentence embeddings (fastembed/ONNX, no torch) + pgvector ANN + 5-factor weighted score

This image runs **both** the FastAPI HTTP server and the ARQ background worker — different commands, same code.

System dependencies pre-installed:
- LibreOffice (for `.doc` → `.docx` conversion)
- Tesseract (OCR fallback when PDFs have no extractable text)
- Poppler utils (PDF helpers)

---

## Tags

| Tag | Description |
|---|---|
| `latest` | Most recent stable build |
| `1.0` | Pinned semantic version |

**Supported architectures:** `linux/amd64`, `linux/arm64` (Apple Silicon native)

**Image size:** ~1.5 GB (LibreOffice + Tesseract are the bulk; pip layer is ~250 MB)

---

## Quick start

You need three things: this image, a Postgres with pgvector, and an OpenRouter API key.

### Easiest — full stack with docker-compose

```bash
mkdir ats-parser && cd ats-parser
curl -O https://raw.githubusercontent.com/YOUR_REPO/main/docker-compose.prod.yml
echo "OPENROUTER_API_KEY=sk-or-v1-your_key" > .env
docker-compose -f docker-compose.prod.yml up -d
```

Open http://localhost:8000/docs — interactive Swagger UI for every endpoint.

Pair with the [`YOURUSER/ats-parser-frontend`](https://hub.docker.com/r/YOURUSER/ats-parser-frontend) image for a Streamlit UI at http://localhost:8501.

### Just the API (BYO Postgres + Redis)

```bash
docker run -d \
  --name ats-api \
  -p 8000:8000 \
  -e OPENROUTER_API_KEY=sk-or-v1-... \
  -e DATABASE_URL=postgresql+asyncpg://user:pass@your-postgres-host:5432/ats_parser \
  -e REDIS_URL=redis://your-redis-host:6379 \
  -e LLM_MODEL=google/gemini-2.5-flash \
  YOURUSER/ats-parser:latest \
  sh -c "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"
```

### Run as a worker instead

Same image, different command:

```bash
docker run -d \
  --name ats-worker \
  -e OPENROUTER_API_KEY=sk-or-v1-... \
  -e DATABASE_URL=postgresql+asyncpg://... \
  -e REDIS_URL=redis://... \
  YOURUSER/ats-parser:latest \
  python -m arq app.workers.parse_worker.WorkerSettings
```

---

## Environment variables

| Variable | Default | Required | Purpose |
|---|---|:---:|---|
| `OPENROUTER_API_KEY` | — | ✅ | OpenRouter key. Get one at https://openrouter.ai/keys |
| `DATABASE_URL` | — | ✅ | `postgresql+asyncpg://user:pass@host:port/db` — must be a Postgres with pgvector extension |
| `REDIS_URL` | `redis://redis:6379` |  | Redis for ARQ. Skip if you only use `/upload/sync` |
| `LLM_MODEL` | `google/gemini-2.5-flash` |  | OpenRouter model slug. See https://openrouter.ai/models |
| `LLM_TEMPERATURE` | `0.0` |  | Keep at 0.0 for deterministic JSON |
| `LLM_MAX_TOKENS` | `8192` |  | Bump higher (16384) for very long resumes |
| `LLM_MAX_RETRIES` | `3` |  | Re-prompt attempts on invalid JSON |
| `LLM_TIMEOUT_SECONDS` | `90` |  | Per-call timeout |
| `MAX_FILE_SIZE_MB` | `10` |  | Upload size cap |
| `MIN_CONFIDENCE_FOR_AUTO_ACCEPT` | `0.70` |  | Below this → status `review_needed` |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` |  | fastembed model — change requires DB schema migration |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | — |  | Optional Textract OCR (Tesseract used as fallback) |
| `AWS_REGION` | `us-east-1` |  |  |

---

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/v1/resumes/upload` | Async upload — queues parse job, returns `resume_id` |
| `POST` | `/api/v1/resumes/upload/sync` | Sync upload — returns parsed JSON inline (waits 30–90s) |
| `GET` | `/api/v1/resumes/{id}` | Full parsed resume |
| `GET` | `/api/v1/resumes/{id}/status` | Parse status + confidence |
| `GET` | `/api/v1/resumes/` | List with filters (status, min_confidence) |
| `DELETE` | `/api/v1/resumes/{id}` | Delete |
| `POST` | `/api/v1/jobs/` | Create job description |
| `GET` | `/api/v1/jobs/{id}` | Job details |
| `POST` | `/api/v1/match/resume/{rid}/job/{jid}` | Score one resume against one job |
| `POST` | `/api/v1/match/job/{id}/top-candidates` | Top-N resumes for a job (pgvector ANN) |
| `POST` | `/api/v1/match/resume/{id}/top-jobs` | Top-N jobs for a resume |
| `GET` | `/api/v1/metrics/accuracy` | Aggregate parser stats |
| `GET` | `/health` | Liveness check |

Full OpenAPI/Swagger docs at `http://your-host:8000/docs`.

---

## Database setup

The image ships with Alembic migrations. On first start, run them:

```bash
docker run --rm \
  -e DATABASE_URL=postgresql+asyncpg://... \
  YOURUSER/ats-parser:latest \
  alembic upgrade head
```

Migrations create the `resumes`, `job_descriptions`, `match_results`, `parse_failures` tables and the pgvector IVFFlat indexes for fast cosine-similarity search.

**Postgres requirement**: must have the `pgvector` extension. The official `pgvector/pgvector:pg15` image works out of the box. Hosted: [Neon](https://neon.tech) (free tier with pgvector), [Supabase](https://supabase.com).

---

## Example: parse a resume

```bash
curl -X POST http://localhost:8000/api/v1/resumes/upload/sync \
  -F "file=@resume.pdf"
```

Response:
```json
{
  "resume_id": "...",
  "status": "completed",
  "confidence_score": 0.92,
  "parsed_data": {
    "personal_info": { "full_name": "Jane Doe", "email": "jane@example.com", ... },
    "skills": { "technical": ["Python", "FastAPI", "PostgreSQL", ...] },
    "experience": [...],
    "education": [...],
    ...
  }
}
```

---

## Resource recommendations

| Workload | RAM | CPU |
|---|---|---|
| API only | 1 GB | 1 core |
| API + worker | 2 GB | 1–2 cores |
| API + worker + heavy OCR | 3 GB | 2 cores |

The first request loads the embedding model (~50 MB) into memory — keep `--min-instances 1` on cold-start-sensitive platforms (Cloud Run etc.) or accept ~5s warm-up latency.

---

## Source code

- **GitHub:** https://github.com/YOUR_REPO/ats-parser
- **Frontend:** https://hub.docker.com/r/YOURUSER/ats-parser-frontend
- **Issues / PRs:** GitHub repo issues tab

## License

MIT
