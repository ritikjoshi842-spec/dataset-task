import os
import re
from urllib.parse import quote_plus
from dotenv import load_dotenv

load_dotenv()

MAX_UPLOAD_SIZE_MB = int(os.getenv("MAX_UPLOAD_SIZE_MB", "50"))
MAX_PLOT_POINTS = int(os.getenv("MAX_PLOT_POINTS", "5000"))

GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")


def _get_secret_or_env(key: str, default: str = None) -> str | None:
    """Reads a configuration value from environment variables or Streamlit secrets without raising."""
    val = os.getenv(key)
    if val:
        return val.strip()
    try:
        import streamlit as st

        if hasattr(st, "secrets"):
            if key in st.secrets:
                return str(st.secrets[key]).strip()
            if "database" in st.secrets and key.lower() in st.secrets["database"]:
                return str(st.secrets["database"][key.lower()]).strip()
    except Exception:
        pass
    return default


def get_database_url() -> str | None:
    """Resolves the Supabase PostgreSQL connection URL from env vars or Streamlit secrets.
    Never hardcodes credentials in source code."""
    load_dotenv(override=True)
    for key in ("DATABASE_URL", "SUPABASE_DB_URL", "POSTGRES_URL"):
        url = _get_secret_or_env(key)
        if url and "[YOUR-PASSWORD]" not in url and "your_password" not in url:
            return url

    # Or assemble from individual Supabase parameters if SUPABASE_DB_PASSWORD and SUPABASE_DB_HOST are provided
    password = _get_secret_or_env("SUPABASE_DB_PASSWORD") or _get_secret_or_env("DB_PASSWORD")
    host = _get_secret_or_env("SUPABASE_DB_HOST")
    if password and host and password not in ("[YOUR-PASSWORD]", "your_password"):
        port = _get_secret_or_env("SUPABASE_DB_PORT", "5432")
        dbname = _get_secret_or_env("SUPABASE_DB_NAME", "postgres")
        user = _get_secret_or_env("SUPABASE_DB_USER", "postgres")
        encoded_pw = quote_plus(password)
        return f"postgresql://{user}:{encoded_pw}@{host}:{port}/{dbname}?sslmode=require"

    return None


def sanitize_db_error(err: Exception | str) -> str:
    """Scrubs database URIs, passwords, and host credentials from error messages."""
    msg = str(err)
    # Redact postgresql://... connection strings
    msg = re.sub(r"postgresql(?:\+\w+)?://[^\s'\"]+", "postgresql://[REDACTED]", msg, flags=re.IGNORECASE)
    # Redact password=... patterns
    msg = re.sub(r"(password\s*=\s*)[^\s'\";]+", r"\1[REDACTED]", msg, flags=re.IGNORECASE)
    return msg
