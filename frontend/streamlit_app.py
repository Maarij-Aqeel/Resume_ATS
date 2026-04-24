"""Streamlit UI for the ATS Resume Parser API."""
from __future__ import annotations

import os
import time
from typing import Any

import requests
import streamlit as st

# ----- Config -----
DEFAULT_API = os.getenv("API_URL", "http://localhost:8000")
REQUEST_TIMEOUT = 180  # seconds — Gemini parse can take 30-90s

st.set_page_config(page_title="ATS Resume Parser", page_icon="📄", layout="wide")


# ----- Helpers -----

def api() -> str:
    return st.session_state.get("api_url", DEFAULT_API).rstrip("/")


def get(path: str, **kwargs) -> requests.Response:
    return requests.get(f"{api()}{path}", timeout=REQUEST_TIMEOUT, **kwargs)


def post(path: str, **kwargs) -> requests.Response:
    return requests.post(f"{api()}{path}", timeout=REQUEST_TIMEOUT, **kwargs)


def delete(path: str, **kwargs) -> requests.Response:
    return requests.delete(f"{api()}{path}", timeout=REQUEST_TIMEOUT, **kwargs)


def health_check(url: str) -> tuple[bool, str]:
    try:
        r = requests.get(f"{url.rstrip('/')}/health", timeout=5)
        if r.status_code == 200:
            return True, r.json().get("status", "ok")
        return False, f"HTTP {r.status_code}"
    except requests.exceptions.RequestException as e:
        return False, str(e)


def fmt_score(v: float | None) -> str:
    return "—" if v is None else f"{v:.2f}"


# ----- Sidebar -----

with st.sidebar:
    st.title("📄 ATS Resume Parser")
    st.caption("LLM-first resume parser powered by Gemini")

    st.subheader("Backend")
    st.text_input("API URL", key="api_url", value=DEFAULT_API, help="FastAPI backend URL")

    ok, msg = health_check(api())
    if ok:
        st.success(f"Backend reachable")
    else:
        st.error(f"Backend unreachable: {msg}")

    st.divider()
    st.subheader("Metrics")
    try:
        m = get("/api/v1/metrics/accuracy").json()
        st.metric("Resumes parsed", m.get("total", 0))
        avg = m.get("avg_confidence")
        st.metric("Avg confidence", fmt_score(float(avg)) if avg is not None else "—")
        st.metric("Low confidence", m.get("low_confidence_count", 0))
        st.metric("Failed", m.get("failed_count", 0))
        st.metric("OCR rate", f"{m.get('ocr_usage_rate', 0) * 100:.1f}%")
    except Exception:
        st.caption("(no metrics — backend down?)")


# ----- Tabs -----

tabs = st.tabs(["📤 Upload", "📋 Resumes", "💼 Jobs", "🎯 Match"])


# -------------------- TAB 1: UPLOAD --------------------

