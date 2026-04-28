import csv
import io
import json
import os
import secrets
import zipfile
from datetime import date, datetime, timedelta

import requests
from flask import Blueprint, Response, current_app, jsonify, request, url_for
from flask_jwt_extended import create_access_token, get_jwt_identity, jwt_required

from ..extensions import db, jwt, limiter
from ..models import (
    ApiKey,
    Attendance,
    Customer,
    Employee,
    Invoice,
    MarketingLog,
    Setting,
    Subscription,
    User,
    WhatsAppMessage,
    WhatsAppSetting,
    WhatsAppTemplate,
)
from ..services.ai_service import generate_business_content, test_ai_provider_connection
from ..services.whatsapp_service import (
    build_message_content,
    decrypt_secret,
    disconnect_whatsapp_settings,
    encrypt_secret,
    environment_whatsapp_available,
    find_builtin_template,
    get_builtin_templates,
    resolve_whatsapp_credentials,
    send_whatsapp_message,
    serialize_whatsapp_status,
    validate_phone_number,
    verify_whatsapp_credentials,
)
from ..services.supabase_auth_service import (
    resolve_supabase_key,
    resolve_supabase_url,
    supabase_auth_configured,
    verify_supabase_access_token,
)
from ..utils import (
    ALLOWED_ATTENDANCE_STATUSES,
    ALLOWED_INVOICE_STATUSES,
    build_growth_series,
    clean_text,
    json_error,
    normalize_email,
    parse_amount,
    validate_email,
    validate_password,
)


api_bp = Blueprint("api", __name__, url_prefix="/api")

TRIAL_DURATION_DAYS = max(1, int(os.getenv("TRIAL_DURATION_DAYS", "7")))
SUBSCRIPTION_BASE_PRICE_INR = max(1, int(os.getenv("SUBSCRIPTION_BASE_PRICE_INR", "200")))
FREE_PLAN_CODE = "free"
TRIAL_PLAN_CODE = "free-trial"
PRO_PLAN_CODE = "pro-200"
LEGACY_PRO_PLAN_CODES = {"starter-99", "pro-99"}
PREMIUM_PLAN_CODES = {PRO_PLAN_CODE, *LEGACY_PRO_PLAN_CODES}
PROMO_CODE_DEFINITIONS = {
    "abinav_9009": {
        "code": "Abinav_9009",
        "discount_type": "percentage",
        "discount_value": 100,
        "description": "100% discount on first Pro subscription purchase",
    }
}
PLAN_DEFINITIONS = {
    FREE_PLAN_CODE: {"label": "Free Plan", "price": "Rs 0/month", "badge": "Free"},
    TRIAL_PLAN_CODE: {
        "label": f"{TRIAL_DURATION_DAYS}-day Free Trial",
        "price": "Rs 0 for 7 days",
        "badge": "Trial",
    },
    PRO_PLAN_CODE: {"label": "Pro Plan", "price": f"Rs {SUBSCRIPTION_BASE_PRICE_INR}/month", "badge": "Pro"},
}
PLAN_DEFINITIONS["starter-99"] = PLAN_DEFINITIONS[PRO_PLAN_CODE]
PLAN_DEFINITIONS["pro-99"] = PLAN_DEFINITIONS[PRO_PLAN_CODE]
WHATSAPP_ENABLED_PLANS = {TRIAL_PLAN_CODE, *PREMIUM_PLAN_CODES}
WHATSAPP_MESSAGE_TYPES = {"text", "promotional", "invoice", "reminder", "welcome"}
AI_PROVIDER_SERVICE = "groq"
AI_LEGACY_PROVIDER_SERVICE = "openai"
SUPPORTED_API_KEY_SERVICES = {
    "groq": "Groq AI API Key",
    "openai": "OpenAI API Key (legacy)",
    "whatsapp": "WhatsApp API Key",
    "payment_gateway": "Payment Gateway Key",
    "email_service": "Email Service API Key",
}
SETTINGS_DEFAULTS = {
    "account.phone_number": "",
    "account.business_name": "",
    "notifications.email_enabled": "true",
    "notifications.whatsapp_enabled": "true",
    "notifications.sms_enabled": "false",
    "preferences.theme": "dark",
    "preferences.language": "english",
    "security.two_factor_enabled": "false",
    "security.session_version": "1",
}


@jwt.unauthorized_loader
def unauthorized_callback(_message):
    return jsonify({"success": False, "message": "Authentication is required."}), 401


@jwt.invalid_token_loader
def invalid_token_callback(_message):
    return jsonify({"success": False, "message": "Invalid token."}), 401


@jwt.expired_token_loader
def expired_token_callback(_header, _payload):
    return jsonify({"success": False, "message": "Session expired. Please log in again."}), 401


@jwt.revoked_token_loader
def revoked_token_callback(_header, _payload):
    return jsonify({"success": False, "message": "Session expired. Please log in again."}), 401


@jwt.token_in_blocklist_loader
def token_in_blocklist(_header, payload):
    identity = payload.get("sub")
    try:
        user = db.session.get(User, int(identity))
    except (TypeError, ValueError):
        return True

    if not user:
        return True

    try:
        token_version = int(payload.get("session_version", 1))
    except (TypeError, ValueError):
        token_version = 1
    return token_version != get_session_version(user)


def get_current_user():
    identity = get_jwt_identity()
    try:
        return db.session.get(User, int(identity))
    except (TypeError, ValueError):
        return None


def get_setting_entry(user, key):
    return Setting.query.filter_by(user_id=user.id, key=key).first()


def get_setting_value(user, key, default=""):
    entry = get_setting_entry(user, key)
    if entry is None or entry.value is None:
        return SETTINGS_DEFAULTS.get(key, default)
    return entry.value


def get_setting_bool(user, key, default=False):
    fallback = "true" if default else "false"
    return str(get_setting_value(user, key, fallback)).strip().lower() in {"1", "true", "yes", "on"}


def get_setting_map(user):
    rows = Setting.query.filter_by(user_id=user.id).all()
    values = {key: default for key, default in SETTINGS_DEFAULTS.items()}
    values.update({row.key: row.value or "" for row in rows})
    return values


def upsert_setting_value(user, key, value):
    entry = get_setting_entry(user, key)
    if entry:
        entry.value = value
        return entry
    entry = Setting(user_id=user.id, key=key, value=value)
    db.session.add(entry)
    return entry


def get_session_version(user):
    raw_value = get_setting_value(user, "security.session_version", "1")
    try:
        return max(1, int(raw_value))
    except (TypeError, ValueError):
        return 1


def bump_session_version(user):
    next_version = get_session_version(user) + 1
    upsert_setting_value(user, "security.session_version", str(next_version))
    return next_version


def create_user_token(user):
    return create_access_token(
        identity=str(user.id),
        additional_claims={"session_version": get_session_version(user)},
    )


def find_user_api_key(user, service_name):
    return ApiKey.query.filter_by(user_id=user.id, service_name=service_name).first()


def upsert_user_api_key(user, service_name, raw_key, status="saved"):
    record = find_user_api_key(user, service_name)
    if record:
        record.encrypted_key = encrypt_secret(raw_key)
        record.status = status
        return record
    record = ApiKey(
        user_id=user.id,
        service_name=service_name,
        encrypted_key=encrypt_secret(raw_key),
        status=status,
    )
    db.session.add(record)
    return record


def delete_user_api_key(user, service_name):
    record = find_user_api_key(user, service_name)
    if record:
        db.session.delete(record)


def resolve_user_api_key(user, service_name):
    if service_name == "whatsapp" and user.whatsapp_setting:
        return decrypt_secret(user.whatsapp_setting.api_key_encrypted)
    record = find_user_api_key(user, service_name)
    return decrypt_secret(record.encrypted_key) if record else ""


def resolve_ai_api_key(user):
    stored_key = resolve_user_api_key(user, AI_PROVIDER_SERVICE)
    if stored_key:
        return stored_key

    legacy_key = resolve_user_api_key(user, AI_LEGACY_PROVIDER_SERVICE)
    if legacy_key:
        return legacy_key

    return os.getenv("GROQ_API_KEY") or os.getenv("OPENAI_API_KEY") or ""


def user_can_manage_api_settings(user):
    return getattr(user, "role", "owner") in {"owner", "admin"}


def sync_whatsapp_api_key_record(user, access_token):
    if access_token:
        upsert_user_api_key(user, "whatsapp", access_token)
    else:
        delete_user_api_key(user, "whatsapp")


def normalize_subscription_plan(plan):
    normalized = (plan or "").strip().lower()
    if normalized in LEGACY_PRO_PLAN_CODES or normalized == "pro":
        return PRO_PLAN_CODE
    if normalized in {"trial"}:
        return TRIAL_PLAN_CODE
    if normalized in {"free plan", "free-plan"}:
        return FREE_PLAN_CODE
    return normalized or FREE_PLAN_CODE


def resolve_promo_definition(raw_code):
    normalized = (raw_code or "").strip().lower()
    return PROMO_CODE_DEFINITIONS.get(normalized)


def promo_code_used_by_user(user, promo_code):
    normalized = (promo_code or "").strip().lower()
    if not normalized:
        return False
    rows = Subscription.query.filter_by(user_id=user.id).all()
    return any((row.promo_code_used or "").strip().lower() == normalized for row in rows)


def build_subscription_state(subscription):
    today = date.today()
    if not subscription:
        return {
            "plan_code": FREE_PLAN_CODE,
            "stored_plan": FREE_PLAN_CODE,
            "label": PLAN_DEFINITIONS[FREE_PLAN_CODE]["label"],
            "price_label": PLAN_DEFINITIONS[FREE_PLAN_CODE]["price"],
            "badge": PLAN_DEFINITIONS[FREE_PLAN_CODE]["badge"],
            "stored_status": "inactive",
            "effective_status": "inactive",
            "trial_start_date": None,
            "trial_end_date": None,
            "trial_days_left": None,
            "trial_active": False,
            "trial_expired": False,
            "premium_active": False,
            "payment_pending": False,
            "upgrade_required": False,
            "next_renewal_on": None,
            "amount_due": 0,
            "promo_code_used": "",
            "promo_discount_percent": 0,
            "promo_discount_amount": 0,
            "payment_provider": "",
            "payment_status": "pending",
            "payment_reference": "",
            "renewed_on": None,
            "activated_at": None,
            "upgrade_prompt_shown_at": None,
        }

    stored_plan = normalize_subscription_plan(subscription.plan)
    plan_info = PLAN_DEFINITIONS.get(subscription.plan, PLAN_DEFINITIONS.get(stored_plan, PLAN_DEFINITIONS[FREE_PLAN_CODE]))
    stored_status = (subscription.status or "active").strip().lower()

    trial_start_date = subscription.trial_start_date
    if stored_plan == TRIAL_PLAN_CODE and not trial_start_date and subscription.created_at:
        trial_start_date = subscription.created_at.date()
    trial_end_date = subscription.trial_end_date
    if stored_plan == TRIAL_PLAN_CODE and not trial_end_date and trial_start_date:
        trial_days = current_app.config.get("TRIAL_DURATION_DAYS", TRIAL_DURATION_DAYS)
        trial_end_date = trial_start_date + timedelta(days=trial_days)

    trial_days_left = None
    if stored_plan == TRIAL_PLAN_CODE and trial_end_date:
        trial_days_left = max(0, (trial_end_date - today).days)

    trial_active = stored_plan == TRIAL_PLAN_CODE and bool(trial_end_date and trial_end_date >= today) and stored_status not in {"cancelled"}
    trial_expired = stored_plan == TRIAL_PLAN_CODE and bool(trial_end_date and trial_end_date < today)
    premium_active = stored_plan == PRO_PLAN_CODE and stored_status not in {"cancelled", "expired", "failed"}
    payment_pending = (subscription.payment_status or "").lower() == "pending" and bool(subscription.payment_reference)
    upgrade_required = trial_expired or payment_pending

    if stored_plan == TRIAL_PLAN_CODE:
        effective_status = "trial" if trial_active else "expired"
    elif stored_plan == PRO_PLAN_CODE:
        effective_status = "active" if premium_active else stored_status
    else:
        effective_status = stored_status or "active"

    next_renewal_on = None
    if stored_plan == PRO_PLAN_CODE and subscription.renewed_on:
        next_renewal_on = subscription.renewed_on + timedelta(days=30)

    amount_due = int(subscription.amount_due or 0)
    if stored_plan == PRO_PLAN_CODE and amount_due <= 0 and not (subscription.promo_code_used or "").strip():
        amount_due = SUBSCRIPTION_BASE_PRICE_INR

    return {
        "plan_code": stored_plan,
        "stored_plan": subscription.plan,
        "label": plan_info["label"],
        "price_label": plan_info["price"],
        "badge": plan_info["badge"],
        "stored_status": stored_status,
        "effective_status": effective_status,
        "trial_start_date": trial_start_date,
        "trial_end_date": trial_end_date,
        "trial_days_left": trial_days_left,
        "trial_active": trial_active,
        "trial_expired": trial_expired,
        "premium_active": premium_active,
        "payment_pending": payment_pending,
        "upgrade_required": upgrade_required,
        "next_renewal_on": next_renewal_on,
        "amount_due": amount_due,
        "promo_code_used": (subscription.promo_code_used or "").strip(),
        "promo_discount_percent": int(subscription.promo_discount_percent or 0),
        "promo_discount_amount": int(subscription.promo_discount_amount or 0),
        "payment_provider": (subscription.payment_provider or "").strip(),
        "payment_status": (subscription.payment_status or "pending").strip().lower(),
        "payment_reference": (subscription.payment_reference or "").strip(),
        "renewed_on": subscription.renewed_on,
        "activated_at": subscription.activated_at,
        "upgrade_prompt_shown_at": subscription.upgrade_prompt_shown_at,
    }


