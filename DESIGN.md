# Smart Job Apply Assistant — Design Document

This document covers the **high-level design (HLD)**, **low-level design (LLD)**, **features**, **user flow**, **data flow**, requirements, and operational notes for the Smart Job Apply Assistant.

---

## 1. Goal

Automate the repetitive parts of job applications so you can safely submit many applications fast. The system:

1. Reads job rows from your **Google Sheet**.
2. Tailors résumé / cover text per JD using **Krutrim LLM**.
3. Opens each apply link in your **real browser** (Playwright).
4. **Auto-fills** all form fields and uploads the résumé.
5. **Pauses** at the final step and marks the row so **you click Submit manually**.

This human-in-the-loop approach keeps final-submit control with the user (avoids bot bans and ATS policy violations) while speeding the rest of the flow to roughly **60–90 seconds per application**.

---

## 2. Features

| Feature | Description |
|---------|-------------|
| **Google Sheets queue** | Manage your job queue directly from a familiar spreadsheet. |
| **LLM-powered tailoring** | Krutrim LLM generates a custom cover blurb + résumé bullets for every job. |
| **Automated form filling** | Playwright opens the real Chrome profile and fills detected form fields. |
| **Platform detection** | Heuristics classify Greenhouse, Lever, Workday, or custom forms. |
| **Résumé upload** | Automatically uploads the tailored résumé via `<input type="file">`. |
| **Human-in-the-loop submit** | The browser tab is left open — the user clicks Submit. |
| **Local web dashboard** | Flask-based UI at `http://127.0.0.1:5000` shows the queue, statuses, and confirm-submit buttons. |
| **SQLite audit trail** | Every action is logged with timestamps and optional screenshots. |
| **Rate limiting** | Configurable daily cap (`max_daily_applies`), randomised delays between actions and between jobs. |
| **Anti-detection** | Uses a real Chrome user-data directory, randomised timings, and standard user-agent. |
| **Privacy-first** | All data stored locally. LLM receives only the JD + profile summary. |
| **Retry support** | Failed jobs can be retried from the orchestrator or the dashboard. |

---

## 3. High-Level Architecture

```
┌────────────────────────────────────────────────────┐
│                   User (Browser)                   │
│  - Manages Google Sheet                            │
│  - Reviews pre-filled tabs                         │
│  - Clicks Submit manually                          │
│  - Uses local dashboard for status / confirm       │
└──────────┬──────────────────────┬──────────────────┘
           │                      │
           ▼                      ▼
┌─────────────────┐    ┌──────────────────────┐
│  Google Sheet    │    │  Local Flask Server   │
│  (Job Queue)     │◄──►│  (Dashboard + API)    │
└────────┬────────┘    └──────────┬───────────┘
         │                        │
         ▼                        ▼
┌──────────────────────────────────────────────┐
│               Orchestrator                   │
│  - Polls pending rows from Google Sheet      │
│  - Calls Tailor module per job               │
│  - Dispatches Playwright Worker              │
│  - Updates statuses in DB + Sheet            │
│  - Manages retries with backoff              │
└──────┬───────────┬───────────┬───────────────┘
       │           │           │
       ▼           ▼           ▼
┌───────────┐ ┌──────────┐ ┌──────────────┐
│ Tailor    │ │ Playwright│ │  SQLite DB   │
│ Module    │ │ Worker    │ │  (Audit Log) │
│ (Krutrim  │ │ (Browser  │ │              │
│  LLM)     │ │  Filler)  │ │              │
└───────────┘ └──────────┘ └──────────────┘
```

### Component Responsibilities

| Component | File | Responsibility |
|-----------|------|----------------|
| **Config** | `src/config.py` | Load `config.yml` + `.env`; merge defaults + env overrides. |
| **DB** | `src/db.py` | SQLite CRUD for `jobs`, `applications`, `logs` tables. |
| **Sheets** | `src/sheets.py` | Read/write Google Sheets via OAuth 2.0. |
| **Tailor** | `src/tailor.py` | Call Krutrim LLM to produce cover text, résumé bullets, and a tailored résumé file. |
| **Playwright Worker** | `src/playwright_worker.py` | Open browser, detect platform, parse form, fill fields, upload résumé, take screenshot, pause. |
| **Orchestrator** | `src/orchestrator.py` | Coordinate the end-to-end pipeline for batch or single-job processing. |
| **Server** | `src/server.py` | Flask REST API + HTML dashboard for queue monitoring and manual confirm-submit. |