with tabs[0]:
    st.header("Upload a resume")
    st.caption("Parses PDF / DOCX / DOC / TXT — extraction → Gemini → validation → embedding.")

    uploaded = st.file_uploader(
        "Drop your resume here",
        type=["pdf", "docx", "doc", "txt", "rtf"],
        help="Max 10 MB",
    )

    col1, col2 = st.columns([1, 3])
    async_mode = col1.toggle("Async (queue it)", value=False, help="If on, uses worker; if off, waits for result inline.")
    parse_btn = col2.button("Parse", type="primary", disabled=uploaded is None)

    if parse_btn and uploaded:
        endpoint = "/api/v1/resumes/upload" if async_mode else "/api/v1/resumes/upload/sync"
        files = {"file": (uploaded.name, uploaded.getvalue(), uploaded.type or "application/octet-stream")}

        with st.spinner("Uploading + parsing (can take 30–90s for long resumes)..."):
            t0 = time.time()
            try:
                r = post(endpoint, files=files)
                elapsed = time.time() - t0
            except requests.exceptions.RequestException as e:
                st.error(f"Request failed: {e}")
                st.stop()

        if r.status_code not in (200, 202):
            st.error(f"HTTP {r.status_code}")
            st.json(r.json() if r.headers.get("content-type", "").startswith("application/json") else {"body": r.text})
            st.stop()

        data = r.json()

        if async_mode:
            rid = data["resume_id"]
            st.success(f"Queued as `{rid}`. Switch to the Resumes tab and refresh to see the result.")
            st.session_state["last_resume_id"] = rid
        else:
            conf = data.get("confidence_score") or 0
            status = data.get("status", "—")
            color = "🟢" if conf >= 0.70 else "🟡" if conf >= 0.40 else "🔴"
            st.success(f"Parsed in {elapsed:.1f}s — status: **{status}** — confidence: {color} **{conf * 100:.1f}%**")
            st.session_state["last_resume_id"] = data.get("resume_id")
            st.session_state["last_parsed"] = data

    # Show the most recent result
    if st.session_state.get("last_parsed"):
        data = st.session_state["last_parsed"]
        parsed = data.get("parsed_data") or {}
        st.divider()

        # Header row
        pi = parsed.get("personal_info") or {}
        name = pi.get("full_name") or "—"
        email = pi.get("email") or "—"
        phone = pi.get("phone") or "—"
        loc = pi.get("location") or {}
        loc_str = ", ".join(x for x in (loc.get("city"), loc.get("state"), loc.get("country")) if x) or "—"

        st.subheader(name)
        c1, c2, c3, c4 = st.columns(4)
        c1.markdown(f"**Email**  \n{email}")
        c2.markdown(f"**Phone**  \n{phone}")
        c3.markdown(f"**Location**  \n{loc_str}")
        c4.markdown(f"**Years Exp.**  \n{parsed.get('parser_metadata', {}).get('total_years_experience') or '—'}")

        # Links
        links = []
        for k, v in (("LinkedIn", pi.get("linkedin_url")), ("GitHub", pi.get("github_url")), ("Portfolio", pi.get("portfolio_url"))):
            if v:
                links.append(f"[{k}]({v})")
        if links:
            st.markdown(" · ".join(links))

        # Summary
        if parsed.get("professional_summary"):
            with st.expander("Professional Summary", expanded=True):
                st.write(parsed["professional_summary"])

        # Skills
        skills = parsed.get("skills") or {}
        with st.expander("Skills", expanded=True):
            if skills.get("technical"):
                st.markdown("**Technical:** " + " · ".join(f"`{s}`" for s in skills["technical"]))
            if skills.get("tools"):
                st.markdown("**Tools:** " + " · ".join(f"`{s}`" for s in skills["tools"]))
            if skills.get("soft"):
                st.markdown("**Soft:** " + ", ".join(skills["soft"]))
            if skills.get("languages"):
                st.markdown("**Languages:** " + ", ".join(skills["languages"]))

        # Experience
        exp_list = parsed.get("experience") or []
        with st.expander(f"Experience ({len(exp_list)})", expanded=True):
            for exp in exp_list:
                title = exp.get("job_title") or "—"
                company = exp.get("company_name") or "—"
                start = exp.get("start_date") or "?"
                end = "Present" if exp.get("is_current") else (exp.get("end_date") or "?")
                st.markdown(f"**{title}** — {company}  \n*{start} → {end}*")
                if exp.get("description"):
                    st.caption(exp["description"][:500])
                if exp.get("achievements"):
                    for a in exp["achievements"][:5]:
                        st.markdown(f"- {a}")
                st.markdown("")

        # Education
        edu_list = parsed.get("education") or []
        if edu_list:
            with st.expander(f"Education ({len(edu_list)})"):
                for edu in edu_list:
                    deg = edu.get("degree_type") or ""
                    field = edu.get("field_of_study") or ""
                    inst = edu.get("institution_name") or "—"
                    grad = edu.get("graduation_date") or "?"
                    st.markdown(f"**{deg} in {field}** — {inst} ({grad})")
                    if edu.get("gpa"):
                        st.caption(f"GPA: {edu['gpa']}/{edu.get('gpa_scale') or '?'}")

        # Projects, certs, awards
        for key, label in (("projects", "Projects"), ("certifications", "Certifications"),
                          ("awards", "Awards"), ("publications", "Publications"),
                          ("volunteer_experience", "Volunteer")):
            items = parsed.get(key) or []
            if items:
                with st.expander(f"{label} ({len(items)})"):
                    for it in items:
                        st.json(it)

        with st.expander("Raw JSON"):
            st.json(data)


