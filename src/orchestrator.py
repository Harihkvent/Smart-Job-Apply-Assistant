import json
import logging
import os
import random
import time

from src.db import (
    add_log,
    create_application,
    get_job,
    get_jobs,
    init_db,
    update_job_status,
    upsert_job,
)
from src.tailor import tailor_resume

try:
    from src.sheets import get_sheets_service, read_pending_jobs
    from src.sheets import update_job_status as sheets_update_status
except ImportError:
    get_sheets_service = None
    read_pending_jobs = None
    sheets_update_status = None

try:
    from src.playwright_worker import prepare_application
except ImportError:
    prepare_application = None

logger = logging.getLogger(__name__)


def load_profile(profile_path="profile.json"):
    """Load user profile from a JSON file."""
    profile_path = os.path.abspath(profile_path)
    if not os.path.exists(profile_path):
        raise FileNotFoundError(
            f"Profile file not found: {profile_path}. "
            "Please create a profile.json with your information."
        )
    with open(profile_path, "r") as f:
        return json.load(f)


def process_job(job, profile, config):
    """Process a single job: tailor resume, create application, and prepare submission."""
    db_path = config["db_path"]
    job_id = job["id"]

    try:
        # Step 1: Mark job as in-progress
        update_job_status(db_path, job_id, "in-progress")
        add_log(db_path, job_id, "INFO", "Started processing job")

        # Step 2: Tailor resume
        add_log(db_path, job_id, "INFO", "Tailoring resume")
        tailored = tailor_resume(job, profile, config)
        resume_path = tailored["resume_pdf_path"]
        cover_text = tailored["cover_text"]

        # Step 3: Create application record
        app_id = create_application(db_path, job_id, resume_path, cover_text)
        add_log(db_path, job_id, "INFO", f"Application record created: {app_id}")

        # Step 4: Prepare application via browser
        if prepare_application is None:
            raise ImportError("playwright_worker is not available")

        result = prepare_application(
            job["apply_link"], resume_path, cover_text, profile, config
        )
        add_log(db_path, job_id, "INFO", f"Browser preparation complete: {result.get('status')}")

        # Step 5: Update status based on result
        if result.get("status") == "ready_for_submit":
            update_job_status(db_path, job_id, "ready_for_submit")
            add_log(db_path, job_id, "INFO", "Job ready for manual submit")
        else:
            error_msg = result.get("error", "Unknown error during preparation")
            update_job_status(db_path, job_id, "failed", note=error_msg)
            add_log(db_path, job_id, "ERROR", error_msg)

        return result

    except Exception as e:
        error_msg = f"Error processing job {job_id}: {e}"
        logger.error(error_msg)
        try:
            update_job_status(db_path, job_id, "failed", note=str(e))
            add_log(db_path, job_id, "ERROR", error_msg)
        except Exception:
            logger.exception("Failed to update job status after error")
        return {"status": "failed", "error": str(e)}


def run_batch(config, profile_path="profile.json"):
    """Main batch processing: read pending jobs from Google Sheet and process each."""
    profile = load_profile(profile_path)
    db_path = init_db(config["db_path"])

    if get_sheets_service is None or read_pending_jobs is None:
        raise ImportError("Google Sheets integration is not available")

    service = get_sheets_service()
    spreadsheet_id = config["google_sheet_id"]
    pending_jobs = read_pending_jobs(service, spreadsheet_id, config.get("sheet_range", "Sheet1!A:H"))

    max_applies = config.get("max_daily_applies", 40)
    summary = {"total": 0, "successful": 0, "failed": 0}

    for job in pending_jobs[:max_applies]:
        summary["total"] += 1

        # Upsert job into local DB
        job_id = upsert_job(
            db_path,
            company=job["company"],
            role=job["role"],
            apply_link=job["apply_link"],
            platform=job.get("platform", "custom"),
            status="pending",
            row_index=job.get("row_index"),
        )
        job["id"] = job_id

        # Process the job
        result = process_job(job, profile, config)

        # Update Google Sheet row status
        if sheets_update_status is not None and "row_index" in job:
            try:
                status = result.get("status", "failed")
                notes = result.get("error", "")
                sheets_update_status(service, spreadsheet_id, job["row_index"], status, notes)
            except Exception:
                logger.exception("Failed to update Google Sheet status for job %s", job_id)

        if result.get("status") == "ready_for_submit":
            summary["successful"] += 1
        else:
            summary["failed"] += 1

        # Random delay between jobs (10-30 seconds)
        jobs_to_process = min(len(pending_jobs), max_applies)
        if summary["total"] < jobs_to_process:
            delay = random.uniform(10, 30)
            logger.info("Waiting %.1f seconds before next job", delay)
            time.sleep(delay)

    logger.info("Batch complete: %s", summary)
    return summary


def run_single(job_id, config, profile_path="profile.json"):
    """Process a single job by its DB id."""
    profile = load_profile(profile_path)
    init_db(config["db_path"])

    job = get_job(config["db_path"], job_id)
    if job is None:
        raise ValueError(f"Job with id {job_id} not found in database")

    return process_job(dict(job), profile, config)


def retry_failed(config, profile_path="profile.json"):
    """Retry all jobs with status 'failed'."""
    profile = load_profile(profile_path)
    init_db(config["db_path"])

    failed_jobs = get_jobs(config["db_path"], status="failed")
    summary = {"total": 0, "successful": 0, "failed": 0}

    for job in failed_jobs:
        summary["total"] += 1
        result = process_job(dict(job), profile, config)

        if result.get("status") == "ready_for_submit":
            summary["successful"] += 1
        else:
            summary["failed"] += 1

    logger.info("Retry complete: %s", summary)
    return summary