def build_subscription_access(subscription_state):
    live_access = bool(subscription_state["trial_active"] or subscription_state["premium_active"])
    return {
        "live_whatsapp_access": live_access,
        "automation_access": live_access,
        "ai_access": live_access,
        "export_access": live_access,
        "upgrade_required": bool(subscription_state["upgrade_required"]),
        "trial_active": bool(subscription_state["trial_active"]),
        "trial_expired": bool(subscription_state["trial_expired"]),
        "premium_active": bool(subscription_state["premium_active"]),
    }


def build_payment_gateway_payload():
    razorpay_available = bool(
        current_app.config.get("RAZORPAY_KEY_ID") and current_app.config.get("RAZORPAY_KEY_SECRET")
    )
    stripe_available = bool(current_app.config.get("STRIPE_SECRET_KEY"))
    if razorpay_available:
        default_provider = "razorpay"
    elif stripe_available:
        default_provider = "stripe"
    else:
        default_provider = "demo"
    return {
        "razorpay_available": razorpay_available,
        "stripe_available": stripe_available,
        "demo_available": bool(current_app.config.get("SUBSCRIPTION_DEMO_PAYMENTS", True)),
        "default_provider": default_provider,
    }


def build_subscription_quote(user, subscription=None, promo_code=None):
    subscription = subscription or get_current_subscription(user)
    subscription_state = build_subscription_state(subscription) if subscription else build_subscription_state(None)
    candidate_code = promo_code or subscription_state["promo_code_used"]
    promo_definition = resolve_promo_definition(candidate_code)

    stored_code = (subscription_state["promo_code_used"] or "").strip().lower()
    candidate_normalized = (candidate_code or "").strip().lower()
    promo_valid = bool(
        promo_definition
        and (
            not promo_code_used_by_user(user, promo_definition["code"])
            or candidate_normalized == stored_code
        )
    )
    discount_percent = promo_definition["discount_value"] if promo_valid else 0
    discount_amount = (SUBSCRIPTION_BASE_PRICE_INR * discount_percent) // 100
    amount_due = max(0, SUBSCRIPTION_BASE_PRICE_INR - discount_amount)

    return {
        "base_amount": SUBSCRIPTION_BASE_PRICE_INR,
        "currency": "INR",
        "promo_code": promo_definition["code"] if promo_valid else (candidate_code or ""),
        "promo_description": promo_definition["description"] if promo_valid else "",
        "promo_valid": promo_valid,
        "promo_used": bool(subscription_state["promo_code_used"]),
        "discount_percent": discount_percent,
        "discount_amount": discount_amount,
        "amount_due": amount_due,
        "payment_status": subscription_state["payment_status"],
        "payment_provider": subscription_state["payment_provider"],
        "payment_reference": subscription_state["payment_reference"],
        "payment_pending": subscription_state["payment_pending"],
        "demo_available": bool(current_app.config.get("SUBSCRIPTION_DEMO_PAYMENTS", True)),
    }


def build_subscription_notice(subscription_state):
    if subscription_state["payment_pending"]:
        return "Payment link pending. Complete payment to activate Pro."
    if subscription_state["promo_code_used"] and subscription_state["amount_due"] == 0 and not subscription_state["premium_active"]:
        return "Promo applied. Pro can be activated for free."
    if subscription_state["trial_expired"]:
        return f"Trial expired. Upgrade to Pro for Rs {SUBSCRIPTION_BASE_PRICE_INR}/month."
    if subscription_state["trial_active"] and subscription_state["trial_days_left"] is not None:
        if subscription_state["trial_days_left"] <= 2:
            return f"Your trial ends in {subscription_state['trial_days_left']} day(s). Upgrade now to keep live features unlocked."
        return f"Trial active with {subscription_state['trial_days_left']} day(s) left."
    if subscription_state["premium_active"]:
        if subscription_state["next_renewal_on"]:
            return f"Pro active. Next renewal on {subscription_state['next_renewal_on'].isoformat()}."
        return "Pro active."
    return "Free plan active."


def create_subscription_record(
    user,
    plan,
    status,
    *,
    trial_start_date=None,
    trial_end_date=None,
    promo_code_used="",
    promo_discount_percent=0,
    promo_discount_amount=0,
    amount_due=0,
    payment_provider=None,
    payment_status="pending",
    payment_reference=None,
    activated_at=None,
    upgrade_prompt_shown_at=None,
    renewed_on=None,
):
    subscription = Subscription(
        user_id=user.id,
        plan=plan,
        status=status,
        renewed_on=renewed_on or date.today(),
        trial_start_date=trial_start_date,
        trial_end_date=trial_end_date,
        promo_code_used=promo_code_used or None,
        promo_discount_percent=promo_discount_percent,
        promo_discount_amount=promo_discount_amount,
        amount_due=amount_due,
        payment_provider=payment_provider,
        payment_status=payment_status,
        payment_reference=payment_reference,
        activated_at=activated_at,
        upgrade_prompt_shown_at=upgrade_prompt_shown_at,
    )
    db.session.add(subscription)
    return subscription


def create_trial_subscription(user):
    today = date.today()
    return create_subscription_record(
        user,
        TRIAL_PLAN_CODE,
        "trial",
        trial_start_date=today,
        trial_end_date=today + timedelta(days=current_app.config.get("TRIAL_DURATION_DAYS", TRIAL_DURATION_DAYS)),
        amount_due=0,
        payment_status="not_required",
        payment_provider="trial",
        activated_at=datetime.utcnow(),
    )


def activate_paid_subscription(
    user,
    *,
    source_subscription=None,
    payment_provider="demo",
    payment_status="paid",
    payment_reference=None,
    promo_code_used="",
    promo_discount_percent=0,
    promo_discount_amount=0,
    amount_due=None,
):
    source_subscription = source_subscription or get_current_subscription(user)
    trial_start_date = source_subscription.trial_start_date if source_subscription else date.today()
    if not trial_start_date and source_subscription and source_subscription.created_at:
        trial_start_date = source_subscription.created_at.date()
    trial_end_date = source_subscription.trial_end_date if source_subscription else None
    if not trial_end_date and trial_start_date:
        trial_end_date = trial_start_date + timedelta(days=current_app.config.get("TRIAL_DURATION_DAYS", TRIAL_DURATION_DAYS))

    return create_subscription_record(
        user,
        PRO_PLAN_CODE,
        "active",
        trial_start_date=trial_start_date,
        trial_end_date=trial_end_date,
        promo_code_used=promo_code_used or (source_subscription.promo_code_used if source_subscription else ""),
        promo_discount_percent=promo_discount_percent,
        promo_discount_amount=promo_discount_amount,
        amount_due=amount_due if amount_due is not None else max(0, SUBSCRIPTION_BASE_PRICE_INR - promo_discount_amount),
        payment_provider=payment_provider,
        payment_status=payment_status,
        payment_reference=payment_reference,
        activated_at=datetime.utcnow(),
        renewed_on=date.today(),
    )


def update_subscription_promo(subscription, promo_code_used, discount_percent, discount_amount, amount_due):
    subscription.promo_code_used = promo_code_used or None
    subscription.promo_discount_percent = discount_percent
    subscription.promo_discount_amount = discount_amount
    subscription.amount_due = amount_due
    if amount_due > 0:
        subscription.payment_status = "pending"


def create_razorpay_payment_link(user, subscription_state, quote):
    key_id = current_app.config.get("RAZORPAY_KEY_ID") or ""
    key_secret = current_app.config.get("RAZORPAY_KEY_SECRET") or ""
    if not key_id or not key_secret:
        raise ValueError("Razorpay is not configured.")
    if int(quote["amount_due"]) <= 0:
        raise ValueError("Razorpay checkout is not required for a free promo activation.")

    payment_reference = f"growflow-{user.id}-{secrets.token_hex(6)}"
    payload = {
        "amount": int(quote["amount_due"]) * 100,
        "currency": "INR",
        "description": f"GrowFlow AI Pro subscription for {user.name}",
        "reference_id": payment_reference[:40],
        "customer": {
            "name": user.name,
            "email": user.email,
        },
        "expire_by": int((datetime.utcnow() + timedelta(days=7)).timestamp()),
        "reminder_enable": True,
        "callback_url": url_for("pages.subscription_page", _external=True),
        "callback_method": "get",
        "notes": {
            "plan_code": PRO_PLAN_CODE,
            "user_id": str(user.id),
            "promo_code": quote["promo_code"] or "",
            "discount_percent": str(quote["discount_percent"]),
        },
    }

    response = requests.post(
        "https://api.razorpay.com/v1/payment_links",
        auth=(key_id, key_secret),
        json=payload,
        timeout=current_app.config.get("GROQ_TIMEOUT_SECONDS", 25),
    )
    try:
        response_data = response.json()
    except ValueError:
        response_data = {}
    if not response.ok:
        raise ValueError(
            response_data.get("error", {}).get("description")
            or response_data.get("description")
            or "Unable to create Razorpay payment link."
        )
    data = response_data
    return {
        "provider": "razorpay",
        "payment_link_id": data.get("id"),
        "short_url": data.get("short_url") or "",
        "status": data.get("status", "issued"),
        "reference_id": data.get("reference_id") or payment_reference,
        "amount": data.get("amount") or int(quote["amount_due"]) * 100,
        "currency": data.get("currency") or "INR",
    }


def fetch_razorpay_payment_link(payment_link_id):
    key_id = current_app.config.get("RAZORPAY_KEY_ID") or ""
    key_secret = current_app.config.get("RAZORPAY_KEY_SECRET") or ""
    if not key_id or not key_secret:
        raise ValueError("Razorpay is not configured.")

    response = requests.get(
        f"https://api.razorpay.com/v1/payment_links/{payment_link_id}",
        auth=(key_id, key_secret),
        timeout=current_app.config.get("GROQ_TIMEOUT_SECONDS", 25),
    )
    try:
        response_data = response.json()
    except ValueError:
        response_data = {}
    if not response.ok:
        raise ValueError(
            response_data.get("error", {}).get("description")
            or response_data.get("description")
            or "Unable to fetch Razorpay payment link."
        )
    return response_data


def json_upgrade_required(user, feature_name, message=None, quote=None):
    payload = build_subscription_payload(user)
    response_payload = {
        "success": False,
        "message": message or "Upgrade to Pro to continue.",
        "upgrade_required": True,
        "feature": feature_name,
        "subscription": payload.get("current"),
        "access": payload.get("access"),
        "quote": quote or payload.get("quote"),
        "payment_gateways": payload.get("payment_gateways"),
        "notice": payload.get("notice"),
    }
    return jsonify(response_payload), 403


def build_account_payload(user):
    return {
        "name": user.name,
        "email": user.email,
        "phone_number": get_setting_value(user, "account.phone_number", ""),
        "business_name": get_setting_value(user, "account.business_name", ""),
    }


def build_auth_payload(user):
    auth_provider = getattr(user, "auth_provider", "local") or "local"
    return {
        "jwt_enabled": True,
        "logged_in": True,
        "auth_provider": auth_provider,
        "provider_label": "Supabase Auth" if auth_provider == "supabase" else "Local Auth",
        "login_method": "Supabase email/password" if auth_provider == "supabase" else "Local email/password",
        "password_reset_enabled": supabase_auth_configured(),
        "google_login_enabled": False,
        "supabase_enabled": supabase_auth_configured(),
        "supabase_url": resolve_supabase_url(),
    }


def extract_supabase_identity(supabase_user):
    if not isinstance(supabase_user, dict):
        raise ValueError("Supabase session payload is invalid.")

    supabase_uid = (supabase_user.get("id") or "").strip()
    email = normalize_email((supabase_user.get("email") or "").strip())
    metadata = supabase_user.get("user_metadata") or {}
    name = (
        metadata.get("full_name")
        or metadata.get("name")
        or metadata.get("display_name")
        or metadata.get("username")
        or supabase_user.get("phone")
        or email.split("@")[0]
        or "GrowFlow User"
    )

    if not supabase_uid:
        raise ValueError("Supabase user id is missing.")
    if not email:
        raise ValueError("Supabase user email is missing.")

    return {
        "supabase_uid": supabase_uid,
        "email": email,
        "name": clean_text(name, "Supabase name", max_length=120),
    }


def upsert_supabase_user(supabase_user):
    identity = extract_supabase_identity(supabase_user)
    user = User.query.filter_by(supabase_uid=identity["supabase_uid"]).first()

    if not user:
        user = User.query.filter_by(email=identity["email"]).first()

    if user:
        user.name = identity["name"] or user.name
        user.email = identity["email"]
        user.supabase_uid = identity["supabase_uid"]
        user.auth_provider = "supabase"
        if not user.password_hash:
            user.set_password(secrets.token_urlsafe(32))
    else:
        user = User(
            name=identity["name"],
            email=identity["email"],
            role="owner",
            auth_provider="supabase",
            supabase_uid=identity["supabase_uid"],
        )
        user.set_password(secrets.token_urlsafe(32))
        db.session.add(user)
        db.session.flush()
        create_trial_subscription(user)

    if not get_current_subscription(user):
        create_trial_subscription(user)

    return user


