# Smart Job Apply Assistant

Automates the repetitive parts of job applications while keeping **human control of the final submit**. Reads job rows from Google Sheets, tailors résumé/cover text using Krutrim LLM, auto-fills application forms via Playwright, and pauses before submission for manual review.

---

## Features

- **Google Sheets integration** for job-queue management
- **Résumé & cover-letter tailoring** via Krutrim LLM (Ola AI)
- **Automated form filling** with Playwright (Greenhouse, Lever, Workday, custom)
- **Human-in-the-loop** — never auto-submits; pauses for manual review
- **Local web dashboard** for monitoring and confirming submissions
- **SQLite audit trail** with logs and screenshots
- **Rate limiting & anti-detection** (randomized delays, real browser profile)
- **Privacy-first** — all data stored locally

---

## Architecture

```
Orchestrator
  ├─► Google Sheets   (fetch job queue)
  ├─► Tailor          (Krutrim LLM résumé/cover customization)
  ├─► Playwright Worker (browser form-fill + screenshot)
  └─► Local DB + API Server (SQLite, Flask dashboard)
```

The **Orchestrator** pulls pending jobs from Google Sheets, sends each job description to the **Tailor** module for LLM-based résumé and cover-letter customization, then hands the tailored content to a **Playwright Worker** that fills out the application form in a real browser. Every action is recorded in an **SQLite database** and exposed through a **Flask API/dashboard** where you review and confirm each submission.

---

## Quick Start

### Prerequisites

| Requirement | Version |
|-------------|---------|
| Python | 3.10+ |
| Google Chrome | Latest stable |
| Google Cloud project | Sheets API enabled |
| Krutrim Cloud API key | [cloud.olakrutrim.com](https://cloud.olakrutrim.com) |

### Installation

```bash
git clone https://github.com/Harihkvent/Smart-Job-Apply-Assistant.git
cd Smart-Job-Apply-Assistant
pip install -r requirements.txt
playwright install chromium
```

### Configuration

1. **Config file** — copy the template and fill in your values:
   ```bash
   cp config.example.yml config.yml
   ```
2. **Environment variables** — add your API keys:
   ```bash
   cp .env.example .env
   ```
3. **Profile** — enter your personal details (name, experience, skills):
   ```bash
   cp profile.example.json profile.json
   ```
4. **Google OAuth** — create OAuth 2.0 credentials in the
   [Google Cloud Console](https://console.cloud.google.com/apis/credentials)
   and add the client ID/secret to `.env`.

### Usage

```bash
# Run the batch orchestrator
python -m src.orchestrator

# Or start the local web server
python -m src.server
```

Then open **<http://127.0.0.1:5000>** to see the dashboard.

---

## Project Structure

```
src/
  config.py              — Configuration loader (YAML + env)
  db.py                  — SQLite database (jobs, applications, logs)
  sheets.py              — Google Sheets connector
  tailor.py              — Résumé/cover tailoring via Krutrim LLM
  playwright_worker.py   — Browser automation (form filling)
  orchestrator.py        — Main job-processing coordinator
  server.py              — Local Flask web API + dashboard
tests/
  test_config.py
  test_db.py
  test_sheets.py
  test_tailor.py
  test_server.py
config.example.yml       — Config template
.env.example             — Environment variables template
profile.example.json     — User profile template
requirements.txt         — Python dependencies
```

---

## API Endpoints

All endpoints (except the dashboard) require a `Authorization: Bearer <token>` header when `server_token` is set.

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/` | Dashboard HTML UI |
| `GET` | `/api/jobs` | List jobs (optional `?status=` filter) |
| `GET` | `/api/jobs/<id>` | Get single job details |
| `POST` | `/api/jobs/<id>/start` | Start processing a job |
| `POST` | `/api/jobs/<id>/confirm-submit` | Confirm and submit the application |
| `GET` | `/api/logs` | List logs (optional `?job_id=` filter) |

---

## Configuration Reference

All keys live in `config.yml`. Secrets should go in `.env` instead.

| Key | Description | Default |
|-----|-------------|---------|
| `google_sheet_id` | Google Spreadsheet ID for job listings | — |
| `sheet_range` | Cell range to read | `Sheet1!A:H` |
| `browser_profile_dir` | Chrome user-data directory | — |
| `resume_base_path` | Path to base résumé PDF | — |
| `llm_provider` | LLM provider name | `krutrim` |
| `llm_endpoint` | LLM API URL | — |
| `llm_model` | Model identifier | `Krutrim-spectre-v2` |
| `max_concurrent_workers` | Parallel browser workers | `2` |
| `random_delay_min_ms` | Minimum random delay (ms) | `200` |
| `random_delay_max_ms` | Maximum random delay (ms) | `1200` |
| `max_daily_applies` | Daily application cap | `40` |
| `db_path` | SQLite database file | `jobs.db` |
| `tailor_temp_dir` | Temp dir for tailored résumés | — |
| `screenshot_dir` | Directory for screenshots | — |
| `log_retention_days` | Days to keep log entries | `90` |
| `server_host` | Flask bind address | `127.0.0.1` |
| `server_port` | Flask bind port | `5000` |
| `server_token` | Bearer token for API auth | — |

**Environment variables** (`.env`):

| Variable | Description |
|----------|-------------|
| `GOOGLE_CLIENT_ID` | Google OAuth 2.0 client ID |
| `GOOGLE_CLIENT_SECRET` | Google OAuth 2.0 client secret |
| `LLM_API_KEY` | Krutrim / LLM provider API key |
| `SENTRY_DSN` | *(optional)* Sentry error-tracking DSN |

---

## Testing

```bash
python -m pytest tests/ -v
```

---

## Privacy & Security

- All data is stored **locally** (SQLite + local files).
- Krutrim LLM API is used for tailoring only — no full résumé is sent unless explicitly configured.
- Google OAuth uses **minimal scopes** (read-only Sheets access).
- The server binds to **localhost only** by default.
- API is protected by a **Bearer token**.
- The assistant **never auto-submits** applications — every submission requires human confirmation.

---

## Roadmap

| Milestone | Status | Description |
|-----------|--------|-------------|
| M1 | ✅ Done | Core infrastructure (Sheets, DB, CLI, Orchestrator) |
| M2 | ✅ Done | Tailor module (Krutrim LLM integration) |
| M3 | ✅ Done | Playwright Worker (form filler + screenshots) |
| M4 | ✅ Done | Web UI & API |
| M5 | 🔧 Next | Hardening (rate limiter, Sentry, encryption, CI) |
| M6 | 📋 Planned | Site-specific adapters (Greenhouse / Lever / Workday) |

---

## License

This project is licensed under the [MIT License](LICENSE).