---

## 4. User Flow

```
1. User adds job rows to Google Sheet (Company, Role, Apply Link, …)
        │
        ▼
2. User runs `python -m src.orchestrator`  (or starts via dashboard)
        │
        ▼
3. Orchestrator reads "pending" rows from Google Sheet
        │
        ▼
4. For each job:
   a.  Orchestrator calls Tailor → LLM returns cover_text + résumé_bullets
   b.  Tailor generates a tailored résumé file in tailor_temp_dir
   c.  Orchestrator calls Playwright Worker
       i.   Worker opens apply link in real Chrome profile
       ii.  Worker detects ATS platform (Greenhouse / Lever / Workday / custom)
       iii. Worker parses visible form fields (label→input mapping)
       iv.  Worker fills fields with profile data (name, email, phone, …)
       v.   Worker uploads tailored résumé via file input
       vi.  Worker fills cover-letter textarea if found
       vii. Worker takes full-page screenshot
       viii. Worker leaves browser tab open
   d.  Orchestrator marks row → "ready_for_submit"
        │
        ▼
5. User reviews the pre-filled tab in their browser
        │
        ▼
6. User clicks Submit manually
        │
        ▼
7. User clicks "Confirm Submit" in the dashboard (or API call)
        │
        ▼
8. Orchestrator marks row → "submitted"
```

---

## 5. Data Flow

```
Google Sheet                Orchestrator              Tailor Module
───────────                 ────────────              ────────────
  pending rows ──────────►  read & normalise
                            job metadata    ────────► JD + profile
                                                         │
                                              Krutrim LLM API call
                                                         │
                                              cover_text + bullets ◄──
                                              tailored résumé file  ◄──
                            ◄─── resume_path + cover_text
                                      │
                                      ▼
                            Playwright Worker
                            ─────────────────
                            open apply_link
                            detect_platform()
                            parse_form_fields()
                            map_fields_to_profile()
                            fill_form()
                            upload_resume()
                            fill_cover_text()
                            take_screenshot()
                                      │
                                      ▼
                            return result + screenshot
                                      │
                            ◄─────────┘
                            update SQLite DB
                            update Google Sheet status
```

### Status Transitions

```
pending ──► in-progress ──► ready_for_submit ──► submitted
                │
                └──► failed  (retryable)
```

---

## 6. Data Models

### 6.1 User Profile (`profile.json`)

```json
{
  "name": "Hari Kiran Ventrapragada",
  "email": "you@example.com",
  "phone": "+91xxxxxxxxxx",
  "location": "Vizianagaram, AP, India",
  "graduation_date": "2026-04-30",
  "degree": "B.Tech Information Technology",
  "cgpa": "7.54",
  "experience": [
    {
      "company": "OmniqAI",
      "title": "AI DevOps Intern",
      "from": "2025-05",
      "to": "2025-07",
      "bullets": ["...", "..."]
    }
  ],
  "skills": ["python", "java", "c++", "sql", "docker", "git", "jira"],
  "linkedin": "https://linkedin.com/in/harikiran",
  "resume_base_path": "/path/to/base_resume.pdf"
}
```

### 6.2 Job Row (Google Sheet → internal dict)

```json
{
  "row_index": 2,
  "company": "Razorpay",
  "role": "Junior Software Engineer",
  "apply_link": "https://razorpay.com/careers/123",
  "location": "Bengaluru",
  "platform": "greenhouse",
  "status": "pending",
  "notes": "",
  "last_tried_at": ""
}
```

### 6.3 Tailor Result

```json
{
  "cover_text": "150-word persuasive paragraph…",
  "resume_bullets": ["bullet1", "bullet2", "bullet3"],
  "skills_to_highlight": ["python", "docker"],
  "resume_pdf_path": "/tmp/tailor_resumes/resume_Razorpay_1700000000.txt"
}
```

---

## 7. Database Schema (SQLite)

