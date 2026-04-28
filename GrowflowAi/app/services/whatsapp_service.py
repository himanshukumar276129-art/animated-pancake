import base64
import hashlib
import re

import requests
from cryptography.fernet import Fernet, InvalidToken
from flask import current_app


PHONE_RE = re.compile(r"^\+?[1-9]\d{7,14}$")

MESSAGE_TEMPLATES = {
    "text": "Hello from GrowFlow AI",
    "promotional": "Hello from GrowFlow AI. Your latest offer is ready to share with customers.",
    "invoice": "Hello from GrowFlow AI. Your invoice update is ready for review.",
    "reminder": "Hello from GrowFlow AI. This is a friendly reminder for your upcoming follow-up.",
    "welcome": "Welcome from GrowFlow AI. Thank you for connecting with our business.",
}

BUILTIN_WHATSAPP_TEMPLATES = [
    {
        "key": "festival-diwali",
        "template_name": "Diwali Offer",
        "category": "festival",
        "content": "Happy Diwali from our shop. Visit today and enjoy festive savings on your favorite products. Reply now to book your order.",
        "is_builtin": True,
    },
    {
        "key": "festival-holi",
        "template_name": "Holi Special",
        "category": "festival",
        "content": "Holi special offer is live now. Celebrate with color, savings, and fast service from our team.",
        "is_builtin": True,
    },
    {
        "key": "discount-offer",
        "template_name": "Discount Offer",
        "category": "discount",
        "content": "Special discount available this week. Reply now to reserve your order or ask for today's pricing.",
        "is_builtin": True,
    },
    {
        "key": "payment-reminder",
        "template_name": "Payment Reminder",
        "category": "reminder",
        "content": "Namaste. This is a friendly reminder about your pending payment. Please reply if you need the invoice again.",
        "is_builtin": True,
    },
    {
        "key": "welcome-message",
        "template_name": "Welcome Message",
        "category": "welcome",
        "content": "Welcome from our business. Thank you for saving our number. We are ready to help you anytime.",
        "is_builtin": True,
    },
]


def build_message_content(message_type, custom_message):
    message = (custom_message or "").strip()
    if message:
        return message
    return MESSAGE_TEMPLATES.get(message_type, MESSAGE_TEMPLATES["text"])


def get_builtin_templates():
    return BUILTIN_WHATSAPP_TEMPLATES


def find_builtin_template(template_key):
    for template in BUILTIN_WHATSAPP_TEMPLATES:
        if template["key"] == template_key:
            return template
    return None


def validate_phone_number(phone):
    value = (phone or "").strip()
    return bool(PHONE_RE.match(value))


def _fernet():
    secret = (
        current_app.config.get("WHATSAPP_SETTINGS_ENCRYPTION_KEY")
        or current_app.config.get("SECRET_KEY")
        or "growflow-whatsapp-secret"
    )
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())
    return Fernet(key)


def encrypt_secret(value):
    text = (value or "").strip()
    if not text:
        return None
    return _fernet().encrypt(text.encode("utf-8")).decode("utf-8")


def decrypt_secret(value):
    if not value:
        return ""
    try:
        return _fernet().decrypt(value.encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError):
        return ""


def mask_secret(value):
    if not value:
        return ""
    visible = value[-4:] if len(value) > 4 else value
    return f"{'*' * max(4, len(value) - len(visible))}{visible}"


def parse_meta_error(response):
    try:
        payload = response.json()
    except ValueError:
        payload = {}

    error = payload.get("error") or {}
    message = error.get("message") or f"Meta API request failed with status {response.status_code}."
    code = error.get("code")

    if response.status_code == 401 or code == 190:
        message = "Invalid or expired API key."
    elif response.status_code == 429 or code in {4, 613, 130429}:
        message = "Meta rate limit reached. Please try again later."
    elif code == 100:
        message = "Wrong Phone Number ID or Business Account ID."

    return {
        "message": message,
        "status_code": response.status_code,
        "raw": error or payload,
    }


def environment_whatsapp_available():
    return bool(current_app.config.get("WHATSAPP_API_KEY")) and bool(
        current_app.config.get("WHATSAPP_PHONE_NUMBER_ID")
    )


def serialize_whatsapp_status(setting):
    if not setting:
        return {
            "status": "disconnected",
            "phone_number_id": "",
            "business_account_id": "",
            "api_key_saved": False,
            "api_key_masked": "",
            "verify_token_saved": False,
            "verify_token_masked": "",
            "last_error": "",
            "last_verified_at": None,
        }

    api_key = decrypt_secret(setting.api_key_encrypted)
    verify_token = decrypt_secret(setting.verify_token_encrypted)
    return {
        "status": setting.status,
        "phone_number_id": setting.phone_number_id or "",
        "business_account_id": setting.business_account_id or "",
        "api_key_saved": bool(setting.api_key_encrypted),
        "api_key_masked": mask_secret(api_key),
        "verify_token_saved": bool(setting.verify_token_encrypted),
        "verify_token_masked": mask_secret(verify_token),
        "last_error": setting.last_error or "",
        "last_verified_at": setting.last_verified_at.isoformat() if setting.last_verified_at else None,
    }


