"""Tests for src.sheets module."""

import sys
from unittest.mock import MagicMock, patch

import pytest

# Mock Google API imports before importing sheets module
_google_mocks = {}
for mod_name in [
    "google",
    "google.auth",
    "google.auth.transport",
    "google.auth.transport.requests",
    "google.oauth2",
    "google.oauth2.credentials",
    "google_auth_oauthlib",
    "google_auth_oauthlib.flow",
    "googleapiclient",
    "googleapiclient.discovery",
]:
    if mod_name not in sys.modules:
        _google_mocks[mod_name] = MagicMock()
        sys.modules[mod_name] = _google_mocks[mod_name]

from src.sheets import _rows_to_dicts, read_all_jobs, read_pending_jobs, update_job_status

SPREADSHEET_ID = "test-sheet-id"

SAMPLE_ROWS = [
    ["Company", "Role", "Apply Link", "Location", "Platform", "Status", "Notes", "LastTriedAt"],
    ["Acme", "Dev", "https://acme.com", "Remote", "lever", "pending", "", ""],
    ["Beta", "QA", "https://beta.com", "NYC", "greenhouse", "submitted", "done", "2024-01-01"],
    ["Gamma", "PM", "https://gamma.com", "SF", "custom", "", "", ""],
]


def _make_service(rows):
    """Build a mock Google Sheets service that returns the given rows."""
    service = MagicMock()
    values_mock = MagicMock()

    get_mock = MagicMock()
    get_mock.execute.return_value = {"values": rows}
    values_mock.get.return_value = get_mock

    update_mock = MagicMock()
    update_mock.execute.return_value = {}
    values_mock.update.return_value = update_mock

    service.spreadsheets.return_value.values.return_value = values_mock
    return service


def test_read_pending_jobs():
    """Mock the Google Sheets API service, verify parsing."""
    service = _make_service(SAMPLE_ROWS)

    pending = read_pending_jobs(service, SPREADSHEET_ID)

    # "Acme" is pending, "Gamma" has empty status → both pending
    assert len(pending) == 2
    companies = {j["company"] for j in pending}
    assert "Acme" in companies
    assert "Gamma" in companies
    assert "Beta" not in companies

    # Verify row_index is set (1-based, header is row 1)
    for job in pending:
        assert "row_index" in job
        assert job["row_index"] >= 2


def test_read_pending_jobs_empty():
    """Mock empty response."""
    service = _make_service([])

    pending = read_pending_jobs(service, SPREADSHEET_ID)
    assert pending == []


def test_read_pending_jobs_header_only():
    """Only header row, no data rows."""
    service = _make_service([SAMPLE_ROWS[0]])

    pending = read_pending_jobs(service, SPREADSHEET_ID)
    assert pending == []


def test_update_job_status():
    """Mock the update call, verify it's called correctly."""
    service = _make_service(SAMPLE_ROWS)

    update_job_status(service, SPREADSHEET_ID, row_index=2, status="submitted",
                      notes="applied via bot")

    update_call = service.spreadsheets().values().update
    update_call.assert_called_once()

    call_kwargs = update_call.call_args
    assert call_kwargs.kwargs["spreadsheetId"] == SPREADSHEET_ID
    assert "F2:H2" in call_kwargs.kwargs["range"]
    assert call_kwargs.kwargs["body"]["values"][0][0] == "submitted"
    assert call_kwargs.kwargs["body"]["values"][0][1] == "applied via bot"


def test_read_all_jobs():
    """Mock and verify all rows returned."""
    service = _make_service(SAMPLE_ROWS)

    jobs = read_all_jobs(service, SPREADSHEET_ID)

    assert len(jobs) == 3
    assert jobs[0]["company"] == "Acme"
    assert jobs[1]["company"] == "Beta"
    assert jobs[2]["company"] == "Gamma"

    # Verify all expected keys are present
    expected_keys = {"company", "role", "apply_link", "location",
                     "platform", "status", "notes", "last_tried_at", "row_index"}
    for job in jobs:
        assert set(job.keys()) == expected_keys