def build_api_key_payload(user):
    rows = []
    for service_name, label in SUPPORTED_API_KEY_SERVICES.items():
        raw_key = resolve_user_api_key(user, service_name)
        env_key = ""
        if service_name == "groq":
            env_key = os.getenv("GROQ_API_KEY") or current_app.config.get("GROQ_API_KEY") or ""
        elif service_name == "openai":
            env_key = os.getenv("OPENAI_API_KEY") or current_app.config.get("OPENAI_API_KEY") or ""
        active_key = raw_key or env_key
        if service_name == "whatsapp":
            record = user.whatsapp_setting
            status = record.status if record else "not_connected"
        else:
            record = find_user_api_key(user, service_name)
            if record and record.status:
                status = record.status
            elif env_key:
                status = "environment"
            else:
                status = "saved" if active_key else "not_saved"

        rows.append(
            {
                "service_name": service_name,
                "label": label,
                "masked_key": mask_key(active_key),
                "has_key": bool(active_key),
                "status": status,
                "environment_available": (
                    service_name == "groq" and bool(os.getenv("GROQ_API_KEY") or current_app.config.get("GROQ_API_KEY"))
                )
                or (
                    service_name == "openai" and bool(os.getenv("OPENAI_API_KEY") or current_app.config.get("OPENAI_API_KEY"))
                ),
            }
        )
    return rows


def build_ai_management_payload(user):
    record = find_user_api_key(user, AI_PROVIDER_SERVICE)
    user_key = decrypt_secret(record.encrypted_key) if record and record.encrypted_key else ""
    env_key = os.getenv("GROQ_API_KEY") or current_app.config.get("GROQ_API_KEY") or ""
    legacy_key = resolve_user_api_key(user, AI_LEGACY_PROVIDER_SERVICE)
    legacy_env_key = os.getenv("OPENAI_API_KEY") or current_app.config.get("OPENAI_API_KEY") or ""
    active_key = user_key or env_key or legacy_key or legacy_env_key or ""
    connection_status = "not_configured"
    if record and record.encrypted_key:
        connection_status = record.status or "saved"
    elif env_key:
        connection_status = "environment"
    elif legacy_key or legacy_env_key:
        connection_status = "legacy"

    return {
        "provider": "Groq",
        "service_name": AI_PROVIDER_SERVICE,
        "label": "Groq AI Provider",
        "model": os.getenv("GROQ_MODEL") or current_app.config.get("GROQ_MODEL", "llama-3.3-70b-versatile"),
        "base_url": os.getenv("GROQ_BASE_URL")
        or current_app.config.get("GROQ_BASE_URL", "https://api.groq.com/openai/v1"),
        "status": connection_status,
        "source": "database"
        if user_key
        else "environment"
        if env_key
        else "legacy"
        if legacy_key
        else "legacy-env"
        if legacy_env_key
        else "none",
        "masked_key": mask_key(active_key),
        "has_user_key": bool(user_key),
        "has_environment_key": bool(env_key),
        "has_legacy_key": bool(legacy_key or legacy_env_key),
        "configured": bool(active_key),
        "editable": True,
    }


def build_notification_payload(user):
    return {
        "email_notifications": get_setting_bool(user, "notifications.email_enabled", True),
        "whatsapp_notifications": get_setting_bool(user, "notifications.whatsapp_enabled", True),
        "sms_alerts": get_setting_bool(user, "notifications.sms_enabled", False),
        "theme": get_setting_value(user, "preferences.theme", "dark"),
        "language": get_setting_value(user, "preferences.language", "english"),
    }


def build_security_payload(user):
    return {
        "two_factor_enabled": get_setting_bool(user, "security.two_factor_enabled", False),
        "session_version": get_session_version(user),
        "api_key_encryption": True,
        "logout_all_supported": True,
    }


def build_subscription_payload(user, track_prompt=False):
    current_subscription = get_current_subscription(user)
    if track_prompt and current_subscription:
        state = build_subscription_state(current_subscription)
        if state["upgrade_required"] and not current_subscription.upgrade_prompt_shown_at:
            current_subscription.upgrade_prompt_shown_at = datetime.utcnow()
            db.session.commit()
            current_subscription = get_current_subscription(user)

    current_state = build_subscription_state(current_subscription) if current_subscription else build_subscription_state(None)
    history = [
        serialize_subscription(row)
        for row in Subscription.query.filter_by(user_id=user.id)
        .order_by(Subscription.created_at.desc())
        .limit(12)
        .all()
    ]
    quote = build_subscription_quote(user, current_subscription)
    access = build_subscription_access(current_state)
    payment_gateways = build_payment_gateway_payload()
    notice = build_subscription_notice(current_state)
    plans = [
        {"code": FREE_PLAN_CODE, **PLAN_DEFINITIONS[FREE_PLAN_CODE]},
        {"code": TRIAL_PLAN_CODE, **PLAN_DEFINITIONS[TRIAL_PLAN_CODE]},
        {"code": PRO_PLAN_CODE, **PLAN_DEFINITIONS[PRO_PLAN_CODE]},
    ]
    return {
        "current": serialize_subscription(current_subscription),
        "quote": quote,
        "access": access,
        "notice": notice,
        "payment_gateways": payment_gateways,
        "upgrade_required": bool(current_state["upgrade_required"]),
        "plans": plans,
        "billing_history": history,
    }


def build_data_summary(user):
    employee_ids = [row.id for row in Employee.query.filter_by(user_id=user.id).all()]
    customer_ids = [row.id for row in Customer.query.filter_by(user_id=user.id).all()]
    invoice_count = Invoice.query.filter(Invoice.customer_id.in_(customer_ids)).count() if customer_ids else 0
    return {
        "customers": len(customer_ids),
        "employees": len(employee_ids),
        "invoices": invoice_count,
        "templates": WhatsAppTemplate.query.filter_by(user_id=user.id).count(),
        "whatsapp_messages": WhatsAppMessage.query.filter_by(user_id=user.id).count(),
        "marketing_logs": MarketingLog.query.filter_by(user_id=user.id).count(),
        "api_keys": ApiKey.query.filter_by(user_id=user.id).count(),
        "backup_download_url": "/api/backup/export",
        "csv_export_url": "/api/settings/data?format=csv",
    }


def mask_key(raw_value):
    if not raw_value:
        return ""
    visible = raw_value[-4:] if len(raw_value) > 4 else raw_value
    return f"{'*' * max(4, len(raw_value) - len(visible))}{visible}"


def build_csv_text(fieldnames, rows):
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def build_csv_export_bundle(user):
    customers = [row.to_dict() for row in Customer.query.filter_by(user_id=user.id).order_by(Customer.id.asc()).all()]
    employees = [row.to_dict() for row in Employee.query.filter_by(user_id=user.id).order_by(Employee.id.asc()).all()]
    customer_ids = [row["id"] for row in customers]
    invoices = [
        row.to_dict()
        for row in Invoice.query.filter(Invoice.customer_id.in_(customer_ids)).order_by(Invoice.id.asc()).all()
    ] if customer_ids else []
    messages = [
        row.to_dict()
        for row in WhatsAppMessage.query.filter_by(user_id=user.id).order_by(WhatsAppMessage.id.asc()).all()
    ]
    templates = [
        row.to_dict()
        for row in WhatsAppTemplate.query.filter_by(user_id=user.id).order_by(WhatsAppTemplate.id.asc()).all()
    ]

    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zipped:
        zipped.writestr(
            "customers.csv",
            build_csv_text(["id", "name", "phone", "email"], customers),
        )
        zipped.writestr(
            "employees.csv",
            build_csv_text(["id", "name", "role", "latest_status"], employees),
        )
        zipped.writestr(
            "invoices.csv",
            build_csv_text(["id", "customer_name", "amount", "status", "issued_on"], invoices),
        )
        zipped.writestr(
            "whatsapp_messages.csv",
            build_csv_text(
                ["id", "customer_name", "recipient_phone", "template_name", "message_type", "mode", "status", "scheduled_for", "sent_at", "message"],
                messages,
            ),
        )
        zipped.writestr(
            "templates.csv",
            build_csv_text(["id", "template_name", "category", "content"], templates),
        )
    archive.seek(0)
    return archive.getvalue()


def delete_user_business_data(user, clear_preferences=False):
    employee_ids = [row.id for row in Employee.query.filter_by(user_id=user.id).all()]
    customer_ids = [row.id for row in Customer.query.filter_by(user_id=user.id).all()]

    if employee_ids:
        Attendance.query.filter(Attendance.employee_id.in_(employee_ids)).delete(
            synchronize_session=False
        )
    WhatsAppMessage.query.filter_by(user_id=user.id).delete(synchronize_session=False)
    MarketingLog.query.filter_by(user_id=user.id).delete(synchronize_session=False)
    WhatsAppTemplate.query.filter_by(user_id=user.id).delete(synchronize_session=False)
    if customer_ids:
        Invoice.query.filter(Invoice.customer_id.in_(customer_ids)).delete(synchronize_session=False)
    Customer.query.filter_by(user_id=user.id).delete(synchronize_session=False)
    Employee.query.filter_by(user_id=user.id).delete(synchronize_session=False)
    WhatsAppSetting.query.filter_by(user_id=user.id).delete(synchronize_session=False)
    ApiKey.query.filter_by(user_id=user.id).delete(synchronize_session=False)

    if clear_preferences:
        Setting.query.filter(
            Setting.user_id == user.id,
            Setting.key != "security.session_version",
        ).delete(synchronize_session=False)


def restore_backup_payload(user, backup_payload):
    delete_user_business_data(user, clear_preferences=True)
    db.session.flush()

    customer_map = {}
    employee_map = {}
    for item in backup_payload.get("customers", []):
        customer = Customer(
            user_id=user.id,
            name=(item.get("name") or "Customer").strip()[:120],
            phone=(item.get("phone") or "").strip()[:25],
            email=(item.get("email") or "").strip()[:255] or None,
        )
        if not customer.phone or not validate_phone_number(customer.phone):
            continue
        db.session.add(customer)
        db.session.flush()
        customer_map[item.get("id")] = customer.id

    for item in backup_payload.get("employees", []):
        employee = Employee(
            user_id=user.id,
            name=(item.get("name") or "Employee").strip()[:120],
            role=(item.get("role") or "Staff").strip()[:120],
        )
        db.session.add(employee)
        db.session.flush()
        employee_map[item.get("id")] = employee.id

    for item in backup_payload.get("invoices", []):
        mapped_customer_id = customer_map.get(item.get("customer_id"))
        if not mapped_customer_id:
            continue
        try:
            amount = parse_amount(item.get("amount"))
        except ValueError:
            continue
        status = (item.get("status") or "pending").strip().lower()
        if status not in ALLOWED_INVOICE_STATUSES:
            status = "pending"
        issued_on = item.get("issued_on") or date.today().isoformat()
        try:
            issued_date = date.fromisoformat(issued_on)
        except ValueError:
            issued_date = date.today()
        db.session.add(
            Invoice(
                customer_id=mapped_customer_id,
                amount=amount,
                status=status,
                issued_on=issued_date,
            )
        )

    for item in backup_payload.get("templates", []):
        template_name = (item.get("template_name") or "").strip()[:120]
        content = (item.get("content") or "").strip()[:1200]
        if not template_name or not content:
            continue
        db.session.add(
            WhatsAppTemplate(
                user_id=user.id,
                template_name=template_name,
                category=(item.get("category") or "custom").strip()[:60] or "custom",
                content=content,
            )
        )

    for item in backup_payload.get("marketing_logs", []):
        message = (item.get("message") or "").strip()
        if not message:
            continue
        db.session.add(
            MarketingLog(
                user_id=user.id,
                message=message,
                audience=(item.get("audience") or "customers").strip()[:120] or "customers",
                delivery_status=(item.get("delivery_status") or "queued").strip()[:20] or "queued",
            )
        )

    for item in backup_payload.get("whatsapp_messages", []):
        message = (item.get("message") or "").strip()
        phone = (item.get("recipient_phone") or "").strip()
        if not message or not phone:
            continue
        db.session.add(
            WhatsAppMessage(
                user_id=user.id,
                customer_id=customer_map.get(item.get("customer_id")),
                recipient_phone=phone[:25],
                message=message,
                template_name=(item.get("template_name") or "").strip()[:120] or None,
                message_type=(item.get("message_type") or "text").strip()[:40] or "text",
                mode=(item.get("mode") or "demo").strip()[:20] or "demo",
                status=(item.get("status") or "queued").strip()[:20] or "queued",
                external_message_id=(item.get("external_message_id") or "").strip()[:255] or None,
                error_message=(item.get("error_message") or "").strip() or None,
            )
        )

    for key, default in SETTINGS_DEFAULTS.items():
        if key == "security.session_version":
            continue
        if key.startswith("notifications.") or key.startswith("preferences.") or key.startswith("account."):
            value = backup_payload.get("settings", {}).get(key, default)
            upsert_setting_value(user, key, value)


def parse_restore_payload(data):
    backup = data.get("backup")
    if isinstance(backup, dict):
        return backup
    if isinstance(backup, str):
        try:
            return json.loads(backup)
        except json.JSONDecodeError:
            raise ValueError("Backup JSON is invalid.") from None
    raise ValueError("Backup payload is required.")


def parse_target_date(raw_value):
    try:
        return date.fromisoformat(raw_value or date.today().isoformat())
    except ValueError:
        raise ValueError("Date must use YYYY-MM-DD format.") from None


def parse_scheduled_datetime(raw_value):
    if not raw_value:
        return None
    try:
        cleaned = str(raw_value).strip().replace("Z", "+00:00")
        scheduled_for = datetime.fromisoformat(cleaned)
    except ValueError:
        raise ValueError("Scheduled time must use ISO datetime format.") from None

    if scheduled_for.tzinfo is not None:
        scheduled_for = scheduled_for.astimezone().replace(tzinfo=None)
    return scheduled_for


def get_current_subscription(user):
    return (
        Subscription.query.filter_by(user_id=user.id)
        .order_by(Subscription.created_at.desc())
        .first()
    )