```sql
CREATE TABLE jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company TEXT NOT NULL,
    role TEXT NOT NULL,
    apply_link TEXT NOT NULL,
    platform TEXT DEFAULT 'custom',
    status TEXT DEFAULT 'pending',
    row_index INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL,
    resume_path TEXT,
    cover_text TEXT,
    tailored_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    user_submitted BOOLEAN DEFAULT 0,
    FOREIGN KEY (job_id) REFERENCES jobs(id)
);

CREATE TABLE logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER,
    ts DATETIME DEFAULT CURRENT_TIMESTAMP,
    level TEXT DEFAULT 'INFO',
    message TEXT,
    screenshot_path TEXT,
    FOREIGN KEY (job_id) REFERENCES jobs(id)
);
```

---

## 8. API Endpoints (Local Flask Server)

All `/api/` endpoints require `Authorization: Bearer <token>` when `server_token` is configured.

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Dashboard HTML UI |
| `GET` | `/api/jobs` | List all jobs (optional `?status=` filter) |
| `GET` | `/api/jobs/<id>` | Get single job details |
| `POST` | `/api/jobs/<id>/start` | Start processing a specific job |
| `POST` | `/api/jobs/<id>/confirm-submit` | Confirm manual submission |
| `GET` | `/api/logs` | List logs (optional `?job_id=` filter) |

---

## 9. Playwright Form-Filling Strategy

### 9.1 Platform Detection Heuristics

| Signal | Platform |
|--------|----------|
| URL contains `greenhouse` or page HTML contains `application-form` | Greenhouse |
| URL contains `lever.co` or page HTML contains `data-apply` | Lever |
| URL or page HTML contains `workday` | Workday |
| None of the above | Custom (generic) |

### 9.2 Selector Resolution Order

1. Find `input[id]` matching a normalised label (lowercase, strip spaces).
2. Find `<label>` whose text matches the expected field → use `label.for` to get the input.
3. Search for `input` whose `placeholder` contains the target keyword.
4. Use DOM proximity: find the nearest input element following a text node.
5. Fallback: iterate `document.querySelectorAll('input')` and fill common fields in order.

### 9.3 Field Mapping Rules

The worker maps profile fields to form fields via keyword matching on label / name / placeholder:

| Keywords | Profile field |
|----------|--------------|
| `first name` | First word of `name` |
| `last name`, `surname` | Last word of `name` |
| `name`, `full name` | `name` |
| `email`, `e-mail` | `email` |
| `phone`, `mobile`, `telephone` | `phone` |
| `linkedin` | `linkedin` |
| `location`, `city`, `address` | `location` |
| `graduation`, `grad date` | `graduation_date` |
| `university`, `school`, `college` | `degree` |
| `gpa`, `cgpa` | `cgpa` |

### 9.4 File Upload

- For `<input type="file">`: uses `input.set_input_files(resume_path)`.
- Custom drag-drop: fallback to JS DOM mutation if standard input is unavailable.

### 9.5 Anti-Detection Tactics

- Uses the user's **real Chrome profile** (`user_data_dir`) so cookies, fonts, and extensions match a human session.
- Randomised delays between actions (`200–1200 ms`, configurable).
- Standard Chrome user-agent (no headless UA).
- Daily application cap (`max_daily_applies`, default 40).
- Random sleep windows (10–30 seconds) between jobs.

---

## 10. LLM Tailoring (Krutrim LLM)

### Prompt Template

```
System: You are an assistant that tailors a candidate's resume bullets and
a short cover blurb for a job application. Be concise and prefer measurable
results. Do not fabricate facts. Output only valid JSON.

User:
Job Description:
<<JD_TEXT>>

Candidate Profile:
<<USER_PROFILE_JSON>>

Return a JSON object with exactly these keys:
{
  "cover_text": "150-word persuasive paragraph focusing on fit and achievements",
  "resume_bullets": ["bullet1", "bullet2", "bullet3"],
  "skills_to_highlight": ["python", "docker"]
}
```

### Parameters

| Parameter | Value |
|-----------|-------|
| `temperature` | 0.2 |
| `max_tokens` | 1024 |
| Provider | Krutrim (Ola AI) — `https://cloud.olakrutrim.com/v1` |
| Model | `Krutrim-spectre-v2` |

### Safety Guardrails

- Do **not** fabricate facts — if a requested metric doesn't exist in the profile, omit it.
- Keep bullets factual and derived from the base résumé.
- LLM receives only the JD + profile summary, **not** the full résumé PDF.

---

## 11. Configuration

### `config.yml`

