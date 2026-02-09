"""Tests for src.db module."""

import pytest

from src.db import (
    add_log,
    confirm_submission,
    create_application,
    get_job,
    get_jobs,
    get_logs,
    init_db,
    update_job_status,
    upsert_job,
)


@pytest.fixture
def db(tmp_path):
    """Create a temporary database and return its path."""
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    return db_path


def test_init_db(tmp_path):
    """Verify tables are created."""
    import sqlite3

    db_path = str(tmp_path / "init_test.db")
    init_db(db_path)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row[0] for row in cur.fetchall()}
    conn.close()

    assert "jobs" in tables
    assert "applications" in tables
    assert "logs" in tables


def test_upsert_job(db):
    """Insert a job, verify it exists."""
    job_id = upsert_job(db, "Acme", "Engineer", "https://acme.com/apply")
    assert job_id is not None

    job = get_job(db, job_id)
    assert job is not None
    assert job["company"] == "Acme"
    assert job["role"] == "Engineer"
    assert job["status"] == "pending"


def test_upsert_job_update(db):
    """Insert same job twice, verify update not duplicate."""
    id1 = upsert_job(db, "Acme", "Engineer", "https://acme.com/apply")
    id2 = upsert_job(db, "Acme", "Senior Engineer", "https://acme.com/apply")

    assert id1 == id2

    job = get_job(db, id1)
    assert job["role"] == "Senior Engineer"

    all_jobs = get_jobs(db)
    assert len(all_jobs) == 1


def test_get_jobs(db):
    """Insert multiple jobs, get all, get by status."""
    upsert_job(db, "A", "Dev", "https://a.com", status="pending")
    upsert_job(db, "B", "QA", "https://b.com", status="submitted")
    upsert_job(db, "C", "PM", "https://c.com", status="pending")

    all_jobs = get_jobs(db)
    assert len(all_jobs) == 3

    pending = get_jobs(db, status="pending")
    assert len(pending) == 2

    submitted = get_jobs(db, status="submitted")
    assert len(submitted) == 1
    assert submitted[0]["company"] == "B"


def test_get_job(db):
    """Get single job by id."""
    job_id = upsert_job(db, "TestCo", "Analyst", "https://testco.com/apply")
    job = get_job(db, job_id)

    assert job is not None
    assert job["id"] == job_id
    assert job["company"] == "TestCo"

    missing = get_job(db, 9999)
    assert missing is None


def test_update_job_status(db):
    """Update status and verify."""
    job_id = upsert_job(db, "X", "Dev", "https://x.com")
    update_job_status(db, job_id, "in_progress", note="started processing")

    job = get_job(db, job_id)
    assert job["status"] == "in_progress"

    logs = get_logs(db, job_id=job_id)
    assert len(logs) == 1
    assert "started processing" in logs[0]["message"]


def test_create_application(db):
    """Create application for a job."""
    job_id = upsert_job(db, "Y", "Dev", "https://y.com")
    app_id = create_application(db, job_id, "/tmp/resume.txt", "cover text")

    assert app_id is not None
    assert isinstance(app_id, int)


def test_confirm_submission(db):
    """Confirm and verify job becomes 'submitted'."""
    job_id = upsert_job(db, "Z", "Dev", "https://z.com")
    create_application(db, job_id, "/tmp/resume.txt", "cover text")

    confirm_submission(db, job_id)

    job = get_job(db, job_id)
    assert job["status"] == "submitted"


def test_add_log(db):
    """Add log entry and verify."""
    job_id = upsert_job(db, "LogCo", "Dev", "https://logco.com")
    add_log(db, job_id, "INFO", "test message", screenshot_path="/tmp/shot.png")

    logs = get_logs(db, job_id=job_id)
    assert len(logs) == 1
    assert logs[0]["message"] == "test message"
    assert logs[0]["level"] == "INFO"
    assert logs[0]["screenshot_path"] == "/tmp/shot.png"


def test_get_logs(db):
    """Get logs filtered by job_id."""
    id1 = upsert_job(db, "A", "Dev", "https://a.com")
    id2 = upsert_job(db, "B", "QA", "https://b.com")

    add_log(db, id1, "INFO", "log for A")
    add_log(db, id2, "ERROR", "log for B")
    add_log(db, id1, "WARN", "another log for A")

    all_logs = get_logs(db)
    assert len(all_logs) == 3

    a_logs = get_logs(db, job_id=id1)
    assert len(a_logs) == 2
    assert all(log["job_id"] == id1 for log in a_logs)

    b_logs = get_logs(db, job_id=id2)
    assert len(b_logs) == 1
    assert b_logs[0]["job_id"] == id2
