import os
import tempfile
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent


def _resolve_database_url():
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return database_url

    if os.getenv("VERCEL") or os.getenv("VERCEL_ENV") or os.getenv("VERCEL_URL"):
        return f"sqlite:///{(Path(tempfile.gettempdir()) / 'growflow.db').as_posix()}"

    return f"sqlite:///{(BASE_DIR / 'growflow.db').as_posix()}"


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "growflow-dev-secret")
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "growflow-jwt-secret")
    SQLALCHEMY_DATABASE_URI = _resolve_database_url()
    SQLALCHEMY_ENGINE_OPTIONS = (
        {"connect_args": {"check_same_thread": False}}
        if SQLALCHEMY_DATABASE_URI.startswith("sqlite")
        else {}
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JSON_SORT_KEYS = False
    RATELIMIT_STORAGE_URI = os.getenv("RATELIMIT_STORAGE_URI", "memory://")
    TRIAL_DURATION_DAYS = int(os.getenv("TRIAL_DURATION_DAYS", "7"))
    SUBSCRIPTION_BASE_PRICE_INR = int(os.getenv("SUBSCRIPTION_BASE_PRICE_INR", "200"))
    SUPABASE_URL = os.getenv("SUPABASE_URL", "")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
    GROQ_TIMEOUT_SECONDS = int(os.getenv("GROQ_TIMEOUT_SECONDS", "25"))
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    WHATSAPP_API_KEY = os.getenv("WHATSAPP_API_KEY", "")
    WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
    WHATSAPP_BUSINESS_ACCOUNT_ID = os.getenv("WHATSAPP_BUSINESS_ACCOUNT_ID", "")
    WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "")
    WHATSAPP_API_VERSION = os.getenv("WHATSAPP_API_VERSION", "v20.0")
    WHATSAPP_SETTINGS_ENCRYPTION_KEY = os.getenv("WHATSAPP_SETTINGS_ENCRYPTION_KEY", "")
    SUPPORT_EMAIL = os.getenv("SUPPORT_EMAIL", "support@growflowai.app")
    SUPPORT_PHONE = os.getenv("SUPPORT_PHONE", "+91 90000 00000")
    RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "")
    RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "")
    RAZORPAY_WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET", "")
    STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
    STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    SUBSCRIPTION_DEMO_PAYMENTS = os.getenv("SUBSCRIPTION_DEMO_PAYMENTS", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