def serialize_subscription(subscription):
    if not subscription:
        return None

    state = build_subscription_state(subscription)
    return {
        **subscription.to_dict(),
        "plan_code": state["plan_code"],
        "stored_plan": state["stored_plan"],
        "label": state["label"],
        "price_label": state["price_label"],
        "badge": state["badge"],
        "status": state["effective_status"],
        "stored_status": state["stored_status"],
        "trial_start_date": state["trial_start_date"].isoformat() if state["trial_start_date"] else None,
        "trial_end_date": state["trial_end_date"].isoformat() if state["trial_end_date"] else None,
        "trial_days_left": state["trial_days_left"],
        "trial_active": state["trial_active"],
        "trial_expired": state["trial_expired"],
        "premium_active": state["premium_active"],
        "payment_pending": state["payment_pending"],
        "upgrade_required": state["upgrade_required"],
        "next_renewal_on": state["next_renewal_on"].isoformat() if state["next_renewal_on"] else None,
        "amount_due": state["amount_due"],
        "promo_code_used": state["promo_code_used"],
        "promo_discount_percent": state["promo_discount_percent"],
        "promo_discount_amount": state["promo_discount_amount"],
        "payment_provider": state["payment_provider"],
        "payment_status": state["payment_status"],
        "payment_reference": state["payment_reference"],
        "renewed_on": state["renewed_on"].isoformat() if state["renewed_on"] else None,
        "activated_at": state["activated_at"].isoformat() if state["activated_at"] else None,
        "upgrade_prompt_shown_at": (
            state["upgrade_prompt_shown_at"].isoformat() if state["upgrade_prompt_shown_at"] else None
        ),
    }


def user_has_live_whatsapp_access(user):
    subscription = get_current_subscription(user)
    if not subscription:
        return False
    state = build_subscription_state(subscription)
    return bool(state["trial_active"] or state["premium_active"])


def upsert_whatsapp_setting(user):
    setting = user.whatsapp_setting
    if setting:
        return setting
    setting = WhatsAppSetting(user_id=user.id)
    db.session.add(setting)
    return setting


def build_whatsapp_status_response(user):
    setting = user.whatsapp_setting
    effective_config = resolve_whatsapp_credentials(user=user, allow_env_fallback=True)
    credential_source = "none"
    if setting and setting.api_key_encrypted:
        credential_source = "custom"
    elif environment_whatsapp_available():
        credential_source = "environment"
    return {
        "status": serialize_whatsapp_status(setting),
        "connection_state": setting.status if setting else "disconnected",
        "credential_source": credential_source,
        "effective_source": effective_config["source"] if effective_config else "none",
        "environment_fallback": {
            "available": environment_whatsapp_available(),
            "api_version": current_app.config.get("WHATSAPP_API_VERSION"),
        },
        "live_access": user_has_live_whatsapp_access(user),
        "verification_allowed": user_has_live_whatsapp_access(user),
        "messaging_mode": "live" if effective_config and user_has_live_whatsapp_access(user) else "demo",
    }


def build_template_listing(user):
    custom_templates = [
        template.to_dict()
        for template in WhatsAppTemplate.query.filter_by(user_id=user.id)
        .order_by(WhatsAppTemplate.created_at.desc())
        .all()
    ]
    builtin_templates = get_builtin_templates()
    return builtin_templates + custom_templates


def resolve_template_content(user, template_selection, message_content, message_type):
    content = (message_content or "").strip()
    template_name = ""
    template_key = (template_selection or "").strip()

    if template_key.startswith("builtin:"):
        builtin = find_builtin_template(template_key.split(":", 1)[1])
        if not builtin:
            raise ValueError("Built-in template not found.")
        template_name = builtin["template_name"]
        content = content or builtin["content"]
    elif template_key.startswith("custom:"):
        template_id = template_key.split(":", 1)[1]
        template = WhatsAppTemplate.query.filter_by(id=template_id, user_id=user.id).first()
        if not template:
            raise ValueError("Custom template not found.")
        template_name = template.template_name
        content = content or template.content

    final_message = build_message_content(message_type, content)
    return final_message, template_name


def build_recipient_records(user, data):
    send_to = (data.get("send_to") or "").strip().lower()
    customer_ids = data.get("customer_ids") or []
    customer_id = data.get("customer_id")
    phone = (data.get("customer_phone_number") or data.get("phone") or "").strip()

    records = []
    if send_to == "all_customers":
        customers = Customer.query.filter_by(user_id=user.id).order_by(Customer.name.asc()).all()
        records.extend(
            {
                "customer_id": customer.id,
                "customer_name": customer.name,
                "recipient_phone": customer.phone,
            }
            for customer in customers
        )
    elif customer_ids:
        customers = (
            Customer.query.filter(Customer.user_id == user.id, Customer.id.in_(customer_ids))
            .order_by(Customer.name.asc())
            .all()
        )
        records.extend(
            {
                "customer_id": customer.id,
                "customer_name": customer.name,
                "recipient_phone": customer.phone,
            }
            for customer in customers
        )
    elif customer_id:
        customer = Customer.query.filter_by(id=customer_id, user_id=user.id).first()
        if not customer:
            raise ValueError("Customer not found.")
        records.append(
            {
                "customer_id": customer.id,
                "customer_name": customer.name,
                "recipient_phone": customer.phone,
            }
        )
    elif phone:
        records.append(
            {
                "customer_id": None,
                "customer_name": "",
                "recipient_phone": phone,
            }
        )
    else:
        raise ValueError("Select at least one customer or enter a phone number.")

    valid_records = []
    for record in records:
        recipient_phone = (record["recipient_phone"] or "").strip()
        if not validate_phone_number(recipient_phone):
            raise ValueError(f"Invalid phone number: {recipient_phone}")
        valid_records.append({**record, "recipient_phone": recipient_phone})
    return valid_records


def create_whatsapp_message_log(
    *,
    user,
    recipient_phone,
    message,
    message_type,
    mode,
    status,
    customer_id=None,
    template_name="",
    scheduled_for=None,
    sent_at=None,
    external_message_id="",
    error_message="",
):
    return WhatsAppMessage(
        user_id=user.id,
        customer_id=customer_id,
        recipient_phone=recipient_phone,
        message=message,
        template_name=template_name or None,
        message_type=message_type,
        mode=mode,
        status=status,
        external_message_id=external_message_id or None,
        scheduled_for=scheduled_for,
        sent_at=sent_at,
        error_message=error_message or None,
    )


def dispatch_whatsapp_messages(
    *,
    user,
    recipients,
    message,
    message_type,
    template_name="",
    delivery_mode="auto",
    scheduled_for=None,
    allow_env_fallback=True,
):
    results = []
    logs = []
    live_access = user_has_live_whatsapp_access(user)

    for recipient in recipients:
        effective_mode = (delivery_mode or "auto").strip().lower()
        if effective_mode not in {"auto", "demo", "live"}:
            effective_mode = "auto"
        if not live_access and effective_mode != "demo":
            effective_mode = "demo"

        if scheduled_for and scheduled_for > datetime.utcnow():
            log = create_whatsapp_message_log(
                user=user,
                customer_id=recipient["customer_id"],
                recipient_phone=recipient["recipient_phone"],
                message=message,
                message_type=message_type,
                template_name=template_name,
                mode=effective_mode,
                status="scheduled",
                scheduled_for=scheduled_for,
            )
            logs.append(log)
            results.append(
                {
                    "success": True,
                    "recipient": recipient["recipient_phone"],
                    "mode": effective_mode,
                    "scheduled": True,
                    "message": "Message scheduled successfully.",
                }
            )
            continue

        result = send_whatsapp_message(
            recipient=recipient["recipient_phone"],
            message=message,
            user=user,
            allow_env_fallback=allow_env_fallback,
            delivery_mode=effective_mode,
        )
        status = "failed"
        sent_at = None
        external_message_id = ""
        error_message = ""
        if result["success"]:
            status = "demo" if result.get("dry_run") else "sent"
            sent_at = datetime.utcnow()
            external_message_id = result.get("external_message_id", "")
        else:
            error_message = result["message"]

        log = create_whatsapp_message_log(
            user=user,
            customer_id=recipient["customer_id"],
            recipient_phone=recipient["recipient_phone"],
            message=message,
            message_type=message_type,
            template_name=template_name,
            mode=result.get("mode", effective_mode),
            status=status,
            sent_at=sent_at,
            external_message_id=external_message_id,
            error_message=error_message,
        )
        logs.append(log)
        results.append(result)

    if logs:
        db.session.add_all(logs)
        db.session.commit()
    return results, logs


def process_due_scheduled_messages(user):
    due_messages = (
        WhatsAppMessage.query.filter_by(user_id=user.id, status="scheduled")
        .filter(WhatsAppMessage.scheduled_for <= datetime.utcnow())
        .order_by(WhatsAppMessage.scheduled_for.asc(), WhatsAppMessage.id.asc())
        .limit(25)
        .all()
    )
    if not due_messages:
        return 0

    processed = 0
    for message in due_messages:
        effective_mode = message.mode
        if not user_has_live_whatsapp_access(user) and effective_mode != "demo":
            effective_mode = "demo"

        result = send_whatsapp_message(
            recipient=message.recipient_phone,
            message=message.message,
            user=user,
            allow_env_fallback=True,
            delivery_mode=effective_mode,
        )
        if result["success"]:
            message.status = "demo" if result.get("dry_run") else "sent"
            message.sent_at = datetime.utcnow()
            message.external_message_id = result.get("external_message_id") or None
            message.error_message = None
        else:
            message.status = "failed"
            message.error_message = result["message"]
        processed += 1

    db.session.commit()
    return processed


@api_bp.post("/register")
@limiter.limit("10 per minute")
def register():
    data = request.get_json(silent=True) or {}
    try:
        name = clean_text(data.get("name"), "Name", max_length=120)
        email = normalize_email(clean_text(data.get("email"), "Email", max_length=255))
        password = data.get("password", "")
    except ValueError as exc:
        return json_error(str(exc))

    if not validate_email(email):
        return json_error("Please provide a valid email address.")

    is_valid, password_message = validate_password(password)
    if not is_valid:
        return json_error(password_message)

    if User.query.filter_by(email=email).first():
        return json_error("An account with this email already exists.", 409)

    user = User(name=name, email=email, role="owner", auth_provider="local")
    user.set_password(password)
    db.session.add(user)
    db.session.flush()
    create_trial_subscription(user)
    db.session.commit()

    token = create_user_token(user)
    return jsonify(
        {
            "success": True,
            "message": "Account created successfully.",
            "token": token,
            "user": user.to_dict(),
        }
    ), 201


@api_bp.post("/login")
@limiter.limit("10 per minute")
def login():
    data = request.get_json(silent=True) or {}
    email = normalize_email((data.get("email") or "").strip())
    password = data.get("password") or ""

    if not validate_email(email):
        return json_error("Please provide a valid email address.")

    user = User.query.filter_by(email=email).first()
    if not user or not user.check_password(password):
        return json_error("Incorrect email or password.", 401)

    token = create_user_token(user)
    return jsonify(
        {
            "success": True,
            "message": "Login successful.",
            "token": token,
            "user": user.to_dict(),
        }
    )


@api_bp.post("/forgot-password")
@limiter.limit("5 per hour")
def forgot_password():
    data = request.get_json(silent=True) or {}
    email = normalize_email((data.get("email") or "").strip())
    if not validate_email(email):
        return json_error("Please provide a valid email address.")

    user = User.query.filter_by(email=email).first()
    has_delivery = bool(user and resolve_user_api_key(user, "email_service"))

    message = "If the email exists, password reset instructions have been queued."
    if not has_delivery:
        message = (
            "If the email exists, the reset request has been recorded. "
            "Configure an Email Service API Key for live delivery."
        )

    return jsonify(
        {
            "success": True,
            "message": message,
            "email_service_configured": has_delivery,
        }
    )


@api_bp.post("/auth/supabase/exchange")
@limiter.limit("10 per minute")
def auth_supabase_exchange():
    if not supabase_auth_configured():
        return json_error("Supabase authentication is not configured.")

    data = request.get_json(silent=True) or {}
    access_token = (data.get("access_token") or "").strip()
    verification = verify_supabase_access_token(access_token)
    if not verification.get("success"):
        return json_error(
            verification.get("message", "Unable to verify Supabase session."),
            verification.get("http_status") or 401,
            verification,
        )

    try:
        user = upsert_supabase_user(verification["user"])
        db.session.commit()
    except ValueError as exc:
        db.session.rollback()
        return json_error(str(exc))
    except Exception as exc:  # pragma: no cover - defensive fallback
        db.session.rollback()
        return json_error(f"Unable to link Supabase session: {exc}")

    token = create_user_token(user)
    return jsonify(
        {
            "success": True,
            "message": "Supabase authentication linked successfully.",
            "token": token,
            "user": user.to_dict(),
            "auth": build_auth_payload(user),
            "supabase_user": {
                "id": verification["user"].get("id"),
                "email": verification["user"].get("email"),
                "aud": verification["user"].get("aud"),
            },
        }
    )


