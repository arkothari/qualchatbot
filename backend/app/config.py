import os
from pathlib import Path

from dotenv import load_dotenv

# Local dev: read the project-root .env (Docker passes env vars directly)
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

DATA_DIR = Path(os.getenv("DATA_DIR", "./data")).resolve()
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")  # empty = admin endpoints open (dev only)

MODELS = {
    "haiku": "claude-haiku-5-5",
    "sonnet": "claude-sonnet-5-5",
}
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "sonnet")

MAX_TOOL_ROUNDS = int(os.getenv("MAX_TOOL_ROUNDS", "10"))
MAX_SQL_ROWS = int(os.getenv("MAX_SQL_ROWS", "200"))
MAX_TOOL_RESULT_CHARS = int(os.getenv("MAX_TOOL_RESULT_CHARS", "30000"))

# The five files that define a client's dataset.
FILE_KINDS = {
    "activities": "Activities (one row per activity)",
    "members": "Members (one row per member)",
    "member_profile": "Member profile (static profile fields)",
    "open_ends": "Open-end responses",
    "closed_ends": "Closed-end responses",
}
ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls", ".parquet"}
