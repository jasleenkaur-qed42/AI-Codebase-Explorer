import os
from pathlib import Path

from dotenv import dotenv_values

CREDENTIAL_KEYS = ("GITHUB_TOKEN", "JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN")

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_tracker_credentials() -> dict:
    """Read-only credential lookup for GitHub/Jira tracker linking.

    Real process environment variables take precedence; missing ones fall
    back to the `.env` file at the project root (where the placeholder
    values ship until a real token is filled in). Never mutates
    `os.environ`, so this is safe to call repeatedly and safe in tests.
    """
    file_values = dotenv_values(PROJECT_ROOT / ".env")
    return {key: os.environ.get(key) or file_values.get(key) for key in CREDENTIAL_KEYS}