@api_bp.get("/dashboard")
@jwt_required()
def dashboard():
    user = get_current_user()
    if not user:
        return json_error("User not found.", 404)

    process_due_scheduled_messages(user)

    employees = Employee.query.filter_by(user_id=user.id).all()
    customers = Customer.query.filter_by(user_id=user.id).all()
    invoices = (
        Invoice.query.join(Customer, Customer.id == Invoice.customer_id)
        .filter(Customer.user_id == user.id)
        .order_by(Invoice.issued_on.desc())
        .all()
    )
    today_records = (
        Attendance.query.join(Employee, Employee.id == Attendance.employee_id)
        .filter(Employee.user_id == user.id, Attendance.date == date.today())
        .all()
    )
    plan = get_current_subscription(user)
    effective_whatsapp = resolve_whatsapp_credentials(user=user, allow_env_fallback=True)
    subscription_payload = build_subscription_payload(user)

    total_sales = sum(float(invoice.amount) for invoice in invoices if invoice.status == "paid")
    today_sales = sum(
        float(invoice.amount)
        for invoice in invoices
        if invoice.status == "paid" and invoice.issued_on == date.today()
    )
    pending_invoices = [invoice for invoice in invoices if invoice.status in {"pending", "overdue"}]
    pending_payments = sum(float(invoice.amount) for invoice in pending_invoices)
    stats = {
        "total_employees": len(employees),
        "today_present": len([record for record in today_records if record.status == "present"]),
        "customer_count": len(customers),
        "today_sales": round(today_sales, 2),
        "pending_payments": round(pending_payments, 2),
        "pending_invoice_count": len(pending_invoices),
        "campaign_count": MarketingLog.query.filter_by(user_id=user.id).count(),
        "total_sales": round(total_sales, 2),
    }

    return jsonify(
        {
            "success": True,
            "user": user.to_dict(),
            "stats": stats,
            "growth_chart": build_growth_series(invoices),
            "recent_marketing": [
                log.to_dict()
                for log in MarketingLog.query.filter_by(user_id=user.id)
                .order_by(MarketingLog.sent_at.desc())
                .limit(4)
                .all()
            ],
            "recent_whatsapp_messages": [
                log.to_dict()
                for log in WhatsAppMessage.query.filter_by(user_id=user.id)
                .order_by(WhatsAppMessage.created_at.desc())
                .limit(6)
                .all()
            ],
            "subscription": subscription_payload["current"],
            "subscription_access": subscription_payload["access"],
            "subscription_quote": subscription_payload["quote"],
            "subscription_notice": subscription_payload["notice"],
            "subscription_upgrade_required": subscription_payload["upgrade_required"],
            "payment_gateways": subscription_payload["payment_gateways"],
            "integrations": {
                "ai_configured": bool(resolve_ai_api_key(user)),
                "openai_configured": bool(resolve_ai_api_key(user)),
                "ai_provider": "groq",
                "ai_source": "database"
                if resolve_user_api_key(user, AI_PROVIDER_SERVICE)
                else "environment"
                if os.getenv("GROQ_API_KEY") or current_app.config.get("GROQ_API_KEY")
                else "legacy"
                if resolve_user_api_key(user, AI_LEGACY_PROVIDER_SERVICE)
                else "none",
                "whatsapp_configured": bool(effective_whatsapp),
                "whatsapp_source": effective_whatsapp["source"] if effective_whatsapp else "none",
                "whatsapp_custom_connected": bool(
                    user.whatsapp_setting and user.whatsapp_setting.status == "connected"
                ),
                "whatsapp_live_access": user_has_live_whatsapp_access(user),
            },
            "focus_mode": "whatsapp-marketing",
        }
    )


@api_bp.route("/employees", methods=["GET", "POST"])
@jwt_required()
def employees():
    user = get_current_user()
    if not user:
        return json_error("User not found.", 404)

    if request.method == "GET":
        rows = Employee.query.filter_by(user_id=user.id).order_by(Employee.created_at.desc()).all()
        return jsonify({"success": True, "employees": [row.to_dict() for row in rows]})

    data = request.get_json(silent=True) or {}
    try:
        name = clean_text(data.get("name"), "Employee name", max_length=120)
        role = clean_text(data.get("role"), "Employee role", max_length=120)
    except ValueError as exc:
        return json_error(str(exc))

    row = Employee(user_id=user.id, name=name, role=role)
    db.session.add(row)
    db.session.commit()
    return jsonify({"success": True, "message": "Employee added.", "employee": row.to_dict()}), 201


@api_bp.route("/employees/<int:employee_id>", methods=["PUT", "DELETE"])
@jwt_required()
def employee_detail(employee_id):
    user = get_current_user()
    if not user:
        return json_error("User not found.", 404)

    row = Employee.query.filter_by(id=employee_id, user_id=user.id).first()
    if not row:
        return json_error("Employee not found.", 404)

    if request.method == "DELETE":
        db.session.delete(row)
        db.session.commit()
        return jsonify({"success": True, "message": "Employee deleted."})

    data = request.get_json(silent=True) or {}
    try:
        row.name = clean_text(data.get("name"), "Employee name", max_length=120)
        row.role = clean_text(data.get("role"), "Employee role", max_length=120)
    except ValueError as exc:
        return json_error(str(exc))

    db.session.commit()
    return jsonify({"success": True, "message": "Employee updated.", "employee": row.to_dict()})


@api_bp.route("/attendance", methods=["GET", "POST"])
@jwt_required()
def attendance():
    user = get_current_user()
    if not user:
        return json_error("User not found.", 404)

    if request.method == "GET":
        try:
            target_date = parse_target_date(request.args.get("date"))
        except ValueError as exc:
            return json_error(str(exc))
        rows = (
            Attendance.query.join(Employee, Employee.id == Attendance.employee_id)
            .filter(Employee.user_id == user.id, Attendance.date == target_date)
            .order_by(Employee.name.asc())
            .all()
        )
        return jsonify({"success": True, "attendance": [row.to_dict() for row in rows]})

    data = request.get_json(silent=True) or {}
    employee_id = data.get("employee_id")
    status = (data.get("status") or "").strip().lower()
    try:
        target_date = parse_target_date(data.get("date"))
    except ValueError as exc:
        return json_error(str(exc))

    if status not in ALLOWED_ATTENDANCE_STATUSES:
        return json_error("Status must be present, absent, or leave.")

    employee = Employee.query.filter_by(id=employee_id, user_id=user.id).first()
    if not employee:
        return json_error("Employee not found.", 404)

    record = Attendance.query.filter_by(employee_id=employee.id, date=target_date).first()
    if record:
        record.status = status
    else:
        record = Attendance(employee_id=employee.id, date=target_date, status=status)
        db.session.add(record)

    db.session.commit()
    return jsonify({"success": True, "message": "Attendance saved.", "attendance": record.to_dict()})


@api_bp.route("/customers", methods=["GET", "POST"])
@jwt_required()
def customers():
    user = get_current_user()
    if not user:
        return json_error("User not found.", 404)

    if request.method == "GET":
        rows = Customer.query.filter_by(user_id=user.id).order_by(Customer.created_at.desc()).all()
        return jsonify({"success": True, "customers": [row.to_dict() for row in rows]})

    data = request.get_json(silent=True) or {}
    try:
        name = clean_text(data.get("name"), "Customer name", max_length=120)
        phone = clean_text(data.get("phone"), "Customer phone", max_length=25)
        email = (data.get("email") or "").strip()
    except ValueError as exc:
        return json_error(str(exc))

    if not validate_phone_number(phone):
        return json_error("Please provide a valid phone number with country code.")
    if email and not validate_email(email):
        return json_error("Please provide a valid customer email.")
    if Customer.query.filter_by(user_id=user.id, phone=phone).first():
        return json_error("A customer with this phone number already exists.", 409)

    row = Customer(user_id=user.id, name=name, phone=phone, email=email or None)
    db.session.add(row)
    db.session.commit()
    return jsonify({"success": True, "message": "Customer added.", "customer": row.to_dict()}), 201


@api_bp.route("/customers/<int:customer_id>", methods=["PUT", "DELETE"])
@jwt_required()
def customer_detail(customer_id):
    user = get_current_user()
    if not user:
        return json_error("User not found.", 404)

    row = Customer.query.filter_by(id=customer_id, user_id=user.id).first()
    if not row:
        return json_error("Customer not found.", 404)

    if request.method == "DELETE":
        db.session.delete(row)
        db.session.commit()
        return jsonify({"success": True, "message": "Customer deleted."})

    data = request.get_json(silent=True) or {}
    try:
        name = clean_text(data.get("name"), "Customer name", max_length=120)
        phone = clean_text(data.get("phone"), "Customer phone", max_length=25)
        email = (data.get("email") or "").strip()
    except ValueError as exc:
        return json_error(str(exc))

    if not validate_phone_number(phone):
        return json_error("Please provide a valid phone number with country code.")
    if email and not validate_email(email):
        return json_error("Please provide a valid customer email.")

    duplicate = Customer.query.filter_by(user_id=user.id, phone=phone).first()
    if duplicate and duplicate.id != row.id:
        return json_error("A customer with this phone number already exists.", 409)

    row.name = name
    row.phone = phone
    row.email = email or None
    db.session.commit()
    return jsonify({"success": True, "message": "Customer updated.", "customer": row.to_dict()})


@api_bp.post("/customers/import")
@jwt_required()
def customers_import():
    user = get_current_user()
    if not user:
        return json_error("User not found.", 404)

    data = request.get_json(silent=True) or {}
    raw_contacts = (data.get("contacts") or "").strip()
    if not raw_contacts:
        return json_error("Paste at least one customer row to import.")

    created = []
    skipped = []
    for line in raw_contacts.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 2:
            skipped.append({"line": line, "reason": "Use format: name,phone,email"})
            continue
        name, phone = parts[0], parts[1]
        email = parts[2] if len(parts) > 2 else ""

        if not name:
            skipped.append({"line": line, "reason": "Name is required."})
            continue
        if not validate_phone_number(phone):
            skipped.append({"line": line, "reason": "Invalid phone number."})
            continue
        if email and not validate_email(email):
            skipped.append({"line": line, "reason": "Invalid email."})
            continue

        existing = Customer.query.filter_by(user_id=user.id, phone=phone).first()
        if existing:
            skipped.append({"line": line, "reason": "Phone already exists."})
            continue

        customer = Customer(user_id=user.id, name=name, phone=phone, email=email or None)
        db.session.add(customer)
        created.append(customer)

    db.session.commit()
    return jsonify(
        {
            "success": True,
            "message": f"Imported {len(created)} customers.",
            "created_count": len(created),
            "skipped": skipped,
        }
    )


@api_bp.route("/invoices", methods=["GET", "POST"])
@jwt_required()
def invoices():
    user = get_current_user()
    if not user:
        return json_error("User not found.", 404)

    if request.method == "GET":
        rows = (
            Invoice.query.join(Customer, Customer.id == Invoice.customer_id)
            .filter(Customer.user_id == user.id)
            .order_by(Invoice.issued_on.desc(), Invoice.id.desc())
            .all()
        )
        return jsonify({"success": True, "invoices": [row.to_dict() for row in rows]})

    data = request.get_json(silent=True) or {}
    customer = Customer.query.filter_by(id=data.get("customer_id"), user_id=user.id).first()
    if not customer:
        return json_error("Customer not found.", 404)

    status = (data.get("status") or "pending").strip().lower()
    if status not in ALLOWED_INVOICE_STATUSES:
        return json_error("Invoice status must be paid, pending, or overdue.")

    try:
        amount = parse_amount(data.get("amount"))
    except ValueError as exc:
        return json_error(str(exc))

    row = Invoice(customer_id=customer.id, amount=amount, status=status)
    db.session.add(row)
    db.session.commit()

    notification_result = None
    send_invoice_whatsapp = data.get("send_whatsapp") in {True, "true", "True", "on", "1", 1}
    if send_invoice_whatsapp and customer.phone:
        invoice_message = (
            f"Hello from GrowFlow AI. Invoice for {customer.name}: "
            f"amount Rs {float(row.amount):.0f}, status {row.status}. "
            "Reply if you need a copy or payment help."
        )
        results, _logs = dispatch_whatsapp_messages(
            user=user,
            recipients=[
                {
                    "customer_id": customer.id,
                    "customer_name": customer.name,
                    "recipient_phone": customer.phone,
                }
            ],
            message=invoice_message,
            message_type="invoice",
            template_name="Invoice message",
            delivery_mode="auto",
            allow_env_fallback=True,
        )
        notification_result = results[0] if results else None

    return jsonify(
        {
            "success": True,
            "message": "Invoice created.",
            "invoice": row.to_dict(),
            "notification": notification_result,
        }
    ), 201


@api_bp.route("/invoices/<int:invoice_id>", methods=["PUT", "DELETE"])
@jwt_required()
def invoice_detail(invoice_id):
    user = get_current_user()
    if not user:
        return json_error("User not found.", 404)

    row = (
        Invoice.query.join(Customer, Customer.id == Invoice.customer_id)
        .filter(Invoice.id == invoice_id, Customer.user_id == user.id)
        .first()
    )
    if not row:
        return json_error("Invoice not found.", 404)

    if request.method == "DELETE":
        db.session.delete(row)
        db.session.commit()
        return jsonify({"success": True, "message": "Invoice deleted."})

    data = request.get_json(silent=True) or {}
    status = (data.get("status") or row.status).strip().lower()
    if status not in ALLOWED_INVOICE_STATUSES:
        return json_error("Invoice status must be paid, pending, or overdue.")

    customer_id = data.get("customer_id") or row.customer_id
    customer = Customer.query.filter_by(id=customer_id, user_id=user.id).first()
    if not customer:
        return json_error("Customer not found.", 404)

    try:
        amount = parse_amount(data.get("amount") if data.get("amount") is not None else row.amount)
    except ValueError as exc:
        return json_error(str(exc))

    issued_on = row.issued_on
    if data.get("issued_on"):
        try:
            issued_on = parse_target_date(data.get("issued_on"))
        except ValueError as exc:
            return json_error(str(exc))

    row.customer_id = customer.id
    row.amount = amount
    row.status = status
    row.issued_on = issued_on
    db.session.commit()
    return jsonify({"success": True, "message": "Invoice updated.", "invoice": row.to_dict()})


