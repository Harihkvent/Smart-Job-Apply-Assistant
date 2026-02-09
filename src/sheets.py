"""Google Sheets integration for the Smart Job Apply Assistant.

Column mapping (expected sheet columns):
  A: Company | B: Role | C: Apply Link | D: Location
  E: Platform | F: Status | G: Notes | H: LastTriedAt
"""

import os
from datetime import datetime, timezone

try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
except ImportError as exc:
    raise ImportError(
        "Google API libraries are required. Install them with:\n"
        "  pip install google-api-python-client google-auth-httplib2 "
        "google-auth-oauthlib"
    ) from exc

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

COLUMN_KEYS = [
    "company", "role", "apply_link", "location",
    "platform", "status", "notes", "last_tried_at",
]


def get_sheets_service(credentials_path="credentials.json"):
    """Load OAuth2 credentials and return the Google Sheets API service."""
    credentials_path = os.path.abspath(credentials_path)
    token_path = os.path.join(os.path.dirname(credentials_path), "token.json")

    creds = None
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                credentials_path, SCOPES
            )
            creds = flow.run_local_server(port=0)
        fd = os.open(token_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as token_file:
            token_file.write(creds.to_json())

    return build("sheets", "v4", credentials=creds)


def _rows_to_dicts(rows):
    """Convert raw sheet rows (list of lists) into list of dicts.

    The first row is treated as headers (skipped). Each subsequent row is
    mapped to COLUMN_KEYS with a ``row_index`` indicating its 1-based
    position in the sheet.
    """
    if not rows or len(rows) < 2:
        return []

    results = []
    for i, row in enumerate(rows[1:], start=2):
        padded = row + [""] * (len(COLUMN_KEYS) - len(row))
        entry = {key: padded[idx] for idx, key in enumerate(COLUMN_KEYS)}
        entry["row_index"] = i
        results.append(entry)
    return results


def read_pending_jobs(service, spreadsheet_id, sheet_range="Sheet1!A:H"):
    """Return rows where status is 'pending' or empty."""
    all_jobs = read_all_jobs(service, spreadsheet_id, sheet_range)
    return [
        job for job in all_jobs
        if (job.get("status") or "").strip().lower() in ("pending", "")
    ]


def update_job_status(service, spreadsheet_id, row_index, status,
                      notes="", sheet_name="Sheet1"):
    """Update Status (F), Notes (G), and LastTriedAt (H) for *row_index*."""
    now = datetime.now(timezone.utc).isoformat()
    range_str = f"{sheet_name}!F{row_index}:H{row_index}"
    body = {"values": [[status, notes, now]]}

    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=range_str,
        valueInputOption="USER_ENTERED",
        body=body,
    ).execute()


def read_all_jobs(service, spreadsheet_id, sheet_range="Sheet1!A:H"):
    """Read all rows from the sheet and return them as a list of dicts."""
    result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=sheet_range)
        .execute()
    )
    rows = result.get("values", [])
    return _rows_to_dicts(rows)