```yaml
google_sheet_id: "SPREADSHEET_ID"
sheet_range: "Sheet1!A:H"
browser_profile_dir: "/home/user/.config/google-chrome/Default"
resume_base_path: "/home/user/resume_base.pdf"
tailor_temp_dir: "/tmp/tailor_resumes"
llm_provider: "krutrim"
llm_endpoint: "https://cloud.olakrutrim.com/v1"
llm_model: "Krutrim-spectre-v2"
max_concurrent_workers: 2
random_delay_min_ms: 200
random_delay_max_ms: 1200
max_daily_applies: 40
db_path: "jobs.db"
screenshot_dir: "/tmp/screenshots"
log_retention_days: 90
server_host: "127.0.0.1"
server_port: 5000
server_token: "change-me-to-a-secure-token"
```

### Environment Variables (`.env`)

| Variable | Description |
|----------|-------------|
| `GOOGLE_CLIENT_ID` | Google OAuth 2.0 client ID |
| `GOOGLE_CLIENT_SECRET` | Google OAuth 2.0 client secret |
| `LLM_API_KEY` | Krutrim / LLM provider API key |
| `SENTRY_DSN` | *(optional)* Sentry error-tracking DSN |

---

## 12. Google Sheets Column Mapping

| Column | Field | Description |
|--------|-------|-------------|
| A | Company | Company name |
| B | Role | Target job title |
| C | Apply Link | URL to the application page |
| D | Location | Job location |
| E | Platform | ATS platform (greenhouse / lever / workday / custom) |
| F | Status | Current status (pending → in-progress → ready_for_submit → submitted) |
| G | Notes | Error messages or remarks |
| H | LastTriedAt | ISO timestamp of last processing attempt |

---

## 13. Sequence Diagram

```
User          Google Sheet     Orchestrator     Tailor       Playwright      SQLite
 │                 │                │              │              │             │
 │ add job rows    │                │              │              │             │
 │────────────────►│                │              │              │             │
 │                 │                │              │              │             │
 │     run batch   │                │              │              │             │
 │─────────────────────────────────►│              │              │             │
 │                 │  read pending  │              │              │             │
 │                 │◄───────────────│              │              │             │
 │                 │  rows          │              │              │             │
 │                 │───────────────►│              │              │             │
 │                 │                │              │              │             │
 │                 │                │ tailor_resume │              │             │
 │                 │                │─────────────►│              │             │
 │                 │                │              │ call Krutrim │             │
 │                 │                │              │ LLM API      │             │
 │                 │                │  result      │              │             │
 │                 │                │◄─────────────│              │             │
 │                 │                │              │              │             │
 │                 │                │ prepare_application          │             │
 │                 │                │─────────────────────────────►│             │
 │                 │                │              │ open, fill,  │             │
 │                 │                │              │ upload,      │             │
 │                 │                │              │ screenshot   │             │
 │                 │                │  result      │              │             │
 │                 │                │◄─────────────────────────────│             │
 │                 │                │              │              │             │
 │                 │                │ update status │              │             │
 │                 │                │──────────────────────────────────────────►│
 │                 │ update sheet   │              │              │             │
 │                 │◄───────────────│              │              │             │
 │                 │                │              │              │             │
 │ review tab      │                │              │              │             │
 │ click Submit    │                │              │              │             │
 │                 │                │              │              │             │
 │ confirm-submit  │                │              │              │             │
 │─────────────────────────────────►│              │              │             │
 │                 │                │──────────────────────────────────────────►│
 │                 │                │ status=submitted             │             │
```

---

## 14. Requirements

### Functional Requirements

| ID | Requirement |
|----|-------------|
| FR-1 | Read job rows from Google Sheet and map columns to internal fields. |
| FR-2 | Detect platform (Greenhouse / Lever / Workday / custom) per job link. |
| FR-3 | Tailor résumé bullets and a cover blurb per job using Krutrim LLM. |
| FR-4 | Generate a versioned résumé file for each application. |
| FR-5 | Open apply link in real Chrome session and pre-fill all detectable fields + upload résumé. |
| FR-6 | Pause at final submit; require manual user confirmation. |
| FR-7 | Update Google Sheet with status transitions: `pending → in-progress → ready_for_submit → submitted / failed`. |
| FR-8 | Store audit logs and screenshots for each step. |
| FR-9 | Allow user to re-run tailoring or re-attempt for failed jobs. |
| FR-10 | Respect rate limits / daily maximum applies (configurable). |

### Non-Functional Requirements

