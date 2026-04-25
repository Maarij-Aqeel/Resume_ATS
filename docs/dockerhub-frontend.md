# ATS Resume Parser — Frontend

Streamlit web UI for the [`YOURUSER/ats-parser`](https://hub.docker.com/r/YOURUSER/ats-parser) backend. Drag-and-drop resume upload, browse parsed resumes, create job descriptions, and run resume↔job matching with one-click scoring.

**Short description (100 chars max — for the field at the top of Docker Hub):**
> Streamlit UI for ATS Resume Parser — upload resumes, create jobs, see match scores. 4-tab interface.

---

## What's inside

A 4-tab Streamlit app:

- **📤 Upload** — drag-and-drop PDF / DOCX / DOC / TXT. Sync or async parse. Renders the parsed result in styled cards (personal info, skills with pills, experience timeline, education, projects, certifications). Live confidence indicator (🟢🟡🔴).
- **📋 Resumes** — list all parsed resumes with status filter + min-confidence slider. One-click delete.
- **💼 Jobs** — create job descriptions (title, company, description, required skills, required years). Browse existing jobs with full details.
- **🎯 Match** — pairwise match (resume × job) with breakdown of semantic / skills / experience / education / title scores plus matching+missing skills lists. Top-candidates ranking for a job (pgvector ANN under the hood, ranked client-side).

The sidebar shows live backend metrics: total resumes parsed, average confidence, OCR usage rate, failure count. Live health check on the API URL.

---

## Tags

| Tag | Description |
|---|---|
| `latest` | Most recent stable build |
| `1.0` | Pinned semantic version |

**Supported architectures:** `linux/amd64`, `linux/arm64` (Apple Silicon native)

**Image size:** ~250 MB (just Python + Streamlit + requests)

---

## Quick start

This is a **frontend only** — you need the backend image running too. Easiest way: use the full-stack docker-compose file from the backend repo.

### Easiest — full stack with docker-compose

```bash
mkdir ats-parser && cd ats-parser
curl -O https://raw.githubusercontent.com/YOUR_REPO/main/docker-compose.prod.yml
echo "OPENROUTER_API_KEY=sk-or-v1-your_key" > .env
docker-compose -f docker-compose.prod.yml up -d
```

Open http://localhost:8501 — the Streamlit UI.

### Standalone (point at your own backend)

```bash
docker run -d \
  --name ats-frontend \
  -p 8501:8501 \
  -e API_URL=https://your-api-host:8000 \
  YOURUSER/ats-parser-frontend:latest
```

Open http://localhost:8501. The sidebar lets you change the backend URL at runtime if you need to point it elsewhere.

### Local dev (no Docker)

```bash
pip install streamlit==1.35.0 requests==2.32.3
API_URL=http://localhost:8000 streamlit run streamlit_app.py
```

---

## Environment variables

| Variable | Default | Required | Purpose |
|---|---|:---:|---|
| `API_URL` | `http://localhost:8000` |  | URL of the [`YOURUSER/ats-parser`](https://hub.docker.com/r/YOURUSER/ats-parser) backend. Override at runtime via the sidebar. |

---

## Ports

| Port | Purpose |
|---|---|
| `8501` | Streamlit web UI (HTTP) |

---

## Screenshots

(See the source repo's README for screenshots.)

---

## Pairing with the backend

This image is designed to talk to [`YOURUSER/ats-parser`](https://hub.docker.com/r/YOURUSER/ats-parser). Both images live in the same project — see the GitHub repo for a full `docker-compose.prod.yml` that wires everything together:

- This frontend
- The FastAPI backend
- The ARQ worker
- Postgres with pgvector
- Redis

If you're hosting the backend on a remote server (Render, Cloud Run, Fly.io), set `API_URL=https://your-api.example.com` and run this image anywhere.

---

## Resource recommendations

Tiny — Streamlit blocks during a request but holds little memory.

| Workload | RAM | CPU |
|---|---|---|
| Solo demo | 256 MB | 0.5 core |
| Small team | 512 MB | 1 core |
| Many concurrent users | 1 GB+ | 1+ core |

For multi-user use you may want a real Streamlit Cloud or Hugging Face Spaces deployment instead of this image — Streamlit isn't natively multi-tenant.

---

## Source code

- **GitHub:** https://github.com/YOUR_REPO/ats-parser
- **Backend:** https://hub.docker.com/r/YOURUSER/ats-parser

## License

MIT
