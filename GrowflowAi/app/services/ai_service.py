import html
import os

import requests
from flask import current_app


DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"
GROQ_CHAT_COMPLETIONS_PATH = "/chat/completions"


def build_poster_svg(headline, subline, cta):
    safe_headline = html.escape(headline[:48] or "Grow your business")
    safe_subline = html.escape(subline[:84] or "Smart marketing for local businesses")
    safe_cta = html.escape(cta[:32] or "Start with GrowFlow AI")
    return f"""
<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="1080" viewBox="0 0 1080 1080" fill="none">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#04110c"/>
      <stop offset="100%" stop-color="#0d221a"/>
    </linearGradient>
    <linearGradient id="glow" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="#65ff9a"/>
      <stop offset="100%" stop-color="#15c862"/>
    </linearGradient>
  </defs>
  <rect width="1080" height="1080" fill="url(#bg)"/>
  <circle cx="170" cy="160" r="120" fill="#3CFF91" fill-opacity="0.10"/>
  <circle cx="920" cy="240" r="180" fill="#3CFF91" fill-opacity="0.08"/>
  <rect x="88" y="96" width="904" height="888" rx="42" fill="#071711" stroke="#2af07b" stroke-opacity="0.25"/>
  <text x="120" y="240" fill="#6EFFA4" font-size="30" font-family="Arial, Helvetica, sans-serif">GrowFlow AI Poster</text>
  <text x="120" y="390" fill="white" font-size="92" font-weight="700" font-family="Arial, Helvetica, sans-serif">{safe_headline}</text>
  <text x="120" y="500" fill="#D1FADF" font-size="38" font-family="Arial, Helvetica, sans-serif">{safe_subline}</text>
  <rect x="120" y="650" width="360" height="78" rx="20" fill="url(#glow)"/>
  <text x="162" y="700" fill="#062313" font-size="32" font-weight="700" font-family="Arial, Helvetica, sans-serif">{safe_cta}</text>
  <text x="120" y="890" fill="#8CB89B" font-size="24" font-family="Arial, Helvetica, sans-serif">AI marketing - billing - attendance - customer growth</text>
</svg>
""".strip()


def resolve_ai_api_key(api_key_override=None):
    value = (
        api_key_override
        or current_app.config.get("GROQ_API_KEY")
        or os.getenv("GROQ_API_KEY")
        or current_app.config.get("OPENAI_API_KEY")
        or os.getenv("OPENAI_API_KEY")
        or ""
    )
    return str(value).strip()


def resolve_ai_model(model_override=None):
    return (
        model_override
        or current_app.config.get("GROQ_MODEL")
        or os.getenv("GROQ_MODEL")
        or current_app.config.get("OPENAI_MODEL")
        or os.getenv("OPENAI_MODEL")
        or DEFAULT_GROQ_MODEL
    )


def resolve_ai_base_url():
    return (
        current_app.config.get("GROQ_BASE_URL")
        or os.getenv("GROQ_BASE_URL")
        or "https://api.groq.com/openai/v1"
    ).rstrip("/")


def resolve_ai_timeout():
    try:
        return int(current_app.config.get("GROQ_TIMEOUT_SECONDS", 25))
    except (TypeError, ValueError):
        return 25


def extract_response_text(payload):
    choices = payload.get("choices") or []
    if not choices:
        return ""

    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        chunks = []
        for item in content:
            if isinstance(item, dict) and item.get("type") in {"output_text", "text"} and item.get("text"):
                chunks.append(str(item["text"]).strip())
        return "\n".join(chunk for chunk in chunks if chunk).strip()
    return ""


def build_fallback_content(business_name, content_type, prompt, warning=""):
    brand = business_name or "your business"
    request = prompt or "promote your latest offer"
    if content_type == "poster":
        content = (
            f"{brand} Mega Offer\n"
            f"Highlight: {request}\n"
            "Visit today for fast service, trusted staff, and local support."
        )
    elif content_type == "marketing":
        content = (
            f"Hello from {brand}. {request}. "
            "Reply now to book your slot or ask for today's pricing."
        )
    else:
        content = (
            f"{brand} is ready to help. {request}. "
            "Trusted service, fast response, and simple support for every customer."
        )

    return {
        "content": content,
        "poster_svg": build_poster_svg(
            headline=brand,
            subline=request,
            cta="Book Now",
        )
        if content_type == "poster"
        else None,
        "provider": "fallback",
        "status": "degraded",
        "used_fallback": True,
        "warning": warning,
    }