| ID | Requirement |
|----|-------------|
| NFR-1 | System must run locally (no remote cloud mandatory) to protect PII. |
| NFR-2 | Résumé tailoring results are deterministic for the same prompt + data (temperature 0.2). |
| NFR-3 | Logs retained for 90 days (configurable via `log_retention_days`). |
| NFR-4 | Dashboard shows job queue and current progress. |
| NFR-5 | PII is stored locally only; résumé is never uploaded to third-party servers beyond the LLM. |
| NFR-6 | System avoids bot-detection patterns: randomised delays, real user profile browser. |

---

## 15. Acceptance Criteria

1. Given 10 pending jobs in Google Sheet, the system should prepare (tailor + pre-fill) at least 8 job pages without full failures.
2. For a prepared job, the browser tab must show filled fields and uploaded résumé; the sheet must be marked `ready_for_submit`.
3. Tailoring JSON must include at least 2 job-specific résumé bullets and a 75–150 word `cover_text`.
4. The system must **not** submit any application automatically without user confirmation.

---

## 16. Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| ATS blocks IP / flags account | Use real browser profile, throttle, do not auto-submit, randomise intervals. |
| LLM fabricates metrics | Only use base résumé facts; tailor module uses safe mode (no invented numbers). |
| Forms change unpredictably | Maintain site adapters and a fallback generic filler. |
| CAPTCHA or MFA on application page | Mark row as `requires_manual` and notify user. |
| Google OAuth token expiry | Auto-refresh via `google-auth` library; store token securely with `0600` permissions. |

---

## 17. Runbook (Failure Handling)

| Symptom | Action |
|---------|--------|
| `file upload failed` | Check file path and permissions; re-run apply for that job. |
| `captcha detected` | Mark row as `requires_manual` and notify user to complete manually. |
| Site layout changed | Save screenshot and mark as `layout_change`; developer must add / update site adapter. |
| LLM returns empty result | Retry with fallback defaults (empty cover text, base résumé). |
| Google Sheets rate limit | Wait and retry with exponential backoff (built into orchestrator). |

---

## 18. Privacy & Legal

- **Never fully automate final submit** — this is the single safest rule to prevent bans and protect long-term account health.
- Do not send the full résumé to third-party LLMs without prior consent. Use local LLM (Ollama) if privacy is critical.
- Google OAuth scope is minimal: `https://www.googleapis.com/auth/spreadsheets`.
- All data (DB, résumés, screenshots) is stored **locally only**.
- Respect each company's terms of service.
- Avoid mass repeated submissions to the same company within short windows.
- Redact phone numbers if required by policy.

---

## 19. Roadmap

| Milestone | Status | Description |
|-----------|--------|-------------|
| M1 | ✅ Done | Core infrastructure — Google Sheets connector, SQLite DB, CLI, Orchestrator skeleton |
| M2 | ✅ Done | Tailor module — Krutrim LLM integration, résumé generation |
| M3 | ✅ Done | Playwright Worker — generic form filler, platform detection, upload + screenshot + pause |
| M4 | ✅ Done | Web UI & API — Flask dashboard, confirm-submit, log viewer |
| M5 | 🔧 Next | Hardening — rate limiter, Sentry integration, encryption at rest, CI pipeline |
| M6 | 📋 Planned | Site-specific adapters — improved reliability for Greenhouse, Lever, Workday |

---

## 20. Project Structure

```
Smart-Job-Apply-Assistant/
├── src/
│   ├── __init__.py
│   ├── config.py              — Configuration loader (YAML + env)
│   ├── db.py                  — SQLite database (jobs, applications, logs)
│   ├── sheets.py              — Google Sheets connector (OAuth 2.0)
│   ├── tailor.py              — Résumé/cover tailoring via Krutrim LLM
│   ├── playwright_worker.py   — Browser automation (form filling)
│   ├── orchestrator.py        — Main job-processing coordinator
│   └── server.py              — Local Flask web API + dashboard
├── tests/
│   ├── __init__.py
│   ├── test_config.py
│   ├── test_db.py
│   ├── test_sheets.py
│   ├── test_tailor.py
│   └── test_server.py
├── config.example.yml         — Configuration template
├── .env.example               — Environment variables template
├── profile.example.json       — User profile template
├── requirements.txt           — Python dependencies
├── DESIGN.md                  — This design document
└── README.md                  — Quick-start guide
```