@api_bp.get("/whatsapp/status")
@jwt_required()
def whatsapp_status():
    user = get_current_user()
    if not user:
        return json_error("User not found.", 404)
    process_due_scheduled_messages(user)
    payload = build_whatsapp_status_response(user)
    return jsonify({"success": True, **payload})


@api_bp.post("/whatsapp/status")
@jwt_required()
def whatsapp_status_post():
    return json_error("Use GET for WhatsApp status.", 405)


@api_bp.post("/whatsapp/connect")
@jwt_required()
@limiter.limit("10 per hour")
def whatsapp_connect():
    user = get_current_user()
    if not user:
        return json_error("User not found.", 404)

    data = request.get_json(silent=True) or {}
    setting = upsert_whatsapp_setting(user)

    existing_api_key = decrypt_secret(setting.api_key_encrypted)
    access_token = (data.get("access_token") or data.get("api_key") or "").strip() or existing_api_key
    verify_token = (data.get("verify_token") or "").strip() or decrypt_secret(
        setting.verify_token_encrypted
    )

    try:
        phone_number_id = clean_text(
            data.get("phone_number_id") or setting.phone_number_id,
            "Phone Number ID",
            max_length=120,
        )
        business_account_id = clean_text(
            data.get("business_account_id") or setting.business_account_id,
            "Business Account ID",
            max_length=120,
        )
    except ValueError as exc:
        return json_error(str(exc))

    if not access_token:
        return json_error("Access token is required.")

    verify_requested = data.get("verify", True)
    verify_requested = False if verify_requested in {False, "false", "False", 0, "0"} else True

    setting.api_key_encrypted = encrypt_secret(access_token)
    setting.phone_number_id = phone_number_id
    setting.business_account_id = business_account_id
    setting.verify_token_encrypted = encrypt_secret(verify_token) if verify_token else None
    setting.status = "saved"
    setting.last_error = None
    setting.last_verified_at = None
    sync_whatsapp_api_key_record(user, access_token)

    if not user_has_live_whatsapp_access(user):
        db.session.commit()
        payload = build_whatsapp_status_response(user)
        if verify_requested:
            return json_upgrade_required(
                user,
                "whatsapp_live",
                f"Live WhatsApp verification is locked after the trial. Upgrade to Pro for Rs {SUBSCRIPTION_BASE_PRICE_INR}/month to test this connection.",
            )
        return jsonify(
            {
                "success": True,
                "message": "WhatsApp credentials saved. Live verification is available on Pro or trial, while free plans stay in demo mode.",
                "verification": {
                    "success": False,
                    "verified": False,
                    "live_access": False,
                    "message": "Live WhatsApp verification is locked on this plan.",
                },
                **payload,
            }
        )

    if not verify_requested:
        db.session.commit()
        payload = build_whatsapp_status_response(user)
        return jsonify(
            {
                "success": True,
                "message": "WhatsApp credentials saved. Click Test Connection to verify them.",
                "verification": {
                    "success": True,
                    "verified": False,
                    "message": "Verification skipped.",
                },
                **payload,
            }
        )

    verification = verify_whatsapp_credentials(
        api_key=access_token,
        phone_number_id=phone_number_id,
        business_account_id=business_account_id,
        api_version=current_app.config.get("WHATSAPP_API_VERSION"),
    )
    if not verification["success"]:
        setting.status = "disconnected"
        setting.last_error = verification["message"]
        db.session.commit()
        payload = build_whatsapp_status_response(user)
        return (
            jsonify(
                {
                    "success": False,
                    "message": verification["message"],
                    "details": verification.get("details"),
                    **payload,
                }
            ),
            400,
        )

    setting.status = "connected"
    setting.last_error = None
    setting.last_verified_at = datetime.utcnow()
    db.session.commit()
    payload = build_whatsapp_status_response(user)
    return jsonify(
        {
            "success": True,
            "message": "WhatsApp connected successfully.",
            "metadata": verification.get("metadata", {}),
            **payload,
        }
    )


@api_bp.post("/whatsapp/disconnect")
@jwt_required()
@limiter.limit("10 per hour")
def whatsapp_disconnect():
    user = get_current_user()
    if not user:
        return json_error("User not found.", 404)

    if user.whatsapp_setting:
        disconnect_whatsapp_settings(user.whatsapp_setting)
        sync_whatsapp_api_key_record(user, "")
        db.session.commit()

    payload = build_whatsapp_status_response(user)
    return jsonify(
        {
            "success": True,
            "message": "WhatsApp settings disconnected and removed.",
            **payload,
        }
    )


@api_bp.get("/whatsapp/templates")
@jwt_required()
def whatsapp_templates_list():
    user = get_current_user()
    if not user:
        return json_error("User not found.", 404)
    return jsonify(
        {
            "success": True,
            "templates": build_template_listing(user),
        }
    )


@api_bp.post("/whatsapp/templates")
@jwt_required()
def whatsapp_templates_save():
    user = get_current_user()
    if not user:
        return json_error("User not found.", 404)

    data = request.get_json(silent=True) or {}
    template_id = data.get("id")
    try:
        template_name = clean_text(data.get("template_name"), "Template name", max_length=120)
        content = clean_text(data.get("content"), "Template content", max_length=1200)
        category = clean_text(data.get("category") or "custom", "Category", max_length=60)
    except ValueError as exc:
        return json_error(str(exc))

    if template_id:
        template = WhatsAppTemplate.query.filter_by(id=template_id, user_id=user.id).first()
        if not template:
            return json_error("Template not found.", 404)
        template.template_name = template_name
        template.content = content
        template.category = category
        message = "Template updated."
    else:
        template = WhatsAppTemplate(
            user_id=user.id,
            template_name=template_name,
            content=content,
            category=category,
        )
        db.session.add(template)
        message = "Template saved."

    db.session.commit()
    return jsonify({"success": True, "message": message, "template": template.to_dict()})


@api_bp.delete("/whatsapp/templates/<int:template_id>")
@jwt_required()
def whatsapp_templates_delete(template_id):
    user = get_current_user()
    if not user:
        return json_error("User not found.", 404)

    template = WhatsAppTemplate.query.filter_by(id=template_id, user_id=user.id).first()
    if not template:
        return json_error("Template not found.", 404)

    db.session.delete(template)
    db.session.commit()
    return jsonify({"success": True, "message": "Template deleted."})


@api_bp.get("/whatsapp/messages")
@jwt_required()
def whatsapp_messages_list():
    user = get_current_user()
    if not user:
        return json_error("User not found.", 404)

    process_due_scheduled_messages(user)
    rows = (
        WhatsAppMessage.query.filter_by(user_id=user.id)
        .order_by(WhatsAppMessage.created_at.desc())
        .limit(50)
        .all()
    )
    summary = {
        "total": len(rows),
        "sent": len([row for row in rows if row.status == "sent"]),
        "demo": len([row for row in rows if row.status == "demo"]),
        "scheduled": len([row for row in rows if row.status == "scheduled"]),
        "failed": len([row for row in rows if row.status == "failed"]),
    }
    return jsonify(
        {
            "success": True,
            "messages": [row.to_dict() for row in rows],
            "summary": summary,
        }
    )


@api_bp.post("/whatsapp/send")
@api_bp.post("/whatsapp/send-message")
@jwt_required()
@limiter.limit("30 per hour")
def whatsapp_send():
    user = get_current_user()
    if not user:
        return json_error("User not found.", 404)

    data = request.get_json(silent=True) or {}
    message_type = (data.get("message_type") or "text").strip().lower()
    if message_type not in WHATSAPP_MESSAGE_TYPES:
        return json_error("Message type must be text, promotional, invoice, reminder, or welcome.")

    delivery_mode = (data.get("mode") or "auto").strip().lower()
    if delivery_mode not in {"auto", "demo", "live"}:
        return json_error("Mode must be auto, demo, or live.")

    try:
        recipients = build_recipient_records(user, data)
        message, template_name = resolve_template_content(
            user=user,
            template_selection=data.get("template_selection"),
            message_content=data.get("message_content") or data.get("message"),
            message_type=message_type,
        )
        scheduled_for = parse_scheduled_datetime(data.get("scheduled_for"))
    except ValueError as exc:
        return json_error(str(exc))

    subscription_state = build_subscription_state(get_current_subscription(user))
    live_access = bool(subscription_state["trial_active"] or subscription_state["premium_active"])
    automation_requested = len(recipients) > 1 or message_type in {"promotional", "reminder"} or scheduled_for is not None
    if delivery_mode == "live" and not live_access:
        return json_upgrade_required(
            user,
            "whatsapp_live",
            f"Live WhatsApp sending is locked after the trial. Upgrade to Pro for Rs {SUBSCRIPTION_BASE_PRICE_INR}/month to continue.",
        )
    if automation_requested and not live_access:
        return json_upgrade_required(
            user,
            "automation",
            f"Broadcasts, reminders, and scheduled campaigns require an active trial or Pro plan at Rs {SUBSCRIPTION_BASE_PRICE_INR}/month.",
        )

    results, logs = dispatch_whatsapp_messages(
        user=user,
        recipients=recipients,
        message=message,
        message_type=message_type,
        template_name=template_name,
        delivery_mode=delivery_mode,
        scheduled_for=scheduled_for,
        allow_env_fallback=True,
    )

    if len(recipients) > 1 or message_type == "promotional":
        delivery_status = "sent" if any(result["success"] for result in results) else "failed"
        db.session.add(
            MarketingLog(
                user_id=user.id,
                message=message,
                audience="broadcast",
                delivery_status=delivery_status,
            )
        )
        db.session.commit()

    status_code = 200 if all(result["success"] for result in results) else 207
    if scheduled_for and scheduled_for > datetime.utcnow():
        summary = "Messages scheduled successfully."
    else:
        summary = "Message request processed."
    return (
        jsonify(
            {
                "success": True,
                "message": summary,
                "results": results,
                "messages": [log.to_dict() for log in logs],
            }
        ),
        status_code,
    )


@api_bp.get("/subscription/status")
@jwt_required()
def subscription_status():
    user = get_current_user()
    if not user:
        return json_error("User not found.", 404)
    return jsonify({"success": True, "subscription": build_subscription_payload(user)})


@api_bp.route("/subscription/trial-check", methods=["GET", "POST"])
@jwt_required()
def subscription_trial_check():
    user = get_current_user()
    if not user:
        return json_error("User not found.", 404)
    return jsonify({"success": True, "subscription": build_subscription_payload(user, track_prompt=True)})


@api_bp.post("/subscription/apply-promo")
@jwt_required()
@limiter.limit("12 per hour")
def subscription_apply_promo():
    user = get_current_user()
    if not user:
        return json_error("User not found.", 404)

    current_subscription = get_current_subscription(user)
    if not current_subscription:
        return json_error("No active subscription found.", 404)

    data = request.get_json(silent=True) or {}
    promo_code = (data.get("promo_code") or "").strip()
    promo_definition = resolve_promo_definition(promo_code)
    if not promo_definition:
        return json_error("Promo code is invalid.")
    current_code = (current_subscription.promo_code_used or "").strip().lower()
    if promo_code_used_by_user(user, promo_definition["code"]) and current_code != promo_definition["code"].lower():
        return json_error("This promo code has already been used for your account.", 409)
    if normalize_subscription_plan(current_subscription.plan) == PRO_PLAN_CODE and (current_subscription.payment_status or "").lower() == "paid":
        return json_error("Promo codes can only be applied before the first Pro purchase.", 400)

    if current_code == promo_definition["code"].lower():
        return jsonify(
            {
                "success": True,
                "message": f"Promo code {promo_definition['code']} is already applied.",
                "subscription": build_subscription_payload(user),
            }
        )

    discount_percent = int(promo_definition["discount_value"])
    discount_amount = (SUBSCRIPTION_BASE_PRICE_INR * discount_percent) // 100
    amount_due = max(0, SUBSCRIPTION_BASE_PRICE_INR - discount_amount)
    update_subscription_promo(current_subscription, promo_definition["code"], discount_percent, discount_amount, amount_due)
    current_subscription.payment_provider = current_subscription.payment_provider or ""
    current_subscription.payment_reference = None
    current_subscription.payment_status = "pending" if amount_due > 0 else "paid"
    db.session.commit()

    return jsonify(
        {
            "success": True,
            "message": (
                f"Promo code {promo_definition['code']} applied successfully. Pro can be activated for free."
                if amount_due == 0
                else f"Promo code {promo_definition['code']} applied successfully."
            ),
            "subscription": build_subscription_payload(user),
        }
    )