def resolve_whatsapp_credentials(user=None, allow_env_fallback=True):
    if user and getattr(user, "whatsapp_setting", None):
        setting = user.whatsapp_setting
        token = decrypt_secret(setting.api_key_encrypted)
        verify_token = decrypt_secret(setting.verify_token_encrypted)
        if (
            setting.status == "connected"
            and token
            and setting.phone_number_id
            and setting.business_account_id
        ):
            return {
                "source": "custom",
                "api_key": token,
                "phone_number_id": setting.phone_number_id,
                "business_account_id": setting.business_account_id,
                "verify_token": verify_token,
                "api_version": current_app.config.get("WHATSAPP_API_VERSION"),
            }

    if allow_env_fallback and environment_whatsapp_available():
        return {
            "source": "environment",
            "api_key": current_app.config.get("WHATSAPP_API_KEY"),
            "phone_number_id": current_app.config.get("WHATSAPP_PHONE_NUMBER_ID"),
            "business_account_id": current_app.config.get("WHATSAPP_BUSINESS_ACCOUNT_ID"),
            "verify_token": current_app.config.get("WHATSAPP_VERIFY_TOKEN"),
            "api_version": current_app.config.get("WHATSAPP_API_VERSION"),
        }

    return None


def verify_whatsapp_credentials(api_key, phone_number_id, business_account_id, api_version):
    headers = {"Authorization": f"Bearer {api_key}"}

    try:
        phone_response = requests.get(
            f"https://graph.facebook.com/{api_version}/{phone_number_id}",
            headers=headers,
            params={"fields": "id,display_phone_number,verified_name"},
            timeout=20,
        )
    except requests.RequestException as exc:
        return {
            "success": False,
            "message": "Network error while contacting Meta.",
            "details": str(exc),
        }

    if not phone_response.ok:
        error = parse_meta_error(phone_response)
        return {"success": False, "message": error["message"], "details": error}

    phone_payload = phone_response.json()

    try:
        account_response = requests.get(
            f"https://graph.facebook.com/{api_version}/{business_account_id}/phone_numbers",
            headers=headers,
            timeout=20,
        )
    except requests.RequestException as exc:
        return {
            "success": False,
            "message": "Network error while validating the Business Account ID.",
            "details": str(exc),
        }

    if not account_response.ok:
        error = parse_meta_error(account_response)
        return {"success": False, "message": error["message"], "details": error}

    account_payload = account_response.json()
    linked = any(
        str(item.get("id")) == str(phone_number_id)
        for item in account_payload.get("data", [])
    )
    if not linked:
        return {
            "success": False,
            "message": "Phone Number ID is not linked to this Business Account ID.",
            "details": account_payload,
        }

    return {
        "success": True,
        "metadata": {
            "display_phone_number": phone_payload.get("display_phone_number") or "",
            "verified_name": phone_payload.get("verified_name") or "",
        },
    }


def disconnect_whatsapp_settings(setting):
    setting.api_key_encrypted = None
    setting.phone_number_id = None
    setting.business_account_id = None
    setting.verify_token_encrypted = None
    setting.status = "disconnected"
    setting.last_error = None
    setting.last_verified_at = None


def _send_live_whatsapp_message(recipient, message, config):
    endpoint = f"https://graph.facebook.com/{config['api_version']}/{config['phone_number_id']}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": recipient,
        "type": "text",
        "text": {"body": message},
    }

    try:
        response = requests.post(
            endpoint,
            headers={
                "Authorization": f"Bearer {config['api_key']}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=30,
        )
    except requests.RequestException as exc:
        return {
            "success": False,
            "dry_run": False,
            "recipient": recipient,
            "source": config["source"],
            "mode": "live",
            "message": "Network error while contacting Meta.",
            "details": str(exc),
        }

    if not response.ok:
        error = parse_meta_error(response)
        return {
            "success": False,
            "dry_run": False,
            "recipient": recipient,
            "source": config["source"],
            "mode": "live",
            "message": error["message"],
            "details": error,
        }

    payload = response.json()
    external_id = ""
    if payload.get("messages"):
        external_id = payload["messages"][0].get("id", "")

    return {
        "success": True,
        "dry_run": False,
        "recipient": recipient,
        "source": config["source"],
        "mode": "live",
        "external_message_id": external_id,
        "response": payload,
    }


def send_whatsapp_message(
    recipient,
    message,
    user=None,
    allow_env_fallback=True,
    delivery_mode="auto",
):
    mode = (delivery_mode or "auto").strip().lower()
    if mode not in {"auto", "demo", "live"}:
        mode = "auto"

    if mode == "demo":
        return {
            "success": True,
            "dry_run": True,
            "recipient": recipient,
            "source": "demo",
            "mode": "demo",
            "message": "Demo mode enabled. Message logged without a real API send.",
        }

    config = resolve_whatsapp_credentials(user=user, allow_env_fallback=allow_env_fallback)
    if not config:
        if mode == "live":
            return {
                "success": False,
                "dry_run": False,
                "recipient": recipient,
                "source": "none",
                "mode": "live",
                "message": "Connect your WhatsApp API first.",
            }
        return {
            "success": True,
            "dry_run": True,
            "recipient": recipient,
            "source": "demo",
            "mode": "demo",
            "message": "No live credentials found. Message logged in demo mode.",
        }

    return _send_live_whatsapp_message(recipient=recipient, message=message, config=config)
