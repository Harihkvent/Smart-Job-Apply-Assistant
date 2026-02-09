import os

import yaml
from dotenv import load_dotenv

DEFAULTS = {
    "google_sheet_id": "",
    "sheet_range": "Sheet1!A:H",
    "browser_profile_dir": "",
    "resume_base_path": "",
    "tailor_temp_dir": "/tmp/tailor_resumes",
    "llm_provider": "ollama",
    "llm_endpoint": "http://localhost:11434",
    "llm_model": "llama3",
    "max_concurrent_workers": 2,
    "random_delay_min_ms": 200,
    "random_delay_max_ms": 1200,
    "max_daily_applies": 40,
    "db_path": "jobs.db",
    "screenshot_dir": "/tmp/screenshots",
    "log_retention_days": 90,
    "server_host": "127.0.0.1",
    "server_port": 5000,
    "server_token": "",
}


def load_config(config_path="config.yml"):
    load_dotenv()

    config_path = os.environ.get("CONFIG_PATH", config_path)

    file_config = {}
    if os.path.exists(config_path):
        with open(config_path, "r") as f:
            file_config = yaml.safe_load(f) or {}

    config = {**DEFAULTS, **file_config}

    env_overrides = {
        "google_client_id": os.environ.get("GOOGLE_CLIENT_ID"),
        "google_client_secret": os.environ.get("GOOGLE_CLIENT_SECRET"),
        "llm_api_key": os.environ.get("LLM_API_KEY"),
        "sentry_dsn": os.environ.get("SENTRY_DSN"),
        "db_path": os.environ.get("DB_PATH"),
    }

    for key, value in env_overrides.items():
        if value is not None:
            config[key] = value

    return config