# -------------------- TAB 2: RESUMES LIST --------------------

with tabs[1]:
    st.header("Parsed resumes")

    c1, c2, c3 = st.columns([2, 2, 1])
    status_filter = c1.selectbox("Status", ["any", "pending", "processing", "completed", "review_needed", "failed"])
    min_conf = c2.slider("Min confidence", 0.0, 1.0, 0.0, step=0.05)
    limit = c3.number_input("Limit", 1, 500, 50)

    params = {"limit": limit, "offset": 0}
    if status_filter != "any":
        params["status"] = status_filter
    if min_conf > 0:
        params["min_confidence"] = min_conf

    if st.button("Refresh", key="refresh_list"):
        pass  # triggers rerun

    try:
        r = get("/api/v1/resumes/", params=params)
        resumes = r.json().get("resumes", []) if r.status_code == 200 else []
    except Exception as e:
        st.error(str(e))
        resumes = []

    if not resumes:
        st.info("No resumes yet. Upload one in the Upload tab.")
    else:
        st.caption(f"{len(resumes)} result(s)")
        for res in resumes:
            c1, c2, c3, c4, c5 = st.columns([3, 2, 2, 2, 1])
            c1.markdown(f"**{res['original_filename']}**  \n`{res['resume_id'][:8]}…`")
            c2.write(res["status"])
            conf = res.get("confidence_score")
            conf_str = f"{float(conf) * 100:.1f}%" if conf is not None else "—"
            c3.write(conf_str)
            c4.caption(res["created_at"].split("T")[0])
            if c5.button("🗑", key=f"del_{res['resume_id']}", help="Delete"):
                try:
                    delete(f"/api/v1/resumes/{res['resume_id']}")
                    st.rerun()
                except Exception as e:
                    st.error(str(e))


# -------------------- TAB 3: JOBS --------------------

with tabs[2]:
    st.header("Job descriptions")

    with st.form("create_job"):
        st.subheader("Create a new job")
        c1, c2 = st.columns(2)
        title = c1.text_input("Title*", placeholder="Senior Python Engineer")
        company = c2.text_input("Company", placeholder="Acme Corp")
        desc = st.text_area(
            "Description*",
            height=200,
            placeholder="We need a senior engineer with 5+ years of Python, FastAPI, PostgreSQL, AWS...",
        )
        c3, c4 = st.columns(2)
        skills_text = c3.text_input("Required skills (comma-separated)", placeholder="Python, FastAPI, PostgreSQL, AWS")
        years = c4.number_input("Required years", 0, 30, 0)

        if st.form_submit_button("Create job", type="primary"):
            if not title or not desc:
                st.error("Title and Description are required.")
            else:
                skills = [s.strip() for s in skills_text.split(",") if s.strip()]
                try:
                    r = post("/api/v1/jobs/", json={
                        "title": title,
                        "company": company or None,
                        "description": desc,
                        "required_skills": skills or None,
                        "required_years": int(years) or None,
                    })
                    if r.status_code == 200:
                        st.success(f"Created job `{r.json()['job_id']}`")
                    else:
                        st.error(r.text)
                except Exception as e:
                    st.error(str(e))

    st.divider()
    st.subheader("Existing jobs")
    try:
        jobs = get("/api/v1/jobs/").json().get("jobs", [])
    except Exception as e:
        st.error(str(e))
        jobs = []

    if not jobs:
        st.info("No jobs yet.")
    else:
        for j in jobs:
            with st.expander(f"{j['title']} — {j.get('company') or '(no company)'}"):
                try:
                    full = get(f"/api/v1/jobs/{j['job_id']}").json()
                    st.caption(f"Job ID: `{full['job_id']}`")
                    st.write(full.get("description", ""))
                    if full.get("required_skills"):
                        st.markdown("**Required skills:** " + " · ".join(f"`{s}`" for s in full["required_skills"]))
                    if full.get("required_years"):
                        st.caption(f"Required years: {full['required_years']}")
                except Exception as e:
                    st.error(str(e))


