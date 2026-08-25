import sqlite3
from datetime import datetime, timezone

DEFAULT_DB_PATH = "jobs.db"


def init_db(db_path=DEFAULT_DB_PATH):
    """Create tables if they don't exist, return the db_path."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS jobs (
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

        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL,
            resume_path TEXT,
            cover_text TEXT,
            tailored_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            user_submitted BOOLEAN DEFAULT 0,
            FOREIGN KEY (job_id) REFERENCES jobs(id)
        );

        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER,
            ts DATETIME DEFAULT CURRENT_TIMESTAMP,
            level TEXT DEFAULT 'INFO',
            message TEXT,
            screenshot_path TEXT,
            FOREIGN KEY (job_id) REFERENCES jobs(id)
        );
    """)
    conn.commit()
    conn.close()
    return db_path


def get_connection(db_path=DEFAULT_DB_PATH):
    """Return a sqlite3 connection with row_factory = sqlite3.Row."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _row_to_dict(row):
    """Convert a sqlite3.Row to a plain dict."""
    return dict(row) if row else None


def upsert_job(db_path, company, role, apply_link, platform="custom",
               status="pending", row_index=None):
    """Insert or update a job by (company, apply_link), return job id."""
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute(
        "SELECT id FROM jobs WHERE company = ? AND apply_link = ?",
        (company, apply_link),
    )
    existing = cur.fetchone()
    now = datetime.now(timezone.utc).isoformat()

    if existing:
        job_id = existing["id"]
        cur.execute(
            """UPDATE jobs
               SET role = ?, platform = ?, status = ?, row_index = ?, updated_at = ?
               WHERE id = ?""",
            (role, platform, status, row_index, now, job_id),
        )
    else:
        cur.execute(
            """INSERT INTO jobs (company, role, apply_link, platform, status,
                                row_index, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (company, role, apply_link, platform, status, row_index, now, now),
        )
        job_id = cur.lastrowid

    conn.commit()
    conn.close()
    return job_id


def get_jobs(db_path, status=None):
    """Return list of dicts; optionally filter by status."""
    conn = get_connection(db_path)
    cur = conn.cursor()
    if status:
        cur.execute("SELECT * FROM jobs WHERE status = ?", (status,))
    else:
        cur.execute("SELECT * FROM jobs")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def get_job(db_path, job_id):
    """Return single job dict or None."""
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
    row = cur.fetchone()
    conn.close()
    return _row_to_dict(row)


def update_job_status(db_path, job_id, status, note=None):
    """Update status and updated_at; if note, also insert a log entry."""
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute(
        "UPDATE jobs SET status = ?, updated_at = ? WHERE id = ?",
        (status, now, job_id),
    )
    if note:
        cur.execute(
            """INSERT INTO logs (job_id, ts, level, message)
               VALUES (?, ?, 'INFO', ?)""",
            (job_id, now, note),
        )
    conn.commit()
    conn.close()


def create_application(db_path, job_id, resume_path, cover_text):
    """Insert application row, return app id."""
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO applications (job_id, resume_path, cover_text)
           VALUES (?, ?, ?)""",
        (job_id, resume_path, cover_text),
    )
    app_id = cur.lastrowid
    conn.commit()
    conn.close()
    return app_id


def confirm_submission(db_path, job_id):
    """Set user_submitted=1 on the latest application for a job, update job status."""
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute(
        """UPDATE applications SET user_submitted = 1
           WHERE id = (
               SELECT id FROM applications
               WHERE job_id = ? ORDER BY tailored_at DESC LIMIT 1
           )""",
        (job_id,),
    )
    if cur.rowcount == 0:
        conn.close()
        return
    now = datetime.now(timezone.utc).isoformat()
    cur.execute(
        "UPDATE jobs SET status = 'submitted', updated_at = ? WHERE id = ?",
        (now, job_id),
    )
    conn.commit()
    conn.close()


def add_log(db_path, job_id, level, message, screenshot_path=None):
    """Insert a log row."""
    conn = get_connection(db_path)
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO logs (job_id, level, message, screenshot_path)
           VALUES (?, ?, ?, ?)""",
        (job_id, level, message, screenshot_path),
    )
    conn.commit()
    conn.close()


def get_logs(db_path, job_id=None):
    """Return list of log dicts, optionally filtered by job_id."""
    conn = get_connection(db_path)
    cur = conn.cursor()
    if job_id:
        cur.execute("SELECT * FROM logs WHERE job_id = ?", (job_id,))
    else:
        cur.execute("SELECT * FROM logs")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows
