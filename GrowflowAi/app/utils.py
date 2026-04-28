import re
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from flask import jsonify
from sqlalchemy import inspect, text

from .extensions import db
from .models import ApiKey, Attendance, Customer, Employee, Invoice, MarketingLog, Subscription, User


EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
ALLOWED_ATTENDANCE_STATUSES = {"present", "absent", "leave"}
ALLOWED_INVOICE_STATUSES = {"paid", "pending", "overdue"}


def json_error(message, status_code=400, details=None):
    payload = {"success": False, "message": message}
    if details:
        payload["details"] = details
    return jsonify(payload), status_code


def normalize_email(value):
    return value.strip().lower()


def validate_email(value):
    return bool(EMAIL_RE.match(value or ""))


def validate_password(value):
    if len(value or "") < 8:
        return False, "Password must be at least 8 characters long."
    return True, None


def clean_text(value, field_name, min_length=1, max_length=255):
    text = (value or "").strip()
    if len(text) < min_length:
        raise ValueError(f"{field_name} is required.")
    if len(text) > max_length:
        raise ValueError(f"{field_name} must be under {max_length} characters.")
    return text


def parse_amount(value):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError):
        raise ValueError("Amount must be a valid number.") from None
    if amount <= 0:
        raise ValueError("Amount must be greater than zero.")
    return amount.quantize(Decimal("0.01"))


def build_growth_series(invoices):
    today = date.today()
    bucket = {}
    for offset in range(6, -1, -1):
        current_day = today - timedelta(days=offset)
        bucket[current_day.isoformat()] = 0.0

    for invoice in invoices:
        issued_on = invoice.issued_on.isoformat()
        if issued_on in bucket:
            bucket[issued_on] += float(invoice.amount)

    return [
        {"label": day[5:], "value": round(value, 2)}
        for day, value in bucket.items()
    ]


def ensure_schema_compatibility():
    inspector = inspect(db.engine)
    table_names = set(inspector.get_table_names())
    statements = []

    if "users" in table_names:
        user_columns = {column["name"] for column in inspector.get_columns("users")}
        if "supabase_uid" not in user_columns:
            statements.append("ALTER TABLE users ADD COLUMN supabase_uid VARCHAR(80)")
        if "auth_provider" not in user_columns:
            statements.append("ALTER TABLE users ADD COLUMN auth_provider VARCHAR(20) NOT NULL DEFAULT 'local'")
        if "role" not in user_columns:
            statements.append("ALTER TABLE users ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'owner'")

    if "api_keys" in table_names:
        api_key_columns = {column["name"] for column in inspector.get_columns("api_keys")}
        if "status" not in api_key_columns:
            statements.append("ALTER TABLE api_keys ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'saved'")

    if "subscriptions" in table_names:
        subscription_columns = {column["name"] for column in inspector.get_columns("subscriptions")}
        if "trial_start_date" not in subscription_columns:
            statements.append("ALTER TABLE subscriptions ADD COLUMN trial_start_date DATE")
        if "trial_end_date" not in subscription_columns:
            statements.append("ALTER TABLE subscriptions ADD COLUMN trial_end_date DATE")
        if "promo_code_used" not in subscription_columns:
            statements.append("ALTER TABLE subscriptions ADD COLUMN promo_code_used VARCHAR(80)")
        if "promo_discount_percent" not in subscription_columns:
            statements.append(
                "ALTER TABLE subscriptions ADD COLUMN promo_discount_percent INTEGER NOT NULL DEFAULT 0"
            )
        if "promo_discount_amount" not in subscription_columns:
            statements.append(
                "ALTER TABLE subscriptions ADD COLUMN promo_discount_amount INTEGER NOT NULL DEFAULT 0"
            )
        if "amount_due" not in subscription_columns:
            statements.append("ALTER TABLE subscriptions ADD COLUMN amount_due INTEGER NOT NULL DEFAULT 0")
        if "payment_provider" not in subscription_columns:
            statements.append("ALTER TABLE subscriptions ADD COLUMN payment_provider VARCHAR(40)")
        if "payment_status" not in subscription_columns:
            statements.append("ALTER TABLE subscriptions ADD COLUMN payment_status VARCHAR(20) NOT NULL DEFAULT 'pending'")
        if "payment_reference" not in subscription_columns:
            statements.append("ALTER TABLE subscriptions ADD COLUMN payment_reference VARCHAR(255)")
        if "activated_at" not in subscription_columns:
            statements.append("ALTER TABLE subscriptions ADD COLUMN activated_at DATETIME")
        if "upgrade_prompt_shown_at" not in subscription_columns:
            statements.append("ALTER TABLE subscriptions ADD COLUMN upgrade_prompt_shown_at DATETIME")

    if not statements:
        return

    with db.engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
        if "subscriptions" in table_names:
            connection.execute(
                text(
                    "UPDATE subscriptions SET trial_start_date = date(created_at) "
                    "WHERE trial_start_date IS NULL AND plan = 'free-trial'"
                )
            )
            connection.execute(
                text(
                    "UPDATE subscriptions SET trial_end_date = date(created_at, '+7 day') "
                    "WHERE trial_end_date IS NULL AND plan = 'free-trial'"
                )
            )
            connection.execute(
                text(
                    "UPDATE subscriptions SET amount_due = 0 "
                    "WHERE amount_due IS NULL"
                )
            )
            connection.execute(
                text(
                    "UPDATE subscriptions SET payment_status = 'paid', amount_due = 200 "
                    "WHERE plan IN ('pro-200', 'pro-99', 'starter-99')"
                )
            )


def purge_legacy_demo_user():
    existing_user = User.query.filter_by(email="demo@growflow.ai").first()
    if not existing_user:
        return

    db.session.delete(existing_user)
    db.session.commit()