# -------------------- TAB 4: MATCH --------------------

with tabs[3]:
    st.header("Match resumes ↔ jobs")

    # load lists
    try:
        resumes = get("/api/v1/resumes/", params={"limit": 200}).json().get("resumes", [])
    except Exception:
        resumes = []
    try:
        jobs = get("/api/v1/jobs/", params={"limit": 200}).json().get("jobs", [])
    except Exception:
        jobs = []

    if not resumes or not jobs:
        st.info("Need at least 1 resume and 1 job. Go to the Upload + Jobs tabs first.")
    else:
        resume_opts = {
            f"{r['original_filename']}  ({r['resume_id'][:8]})": r["resume_id"]
            for r in resumes
            if r["status"] in ("completed", "review_needed")
        }
        job_opts = {f"{j['title']}  ({j['job_id'][:8]})": j["job_id"] for j in jobs}

        st.subheader("Score one resume against one job")
        c1, c2, c3 = st.columns([3, 3, 1])
        r_label = c1.selectbox("Resume", list(resume_opts.keys()) if resume_opts else ["— none parsed —"])
        j_label = c2.selectbox("Job", list(job_opts.keys()))
        go = c3.button("Compute", type="primary", disabled=not resume_opts)

        if go and resume_opts:
            rid = resume_opts[r_label]
            jid = job_opts[j_label]
            with st.spinner("Computing match..."):
                r = post(f"/api/v1/match/resume/{rid}/job/{jid}")
            if r.status_code == 200:
                d = r.json()
                c1, c2, c3, c4, c5, c6 = st.columns(6)
                c1.metric("Total", f"{d['total_score']:.1f}%")
                b = d["breakdown"]
                c2.metric("Semantic", f"{b['semantic']:.2f}")
                c3.metric("Skills", f"{b['skills']:.2f}")
                c4.metric("Experience", f"{b['experience']:.2f}")
                c5.metric("Education", f"{b['education']:.2f}")
                c6.metric("Title", f"{b['title']:.2f}")

                col_a, col_b = st.columns(2)
                with col_a:
                    st.subheader("✓ Matching skills")
                    if d["matching_skills"]:
                        st.markdown(" · ".join(f"`{s}`" for s in d["matching_skills"]))
                    else:
                        st.caption("(none)")
                with col_b:
                    st.subheader("✗ Missing skills")
                    if d["missing_skills"]:
                        st.markdown(" · ".join(f"`{s}`" for s in d["missing_skills"]))
                    else:
                        st.caption("(none — full coverage!)")
            else:
                st.error(r.text)

        st.divider()
        st.subheader("Top candidates for a job")
        c1, c2, c3 = st.columns([3, 1, 1])
        top_job_label = c1.selectbox("Job", list(job_opts.keys()), key="top_job_select")
        top_n = c2.slider("Limit", 1, 50, 10)
        min_s = c3.slider("Min score", 0.0, 1.0, 0.0, step=0.05)
        if st.button("Rank candidates", type="primary"):
            jid = job_opts[top_job_label]
            with st.spinner("Ranking..."):
                r = post(
                    f"/api/v1/match/job/{jid}/top-candidates",
                    json={"limit": top_n, "min_score": float(min_s)},
                )
            if r.status_code == 200:
                cands = r.json().get("candidates", [])
                if not cands:
                    st.info("No candidates matched the minimum score.")
                for i, c in enumerate(cands, 1):
                    c1, c2, c3 = st.columns([1, 4, 3])
                    c1.markdown(f"### {i}.")
                    c2.markdown(f"**{c['original_filename']}**")
                    c2.caption(f"`{c['resume_id'][:8]}…`")
                    c3.metric("Score", f"{c['total_score']:.1f}%")
                    if c.get("matching_skills"):
                        st.caption("✓ " + ", ".join(c["matching_skills"][:8]))
                    if c.get("missing_skills"):
                        st.caption("✗ " + ", ".join(c["missing_skills"][:8]))
                    st.divider()
            else:
                st.error(r.text)