@api_bp.post("/subscription/payment")
@jwt_required()
@limiter.limit("10 per hour")
def subscription_payment():
    user = get_current_user()
    if not user:
        return json_error("User not found.", 404)

    current_subscription = get_current_subscription(user)
    if not current_subscription:
        return json_error("No active subscription found.", 404)

    data = request.get_json(silent=True) or {}
    provider = (data.get("provider") or build_payment_gateway_payload()["default_provider"]).strip().lower()

    quote = build_subscription_quote(user, current_subscription, data.get("promo_code"))
    current_code = (current_subscription.promo_code_used or "").strip().lower()
    if quote["promo_valid"] and quote["promo_code"] and quote["promo_code"].strip().lower() != current_code:
        update_subscription_promo(
            current_subscription,
            quote["promo_code"],
            quote["discount_percent"],
            quote["discount_amount"],
            quote["amount_due"],
        )
        current_subscription.payment_reference = None
        current_subscription.payment_provider = provider
        current_subscription.payment_status = "pending"
        db.session.flush()

    if int(quote["amount_due"]) <= 0:
        subscription = activate_paid_subscription(
            user,
            source_subscription=current_subscription,
            payment_provider="promo",
            payment_status="paid",
            payment_reference=f"promo-{secrets.token_hex(6)}",
            promo_code_used=quote["promo_code"],
            promo_discount_percent=quote["discount_percent"],
            promo_discount_amount=quote["discount_amount"],
            amount_due=0,
        )
        db.session.commit()
        return jsonify(
            {
                "success": True,
                "message": "Promo code applied. Pro access activated for free.",
                "subscription": serialize_subscription(subscription),
                "quote": quote,
            }
        )

    if provider not in {"razorpay", "stripe", "demo"}:
        return json_error("Provider must be razorpay, stripe, or demo.")

    payment_link_id = (data.get("payment_link_id") or current_subscription.payment_reference or "").strip()
    if payment_link_id and provider == "razorpay":
        try:
            link_payload = fetch_razorpay_payment_link(payment_link_id)
        except ValueError as exc:
            return json_error(str(exc))

        link_status = (link_payload.get("status") or "").strip().lower()
        if link_status != "paid":
            current_subscription.payment_provider = "razorpay"
            current_subscription.payment_status = "pending"
            current_subscription.payment_reference = payment_link_id
            current_subscription.amount_due = quote["amount_due"]
            db.session.commit()
            return jsonify(
                {
                    "success": True,
                    "message": "Payment link is still pending. Complete the payment and verify again.",
                    "checkout": {
                        "provider": "razorpay",
                        "payment_link_id": payment_link_id,
                        "short_url": link_payload.get("short_url") or "",
                        "status": link_status,
                        "amount": link_payload.get("amount") or int(quote["amount_due"]) * 100,
                        "currency": link_payload.get("currency") or "INR",
                    },
                    "subscription": build_subscription_payload(user),
                }
            )

        subscription = activate_paid_subscription(
            user,
            source_subscription=current_subscription,
            payment_provider="razorpay",
            payment_status="paid",
            payment_reference=payment_link_id,
            promo_code_used=quote["promo_code"],
            promo_discount_percent=quote["discount_percent"],
            promo_discount_amount=quote["discount_amount"],
            amount_due=quote["amount_due"],
        )
        db.session.commit()
        return jsonify(
            {
                "success": True,
                "message": "Payment verified and Pro access activated.",
                "subscription": serialize_subscription(subscription),
            }
        )

    if provider == "razorpay" and build_payment_gateway_payload()["razorpay_available"]:
        current_subscription.payment_provider = "razorpay"
        current_subscription.payment_status = "pending"
        current_subscription.amount_due = quote["amount_due"]
        db.session.flush()
        try:
            checkout = create_razorpay_payment_link(user, build_subscription_state(current_subscription), quote)
        except ValueError as exc:
            return json_error(str(exc))

        current_subscription.payment_reference = checkout["payment_link_id"]
        db.session.commit()
        return jsonify(
            {
                "success": True,
                "message": "Razorpay payment link created.",
                "checkout": checkout,
                "quote": quote,
                "subscription": build_subscription_payload(user),
            }
        )

    if provider == "stripe":
        return json_error("Stripe checkout is not wired in this build yet.", 501)

    if not current_app.config.get("SUBSCRIPTION_DEMO_PAYMENTS", True):
        return json_error("Configure Razorpay to accept live payments.", 503)

    subscription = activate_paid_subscription(
        user,
        source_subscription=current_subscription,
        payment_provider="demo",
        payment_status="paid",
        payment_reference=f"demo-{secrets.token_hex(6)}",
        promo_code_used=quote["promo_code"],
        promo_discount_percent=quote["discount_percent"],
        promo_discount_amount=quote["discount_amount"],
        amount_due=quote["amount_due"],
    )
    db.session.commit()
    return jsonify(
        {
            "success": True,
            "message": "Demo payment processed and Pro access activated.",
            "subscription": serialize_subscription(subscription),
            "quote": quote,
        }
    )


@api_bp.post("/subscription/upgrade")
@jwt_required()
def subscription_upgrade():
    return subscription_payment()


@api_bp.post("/subscription/update")
@jwt_required()
def subscription_update():
    user = get_current_user()
    if not user:
        return json_error("User not found.", 404)

    data = request.get_json(silent=True) or {}
    plan = normalize_subscription_plan(data.get("plan"))
    if plan == FREE_PLAN_CODE:
        subscription = create_subscription_record(
            user,
            FREE_PLAN_CODE,
            "active",
            amount_due=0,
            payment_status="not_required",
            payment_provider="manual",
            activated_at=datetime.utcnow(),
            renewed_on=date.today(),
        )
        db.session.commit()
        return jsonify(
            {
                "success": True,
                "message": "Plan updated successfully.",
                "subscription": serialize_subscription(subscription),
            }
        )

    if plan in PREMIUM_PLAN_CODES:
        return json_error("Use /api/subscription/payment to activate Pro.", 403)

    return json_error("Plan must be free or pro.")


@api_bp.get("/backup/export")
@jwt_required()
def backup_export():
    user = get_current_user()
    if not user:
        return json_error("User not found.", 404)

    subscription_state = build_subscription_state(get_current_subscription(user))
    if not (subscription_state["trial_active"] or subscription_state["premium_active"]):
        return json_upgrade_required(
            user,
            "export",
            f"Backup exports are locked after the trial. Upgrade to Pro for Rs {SUBSCRIPTION_BASE_PRICE_INR}/month to continue.",
        )

    customers = Customer.query.filter_by(user_id=user.id).order_by(Customer.id.asc()).all()
    employees = Employee.query.filter_by(user_id=user.id).order_by(Employee.id.asc()).all()
    invoices = (
        Invoice.query.join(Customer, Customer.id == Invoice.customer_id)
        .filter(Customer.user_id == user.id)
        .order_by(Invoice.id.asc())
        .all()
    )
    logs = MarketingLog.query.filter_by(user_id=user.id).order_by(MarketingLog.id.asc()).all()
    whatsapp_logs = (
        WhatsAppMessage.query.filter_by(user_id=user.id)
        .order_by(WhatsAppMessage.id.asc())
        .all()
    )
    templates = (
        WhatsAppTemplate.query.filter_by(user_id=user.id)
        .order_by(WhatsAppTemplate.id.asc())
        .all()
    )
    subscription = get_current_subscription(user)

    response = jsonify(
        {
            "success": True,
            "generated_at": datetime.utcnow().isoformat(),
            "user": user.to_dict(),
            "settings": get_setting_map(user),
            "api_keys": build_api_key_payload(user),
            "subscription": serialize_subscription(subscription),
            "customers": [row.to_dict() for row in customers],
            "employees": [row.to_dict() for row in employees],
            "invoices": [row.to_dict() for row in invoices],
            "marketing_logs": [row.to_dict() for row in logs],
            "whatsapp_messages": [row.to_dict() for row in whatsapp_logs],
            "templates": [row.to_dict() for row in templates],
            "whatsapp_status": build_whatsapp_status_response(user),
        }
    )
    response.headers["Content-Disposition"] = 'attachment; filename="growflow-backup.json"'
    return response


@api_bp.route("/settings/account", methods=["GET", "POST", "DELETE"])
@jwt_required()
def settings_account():
    user = get_current_user()
    if not user:
        return json_error("User not found.", 404)

    if request.method == "GET":
        return jsonify({"success": True, "account": build_account_payload(user)})

    data = request.get_json(silent=True) or {}
    if request.method == "DELETE":
        if getattr(user, "auth_provider", "local") == "supabase":
            return json_error(
                "Account deletion for Supabase-authenticated users is not enabled from this dashboard yet.",
                403,
            )
        password = data.get("password") or ""
        if not password or not user.check_password(password):
            return json_error("Current password is required to delete the account.", 403)
        db.session.delete(user)
        db.session.commit()
        return jsonify({"success": True, "message": "Account deleted permanently."})

    try:
        name = clean_text(data.get("name"), "Name", max_length=120)
        email = normalize_email(clean_text(data.get("email"), "Email", max_length=255))
    except ValueError as exc:
        return json_error(str(exc))

    phone_number = (data.get("phone_number") or "").strip()
    business_name = (data.get("business_name") or "").strip()

    if not validate_email(email):
        return json_error("Please provide a valid email address.")
    existing = User.query.filter_by(email=email).first()
    if existing and existing.id != user.id:
        return json_error("Another account already uses this email address.", 409)
    if getattr(user, "auth_provider", "local") == "supabase" and email != user.email:
        return json_error(
            "Email changes are managed by Supabase authentication. Keep the auth email unchanged from this dashboard.",
            403,
        )
    if phone_number and not validate_phone_number(phone_number):
        return json_error("Please provide a valid phone number with country code.")
    if len(business_name) > 160:
        return json_error("Business name must be under 160 characters.")

    user.name = name
    if getattr(user, "auth_provider", "local") != "supabase":
        user.email = email
    upsert_setting_value(user, "account.phone_number", phone_number)
    upsert_setting_value(user, "account.business_name", business_name)
    db.session.commit()

    return jsonify(
        {
            "success": True,
            "message": "Account settings updated.",
            "account": build_account_payload(user),
            "user": user.to_dict(),
        }
    )


@api_bp.route("/settings/auth", methods=["GET", "POST"])
@jwt_required()
def settings_auth():
    user = get_current_user()
    if not user:
        return json_error("User not found.", 404)

    if request.method == "GET":
        return jsonify({"success": True, "auth": build_auth_payload(user)})

    data = request.get_json(silent=True) or {}
    action = (data.get("action") or "password_reset").strip().lower()
    if action != "password_reset":
        return json_error("Supported action is password_reset only.")

    if supabase_auth_configured():
        return jsonify(
            {
                "success": True,
                "message": "Supabase handles password resets from the authentication page.",
            }
        )

    if resolve_user_api_key(user, "email_service"):
        return jsonify(
            {
                "success": True,
                "message": "Password reset request accepted. Delivery would use your configured email service.",
            }
        )
    return jsonify(
        {
            "success": True,
            "message": "Password reset demo requested. Add an Email Service API Key for live delivery.",
        }
    )


@api_bp.route("/settings/api-management", methods=["GET", "POST", "DELETE"])
@jwt_required()
@limiter.limit("15 per hour")
def settings_api_management():
    user = get_current_user()
    if not user:
        return json_error("User not found.", 404)
    if not user_can_manage_api_settings(user):
        return json_error("Only account owners can manage the AI API.", 403)

    if request.method == "GET":
        return jsonify(
            {
                "success": True,
                "api_management": build_ai_management_payload(user),
                "api_keys": build_api_key_payload(user),
            }
        )

    if request.method == "DELETE":
        record = find_user_api_key(user, AI_PROVIDER_SERVICE)
        removed = bool(record)
        if record:
            db.session.delete(record)
            db.session.commit()
        message = "Groq API key removed." if removed else "No stored Groq API key was found."
        if os.getenv("GROQ_API_KEY") or current_app.config.get("GROQ_API_KEY"):
            message += " GROQ_API_KEY from the environment is still active."
        return jsonify(
            {
                "success": True,
                "message": message,
                "api_management": build_ai_management_payload(user),
                "api_keys": build_api_key_payload(user),
            }
        )

    data = request.get_json(silent=True) or {}
    raw_key = (data.get("api_key") or "").strip()
    verify = data.get("verify")
    verify = False if verify in {False, "false", "False", 0, "0"} else True
    model_override = (data.get("model") or "").strip() or None

    if raw_key:
        upsert_user_api_key(user, AI_PROVIDER_SERVICE, raw_key, status="saved")

    active_key = raw_key or resolve_ai_api_key(user)
    if not active_key:
        return json_error("Add a Groq API key or set GROQ_API_KEY in the environment.")

    verification = {
        "success": True,
        "message": "Verification skipped.",
        "status": "saved",
        "verified": False,
    }
    if verify:
        verification = test_ai_provider_connection(active_key, model=model_override)
        verification["verified"] = True

    record = find_user_api_key(user, AI_PROVIDER_SERVICE)
    if record:
        if verify:
            record.status = "connected" if verification.get("success") else "error"
        else:
            record.status = "saved"
        if raw_key and not verification.get("success"):
            record.status = "error"
        if not verification.get("success"):
            record.status = "error"
        if verification.get("success") and raw_key and verify:
            record.status = "connected"

    db.session.commit()

    if raw_key and verify and verification.get("success"):
        message = "Groq API key saved and verified."
    elif raw_key and not verify:
        message = "Groq API key saved."
    elif raw_key and verify:
        message = "Groq API key saved, but verification failed."
    elif verify and verification.get("success"):
        message = "Groq API configuration verified."
    elif verify:
        message = "Groq API configuration verification failed."
    else:
        message = "Groq API configuration updated."

    return jsonify(
        {
            "success": True,
            "message": message,
            "api_management": build_ai_management_payload(user),
            "api_keys": build_api_key_payload(user),
            "verification": verification,
        }
    )


@api_bp.route("/settings/api-keys", methods=["GET", "POST", "DELETE"])
@jwt_required()
def settings_api_keys():
    user = get_current_user()
    if not user:
        return json_error("User not found.", 404)

    if request.method == "GET":
        return jsonify({"success": True, "api_keys": build_api_key_payload(user)})

    data = request.get_json(silent=True) or {}
    service_name = (data.get("service_name") or "").strip().lower()
    if service_name not in SUPPORTED_API_KEY_SERVICES:
        return json_error("Choose a supported API key service.")

    if request.method == "DELETE":
        if service_name == "whatsapp" and user.whatsapp_setting:
            user.whatsapp_setting.api_key_encrypted = None
            user.whatsapp_setting.status = "disconnected"
            user.whatsapp_setting.last_error = "Access token removed from API key settings."
            user.whatsapp_setting.last_verified_at = None
        delete_user_api_key(user, service_name)
        db.session.commit()
        return jsonify(
            {
                "success": True,
                "message": f"{SUPPORTED_API_KEY_SERVICES[service_name]} removed.",
                "api_keys": build_api_key_payload(user),
            }
        )

    raw_key = (data.get("api_key") or "").strip()
    if not raw_key:
        return json_error("API key value is required.")

    upsert_user_api_key(user, service_name, raw_key, status="saved")
    if service_name == "whatsapp":
        setting = upsert_whatsapp_setting(user)
        setting.api_key_encrypted = encrypt_secret(raw_key)
        if not setting.phone_number_id or not setting.business_account_id:
            setting.status = "disconnected"
    db.session.commit()

    return jsonify(
        {
            "success": True,
            "message": f"{SUPPORTED_API_KEY_SERVICES[service_name]} saved securely.",
            "api_keys": build_api_key_payload(user),
        }
    )


