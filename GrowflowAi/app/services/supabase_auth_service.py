import os

import requests
from flask import current_app


def resolve_supabase_url():
    return (
        current_app.config.get("SUPABASE_URL")
        or os.getenv("SUPABASE_URL")
        or ""
    ).strip().rstrip("/")


def resolve_supabase_key():
    return (
        current_app.config.get("SUPABASE_KEY")
        or os.getenv("SUPABASE_KEY")
        or ""
    ).strip()


def supabase_auth_configured():
    return bool(resolve_supabase_url() and resolve_supabase_key())


def verify_supabase_access_token(access_token):
    url = resolve_supabase_url()
    key = resolve_supabase_key()

    if not url or not key:
        return {
            "success": False,
            "message": "Supabase authentication is not configured.",
            "status": "not_configured",
        }

    if not access_token:
        return {
            "success": False,
            "message": "Supabase access token is required.",
            "status": "missing_token",
        }

    try:
        response = requests.get(
            f"{url}/auth/v1/user",
            headers={
                "apikey": key,
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            timeout=15,
        )
    except requests.Timeout:
        return {
            "success": False,
            "message": "Supabase session verification timed out.",
            "status": "timeout",
        }
    except requests.RequestException as exc:
        return {
            "success": False,
            "message": "Supabase session verification failed.",
            "status": "error",
            "details": str(exc),
        }

    payload = {}
    if response.text:
        try:
            payload = response.json()
        except ValueError:
            payload = {}

    if response.ok and isinstance(payload, dict):
        return {
            "success": True,
            "status": "verified",
            "user": payload,
        }

    error_message = (
        payload.get("msg")
        or payload.get("error_description")
        or payload.get("message")
        or "Supabase session verification failed."
    )
    status = "unauthorized" if response.status_code in {401, 403} else "error"
    return {
        "success": False,
        "message": error_message,
        "status": status,
        "http_status": response.status_code,
        "details": payload or response.text or error_message,
    }
