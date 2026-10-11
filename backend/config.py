import os
import re
from pathlib import Path
from urllib.parse import quote_plus
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

MAX_UPLOAD_SIZE_MB = int(os.getenv("MAX_UPLOAD_SIZE_MB", "50"))
MAX_PLOT_POINTS = int(os.getenv("MAX_PLOT_POINTS", "5000"))

_PLACEHOLDER_VALUES = {
    "",
    "your_groq_api_key_here",
    "gsk_your_groq_api_key_here",
    "[your-password]",
    "your_password",
    "your_supabase_database_password",
    "[your-supabase-host]",
}


def _is_placeholder(val: str | None) -> bool:
    if not val:
        return True
    cleaned = val.strip()
    if cleaned.lower() in _PLACEHOLDER_VALUES:
        return True
    if "[YOUR-PASSWORD]" in cleaned or "[YOUR-SUPABASE-HOST]" in cleaned:
        return True
    return False


def _get_secret_or_env(key: str, default: str | None = None) -> str | None:
    """Reads a configuration value from Streamlit secrets (`st.secrets`) or environment variables.
    Supports both top-level keys and nested `[database]` / `[supabase]` sections in `secrets.toml`."""
    # 1. Check environment variables
    val = os.getenv(key)
    if val and not _is_placeholder(val):
        return val.strip()

    # 2. Check Streamlit secrets (.streamlit/secrets.toml locally or Streamlit Community Cloud Secrets)
    try:
        import streamlit as st

        if hasattr(st, "secrets"):
            if key in st.secrets:
                s_val = str(st.secrets[key]).strip()
                if not _is_placeholder(s_val):
                    return s_val
            for section in ("database", "supabase"):
                if section in st.secrets:
                    sec_obj = st.secrets[section]
                    for candidate_key in (key, key.lower(), key.upper()):
                        if candidate_key in sec_obj:
                            s_val = str(sec_obj[candidate_key]).strip()
                            if not _is_placeholder(s_val):
                                return s_val
    except Exception:
        pass

    return default


def get_groq_api_key() -> str | None:
    """Resolves GROQ_API_KEY from environment variables or Streamlit st.secrets."""
    load_dotenv(PROJECT_ROOT / ".env", override=True)
    return _get_secret_or_env("GROQ_API_KEY")


def get_groq_model() -> str:
    """Resolves GROQ_MODEL from environment variables or Streamlit st.secrets."""
    return _get_secret_or_env("GROQ_MODEL", "openai/gpt-oss-120b") or "openai/gpt-oss-120b"


GROQ_MODEL = get_groq_model()


def get_database_url() -> str | None:
    """Resolves the Supabase PostgreSQL connection URL from env vars or Streamlit st.secrets.
    Never hardcodes credentials in source code."""
    load_dotenv(PROJECT_ROOT / ".env", override=True)
    for key in ("DATABASE_URL", "SUPABASE_DB_URL", "POSTGRES_URL"):
        url = _get_secret_or_env(key)
        if url and not _is_placeholder(url):
            return url

    # Or assemble from individual Supabase parameters if SUPABASE_DB_PASSWORD and SUPABASE_DB_HOST are provided
    password = _get_secret_or_env("SUPABASE_DB_PASSWORD") or _get_secret_or_env("DB_PASSWORD")
    host = _get_secret_or_env("SUPABASE_DB_HOST") or _get_secret_or_env("DB_HOST")
    if password and host and not _is_placeholder(password) and not _is_placeholder(host):
        port = _get_secret_or_env("SUPABASE_DB_PORT", "5432")
        dbname = _get_secret_or_env("SUPABASE_DB_NAME", "postgres")
        user = _get_secret_or_env("SUPABASE_DB_USER", "postgres")
        encoded_pw = quote_plus(password)
        ssl_suffix = "" if "sslmode=" in host else "?sslmode=require"
        return f"postgresql://{user}:{encoded_pw}@{host}:{port}/{dbname}{ssl_suffix}"

    return None


def sanitize_db_error(err: Exception | str) -> str:
    """Scrubs database URIs, passwords, API keys, and host credentials from error messages."""
    msg = str(err)
    # Redact postgresql://... connection strings
    msg = re.sub(r"postgresql(?:\+\w+)?://[^\s'\"]+", "postgresql://[REDACTED]", msg, flags=re.IGNORECASE)
    # Redact password=... patterns
    msg = re.sub(r"(password\s*=\s*)[^\s'\";]+", r"\1[REDACTED]", msg, flags=re.IGNORECASE)
    # Redact Groq API keys if ever present
    msg = re.sub(r"gsk_[A-Za-z0-9]{16,}", "gsk_[REDACTED]", msg)
    return msg