@api_bp.route("/settings/whatsapp", methods=["GET", "POST"])
@jwt_required()
def settings_whatsapp():
    user = get_current_user()
    if not user:
        return json_error("User not found.", 404)

    if request.method == "GET":
        return jsonify({"success": True, **build_whatsapp_status_response(user)})

    data = request.get_json(silent=True) or {}
    action = (data.get("action") or "connect").strip().lower()
    if action == "disconnect":
        return whatsapp_disconnect()
    if action in {"test", "verify"}:
        return whatsapp_verify()
    if action != "connect":
        return json_error("Action must be connect, disconnect, test, or verify.")
    return whatsapp_connect()


@api_bp.post("/whatsapp/verify")
@jwt_required()
@limiter.limit("10 per hour")
def whatsapp_verify():
    return whatsapp_connect()


@api_bp.post("/whatsapp/bulk-send")
@jwt_required()
@limiter.limit("20 per hour")
def whatsapp_bulk_send():
    return whatsapp_send()


@api_bp.get("/whatsapp/history")
@jwt_required()
def whatsapp_history():
    return whatsapp_messages_list()


@api_bp.route("/settings/notifications", methods=["GET", "POST"])
@jwt_required()
def settings_notifications():
    user = get_current_user()
    if not user:
        return json_error("User not found.", 404)

    if request.method == "GET":
        return jsonify({"success": True, "preferences": build_notification_payload(user)})

    data = request.get_json(silent=True) or {}
    theme = (data.get("theme") or "dark").strip().lower()
    language = (data.get("language") or "english").strip().lower()

    if theme not in {"dark", "light"}:
        return json_error("Theme must be dark or light.")
    if language not in {"english", "hindi"}:
        return json_error("Language must be English or Hindi.")

    upsert_setting_value(
        user,
        "notifications.email_enabled",
        "true" if data.get("email_notifications") in {True, "true", "True", "on", "1", 1} else "false",
    )
    upsert_setting_value(
        user,
        "notifications.whatsapp_enabled",
        "true" if data.get("whatsapp_notifications") in {True, "true", "True", "on", "1", 1} else "false",
    )
    upsert_setting_value(
        user,
        "notifications.sms_enabled",
        "true" if data.get("sms_alerts") in {True, "true", "True", "on", "1", 1} else "false",
    )
    upsert_setting_value(user, "preferences.theme", theme)
    upsert_setting_value(user, "preferences.language", language)
    db.session.commit()

    return jsonify(
        {
            "success": True,
            "message": "Notification and preference settings updated.",
            "preferences": build_notification_payload(user),
        }
    )


@api_bp.route("/settings/subscription", methods=["GET", "POST"])
@jwt_required()
def settings_subscription():
    user = get_current_user()
    if not user:
        return json_error("User not found.", 404)

    if request.method == "GET":
        return jsonify({"success": True, "subscription": build_subscription_payload(user)})

    data = request.get_json(silent=True) or {}
    action = (data.get("action") or "change").strip().lower()
    plan = (data.get("plan") or "").strip().lower()

    if action == "cancel":
        subscription = create_subscription_record(
            user,
            FREE_PLAN_CODE,
            "active",
            amount_due=0,
            payment_status="not_required",
            payment_provider="manual",
            activated_at=datetime.utcnow(),
            renewed_on=date.today(),
        )
        db.session.commit()
        return jsonify(
            {
                "success": True,
                "message": "Subscription cancelled. Account moved to Free plan.",
                "subscription": build_subscription_payload(user),
            }
        )

    if action == "change" and plan in PREMIUM_PLAN_CODES:
        return json_error("Use the subscription payment flow to activate Pro.", 403)

    normalized_plan = normalize_subscription_plan(plan)
    if normalized_plan == FREE_PLAN_CODE:
        subscription = create_subscription_record(
            user,
            FREE_PLAN_CODE,
            "active",
            amount_due=0,
            payment_status="not_required",
            payment_provider="manual",
            activated_at=datetime.utcnow(),
            renewed_on=date.today(),
        )
        db.session.commit()
        return jsonify(
            {
                "success": True,
                "message": "Subscription updated successfully.",
                "subscription": build_subscription_payload(user),
            }
        )

    if normalized_plan in PREMIUM_PLAN_CODES:
        return json_error("Use the subscription payment flow to activate Pro.", 403)

    return json_error("Plan must be free or pro.")


@api_bp.route("/settings/security", methods=["GET", "POST"])
@jwt_required()
def settings_security():
    user = get_current_user()
    if not user:
        return json_error("User not found.", 404)

    if request.method == "GET":
        return jsonify({"success": True, "security": build_security_payload(user)})

    data = request.get_json(silent=True) or {}
    action = (data.get("action") or "change_password").strip().lower()

    if action == "toggle_2fa":
        enabled = data.get("enabled") in {True, "true", "True", "on", "1", 1}
        upsert_setting_value(user, "security.two_factor_enabled", "true" if enabled else "false")
        db.session.commit()
        return jsonify(
            {
                "success": True,
                "message": "Two-factor preference updated.",
                "security": build_security_payload(user),
            }
        )

    if action == "logout_all":
        bump_session_version(user)
        db.session.commit()
        return jsonify(
            {
                "success": True,
                "message": "All active sessions were logged out.",
                "logout_required": True,
            }
        )

    if action != "change_password":
        return json_error("Action must be change_password, toggle_2fa, or logout_all.")

    if getattr(user, "auth_provider", "local") == "supabase":
        return json_error(
            "Password changes are handled by Supabase authentication. Use the reset link on the sign-in page.",
            403,
        )

    current_password = data.get("current_password") or ""
    new_password = data.get("new_password") or ""

    if not user.check_password(current_password):
        return json_error("Current password is incorrect.", 403)

    is_valid, password_message = validate_password(new_password)
    if not is_valid:
        return json_error(password_message)

    user.set_password(new_password)
    bump_session_version(user)
    db.session.commit()
    new_token = create_user_token(user)
    return jsonify(
        {
            "success": True,
            "message": "Password changed successfully.",
            "token": new_token,
            "user": user.to_dict(),
            "security": build_security_payload(user),
        }
    )


@api_bp.route("/settings/data", methods=["GET", "POST", "DELETE"])
@jwt_required()
def settings_data():
    user = get_current_user()
    if not user:
        return json_error("User not found.", 404)

    if request.method == "GET":
        if request.args.get("format") == "csv":
            subscription_state = build_subscription_state(get_current_subscription(user))
            if not (subscription_state["trial_active"] or subscription_state["premium_active"]):
                return json_upgrade_required(
                    user,
                    "export",
                    f"CSV exports are locked after the trial. Upgrade to Pro for Rs {SUBSCRIPTION_BASE_PRICE_INR}/month to continue.",
                )
            payload = build_csv_export_bundle(user)
            response = Response(payload, mimetype="application/zip")
            response.headers["Content-Disposition"] = 'attachment; filename="growflow-export-csv.zip"'
            return response
        return jsonify({"success": True, "data": build_data_summary(user)})

    data = request.get_json(silent=True) or {}
    if request.method == "DELETE":
        if str(data.get("confirm") or "").strip().upper() != "DELETE":
            return json_error("Type DELETE to confirm data removal.")
        delete_user_business_data(user, clear_preferences=False)
        db.session.commit()
        return jsonify(
            {
                "success": True,
                "message": "Business data deleted. Account and subscription were kept.",
                "data": build_data_summary(user),
            }
        )

    action = (data.get("action") or "restore").strip().lower()
    if action != "restore":
        return json_error("Supported action is restore only.")

    try:
        backup_payload = parse_restore_payload(data)
    except ValueError as exc:
        return json_error(str(exc))

    restore_backup_payload(user, backup_payload)
    db.session.commit()
    return jsonify(
        {
            "success": True,
            "message": "Backup restored successfully.",
            "data": build_data_summary(user),
        }
    )


@api_bp.post("/marketing/send")
@jwt_required()
@limiter.limit("20 per hour")
def marketing_send():
    user = get_current_user()
    if not user:
        return json_error("User not found.", 404)

    data = request.get_json(silent=True) or {}
    subscription_state = build_subscription_state(get_current_subscription(user))
    if not (subscription_state["trial_active"] or subscription_state["premium_active"]):
        return json_upgrade_required(
            user,
            "automation",
            f"Bulk marketing broadcasts are locked after the trial. Upgrade to Pro for Rs {SUBSCRIPTION_BASE_PRICE_INR}/month to continue.",
        )
    try:
        message = clean_text(data.get("message"), "Marketing message", max_length=1200)
    except ValueError as exc:
        return json_error(str(exc))

    audience = (data.get("audience") or "selected_customers").strip()
    customer_ids = data.get("customer_ids") or []
    manual_numbers = data.get("numbers") or []

    recipients = []
    customers_query = Customer.query.filter_by(user_id=user.id)
    if audience == "all_customers":
        recipients.extend(
            {
                "customer_id": customer.id,
                "customer_name": customer.name,
                "recipient_phone": customer.phone,
            }
            for customer in customers_query.all()
        )
    else:
        recipients.extend(
            {
                "customer_id": customer.id,
                "customer_name": customer.name,
                "recipient_phone": customer.phone,
            }
            for customer in customers_query.filter(Customer.id.in_(customer_ids)).all()
        )

    for number in manual_numbers:
        if str(number).strip():
            recipients.append(
                {
                    "customer_id": None,
                    "customer_name": "",
                    "recipient_phone": str(number).strip(),
                }
            )

    if not recipients:
        return json_error("Please select at least one recipient.")

    for record in recipients:
        if not validate_phone_number(record["recipient_phone"]):
            return json_error(f"Invalid phone number: {record['recipient_phone']}")

    results, _logs = dispatch_whatsapp_messages(
        user=user,
        recipients=recipients,
        message=message,
        message_type="promotional",
        template_name="Broadcast campaign",
        delivery_mode="auto",
        allow_env_fallback=True,
    )
    delivery_status = "sent" if any(result["success"] for result in results) else "failed"

    log = MarketingLog(
        user_id=user.id,
        message=message,
        audience=audience,
        delivery_status=delivery_status,
    )
    db.session.add(log)
    db.session.commit()

    return jsonify(
        {
            "success": True,
            "message": "Marketing request processed.",
            "results": results,
            "log": log.to_dict(),
        }
    )


def generate_ai_content_response(user, content_type, data):
    if content_type not in {"poster", "caption", "marketing"}:
        return json_error("Content type must be poster, caption, or marketing.")

    subscription_state = build_subscription_state(get_current_subscription(user))
    if not (subscription_state["trial_active"] or subscription_state["premium_active"]):
        return json_upgrade_required(
            user,
            "ai_tools",
            f"AI content generation is locked after the trial. Upgrade to Pro for Rs {SUBSCRIPTION_BASE_PRICE_INR}/month to continue.",
        )

    try:
        prompt = clean_text(data.get("prompt"), "Prompt", max_length=600)
    except ValueError as exc:
        return json_error(str(exc))

    business_name = (data.get("business_name") or user.name).strip()
    model_override = (data.get("model") or "").strip() or None
    result = generate_business_content(
        business_name=business_name,
        content_type=content_type,
        prompt=prompt,
        api_key_override=resolve_ai_api_key(user),
        model_override=model_override,
    )

    response_payload = {
        "success": True,
        "content_type": content_type,
        "result": result,
        "api_management": build_ai_management_payload(user),
    }
    if result.get("warning"):
        response_payload["warning"] = result["warning"]
    if result.get("used_fallback"):
        response_payload["used_fallback"] = True
    return jsonify(response_payload)


@api_bp.post("/ai/generate-content")
@jwt_required()
@limiter.limit("25 per hour")
def ai_generate_content():
    user = get_current_user()
    if not user:
        return json_error("User not found.", 404)

    data = request.get_json(silent=True) or {}
    content_type = (data.get("content_type") or data.get("type") or "caption").strip().lower()
    return generate_ai_content_response(user, content_type, data)


@api_bp.post("/ai/generate-poster")
@jwt_required()
@limiter.limit("25 per hour")
def ai_generate_poster():
    user = get_current_user()
    if not user:
        return json_error("User not found.", 404)

    data = request.get_json(silent=True) or {}
    return generate_ai_content_response(user, "poster", data)


@api_bp.post("/ai/generate-marketing-message")
@jwt_required()
@limiter.limit("25 per hour")
def ai_generate_marketing_message():
    user = get_current_user()
    if not user:
        return json_error("User not found.", 404)

    data = request.get_json(silent=True) or {}
    return generate_ai_content_response(user, "marketing", data)


@api_bp.post("/ai/generate")
@jwt_required()
@limiter.limit("25 per hour")
def ai_generate():
    user = get_current_user()
    if not user:
        return json_error("User not found.", 404)

    data = request.get_json(silent=True) or {}
    content_type = (data.get("type") or data.get("content_type") or "caption").strip().lower()
    return generate_ai_content_response(user, content_type, data)