def build_generation_messages(business_name, content_type, prompt):
    system_prompt = (
        "You create concise, high-converting marketing content for local businesses. "
        "Return only useful text. Keep it practical and easy for Indian local-business owners to use."
    )
    user_prompt = (
        f"Business name: {business_name or 'GrowFlow client'}\n"
        f"Content type: {content_type}\n"
        f"Goal: {prompt}\n"
        "If the content type is poster, write exactly 3 short lines: headline, offer, CTA."
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def request_groq_completion(api_key, model, messages, max_tokens=220):
    response = requests.post(
        f"{resolve_ai_base_url()}{GROQ_CHAT_COMPLETIONS_PATH}",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.7,
        },
        timeout=resolve_ai_timeout(),
    )
    response.raise_for_status()
    return response.json()


def test_ai_provider_connection(api_key, model=None):
    resolved_key = resolve_ai_api_key(api_key)
    if not resolved_key:
        return {
            "success": False,
            "message": "GROQ_API_KEY is not configured.",
            "provider": "groq",
            "status": "not_configured",
        }

    resolved_model = resolve_ai_model(model)
    try:
        payload = request_groq_completion(
            api_key=resolved_key,
            model=resolved_model,
            messages=[
                {"role": "system", "content": "Reply with one short word only."},
                {"role": "user", "content": "OK"},
            ],
            max_tokens=8,
        )
        sample = extract_response_text(payload) or "OK"
        return {
            "success": True,
            "message": "Groq API connection verified.",
            "provider": "groq",
            "status": "connected",
            "model": resolved_model,
            "sample": sample[:80],
        }
    except requests.Timeout:
        return {
            "success": False,
            "message": "Groq API request timed out.",
            "provider": "groq",
            "status": "timeout",
        }
    except requests.HTTPError as exc:
        status_code = exc.response.status_code if exc.response is not None else None
        error_body = {}
        try:
            error_body = exc.response.json() if exc.response is not None else {}
        except ValueError:
            error_body = {}
        error_message = (
            error_body.get("error", {}).get("message")
            or error_body.get("message")
            or "Groq API request failed."
        )
        if status_code in {401, 403}:
            status = "unauthorized"
            message = "Groq API key is invalid or expired."
        elif status_code == 429:
            status = "rate_limited"
            message = "Groq API rate limit reached."
        elif status_code and status_code >= 500:
            status = "provider_down"
            message = "Groq API is temporarily unavailable."
        else:
            status = "error"
            message = error_message
        return {
            "success": False,
            "message": message,
            "provider": "groq",
            "status": status,
            "details": error_message,
            "http_status": status_code,
        }
    except requests.RequestException as exc:
        return {
            "success": False,
            "message": "Groq API request failed.",
            "provider": "groq",
            "status": "error",
            "details": str(exc),
        }


def generate_business_content(business_name, content_type, prompt, api_key_override=None, model_override=None):
    resolved_key = resolve_ai_api_key(api_key_override)
    resolved_model = resolve_ai_model(model_override)

    if not resolved_key:
        return build_fallback_content(
            business_name,
            content_type,
            prompt,
            warning="Groq API key is not configured. Using local fallback content.",
        )

    try:
        payload = request_groq_completion(
            api_key=resolved_key,
            model=resolved_model,
            messages=build_generation_messages(business_name, content_type, prompt),
        )
        text = extract_response_text(payload)
        if not text:
            raise ValueError("Groq returned an empty completion.")

        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return {
            "content": text,
            "poster_svg": build_poster_svg(
                headline=lines[0] if lines else business_name or "GrowFlow AI",
                subline=lines[1] if len(lines) > 1 else prompt,
                cta=lines[2] if len(lines) > 2 else "Message Us",
            )
            if content_type == "poster"
            else None,
            "provider": "groq",
            "status": "ok",
            "used_fallback": False,
            "model": resolved_model,
        }
    except requests.Timeout:
        return build_fallback_content(
            business_name,
            content_type,
            prompt,
            warning="Groq API request timed out. Using local fallback content.",
        )
    except requests.HTTPError as exc:
        status_code = exc.response.status_code if exc.response is not None else None
        if status_code in {401, 403}:
            warning = "Groq API key is invalid or expired. Using local fallback content."
        elif status_code == 429:
            warning = "Groq API rate limit reached. Using local fallback content."
        elif status_code and status_code >= 500:
            warning = "Groq API is temporarily unavailable. Using local fallback content."
        else:
            warning = "Groq API request failed. Using local fallback content."
        return build_fallback_content(business_name, content_type, prompt, warning=warning)
    except (requests.RequestException, ValueError) as exc:
        return build_fallback_content(
            business_name,
            content_type,
            prompt,
            warning=f"Groq request failed: {exc}. Using local fallback content.",
        )
