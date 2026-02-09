"""Tests for src.server module."""

import pytest

from src.db import add_log, create_application, init_db, upsert_job
from src.server import create_app


@pytest.fixture
def app_and_db(tmp_path):
    """Create a Flask test app with a temporary database."""
    db_path = str(tmp_path / "test.db")
    config = {
        "db_path": db_path,
        "server_token": "",
    }
    init_db(db_path)
    app = create_app(config=config)
    app.config["TESTING"] = True
    return app, db_path


@pytest.fixture
def client(app_and_db):
    """Flask test client."""
    app, _ = app_and_db
    return app.test_client()


@pytest.fixture
def db_path(app_and_db):
    """Return the db_path for direct DB manipulation."""
    _, path = app_and_db
    return path


def test_get_jobs(client, db_path):
    """Verify GET /api/jobs returns job list."""
    upsert_job(db_path, "Acme", "Dev", "https://acme.com")
    upsert_job(db_path, "Beta", "QA", "https://beta.com")

    resp = client.get("/api/jobs")
    assert resp.status_code == 200

    data = resp.get_json()
    assert "jobs" in data
    assert len(data["jobs"]) == 2


def test_get_job_not_found(client):
    """Verify 404 for missing job."""
    resp = client.get("/api/jobs/9999")
    assert resp.status_code == 404

    data = resp.get_json()
    assert "error" in data


def test_confirm_submit(client, db_path):
    """POST confirm-submit, verify status changes."""
    job_id = upsert_job(db_path, "Z", "Dev", "https://z.com")
    create_application(db_path, job_id, "/tmp/resume.txt", "cover")

    resp = client.post(f"/api/jobs/{job_id}/confirm-submit")
    assert resp.status_code == 200

    data = resp.get_json()
    assert data["status"] == "submitted"

    # Verify via GET
    resp2 = client.get(f"/api/jobs/{job_id}")
    assert resp2.get_json()["job"]["status"] == "submitted"


def test_get_logs(client, db_path):
    """Verify GET /api/logs returns logs."""
    job_id = upsert_job(db_path, "LogCo", "Dev", "https://logco.com")
    add_log(db_path, job_id, "INFO", "test log msg")

    resp = client.get("/api/logs")
    assert resp.status_code == 200

    data = resp.get_json()
    assert "logs" in data
    assert len(data["logs"]) == 1
    assert data["logs"][0]["message"] == "test log msg"


def test_get_logs_filtered(client, db_path):
    """Verify GET /api/logs?job_id= filters correctly."""
    id1 = upsert_job(db_path, "A", "Dev", "https://a.com")
    id2 = upsert_job(db_path, "B", "QA", "https://b.com")
    add_log(db_path, id1, "INFO", "log A")
    add_log(db_path, id2, "INFO", "log B")

    resp = client.get(f"/api/logs?job_id={id1}")
    data = resp.get_json()
    assert len(data["logs"]) == 1
    assert data["logs"][0]["message"] == "log A"


def test_dashboard(client):
    """Verify GET / returns HTML."""
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"Smart Job Apply Assistant" in resp.data
    assert b"<html" in resp.data


def test_auth_required(tmp_path):
    """When token is set, verify 401 without auth header."""
    db_path = str(tmp_path / "auth_test.db")
    config = {
        "db_path": db_path,
        "server_token": "secret-token-123",
    }
    init_db(db_path)
    app = create_app(config=config)
    app.config["TESTING"] = True
    client = app.test_client()

    # Without token → 401
    resp = client.get("/api/jobs")
    assert resp.status_code == 401

    # With correct token → 200
    resp = client.get("/api/jobs", headers={
        "Authorization": "Bearer secret-token-123",
    })
    assert resp.status_code == 200

    # Dashboard is not protected
    resp = client.get("/")
    assert resp.status_code == 200
