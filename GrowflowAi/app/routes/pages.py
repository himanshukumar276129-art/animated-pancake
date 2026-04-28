import json
from io import BytesIO

import qrcode
from flask import Blueprint, Response, current_app, render_template, url_for


pages_bp = Blueprint("pages", __name__)

APP_PAGES = [
    {
        "key": "dashboard",
        "endpoint": "pages.dashboard_page",
        "route": "/dashboard",
        "template": "dashboard.html",
        "label": "Dashboard Overview",
        "eyebrow": "Business Pulse",
        "description": "Track sales, attendance, activity, and jump into every GrowFlow module from one clear control room.",
        "badges": ["Overview", "Sales", "Activity"],
    },
    {
        "key": "employees",
        "endpoint": "pages.employees_page",
        "route": "/employees",
        "template": "employees.html",
        "label": "Employee Management",
        "eyebrow": "Team Workspace",
        "description": "Add, edit, and manage employee records with daily role visibility and quick attendance links.",
        "badges": ["CRUD", "Roles", "Records"],
    },
    {
        "key": "attendance",
        "endpoint": "pages.attendance_page",
        "route": "/attendance",
        "template": "attendance.html",
        "label": "Attendance System",
        "eyebrow": "Daily Tracking",
        "description": "Mark attendance, filter by date, and export structured logs for sheets and reporting.",
        "badges": ["Marking", "Logs", "Export"],
    },
    {
        "key": "customers",
        "endpoint": "pages.customers_page",
        "route": "/customers",
        "template": "customers.html",
        "label": "Customer Management",
        "eyebrow": "Relationship Desk",
        "description": "Capture customer contacts, maintain purchase context, and keep outreach lists ready.",
        "badges": ["Contacts", "History", "Import"],
    },
    {
        "key": "billing",
        "endpoint": "pages.billing_page",
        "route": "/billing",
        "template": "billing.html",
        "label": "Billing & Payments",
        "eyebrow": "Revenue Desk",
        "description": "Generate invoices, update payment status, and review billing history with optional WhatsApp follow-up.",
        "badges": ["Invoices", "Payments", "History"],
    },
    {
        "key": "whatsapp",
        "endpoint": "pages.whatsapp_page",
        "route": "/whatsapp",
        "template": "whatsapp.html",
        "label": "WhatsApp Marketing",
        "eyebrow": "Campaign Console",
        "description": "Manage client-owned WhatsApp credentials, send campaigns, and review delivery history in one workspace.",
        "badges": ["API", "Bulk Send", "Automation"],
    },
    {
        "key": "whatsapp-settings",
        "endpoint": "pages.whatsapp_settings_page",
        "route": "/whatsapp/settings",
        "template": "whatsapp-settings.html",
        "label": "WhatsApp Settings",
        "eyebrow": "Connection Vault",
        "description": "Store encrypted client credentials, test Meta connectivity, and keep the live connection status visible.",
        "badges": ["Encrypted", "Verify", "Secure"],
    },
    {
        "key": "whatsapp-dashboard",
        "endpoint": "pages.whatsapp_dashboard_page",
        "route": "/whatsapp/dashboard",
        "template": "whatsapp-dashboard.html",
        "label": "WhatsApp Dashboard",
        "eyebrow": "Messaging Hub",
        "description": "Send single or bulk messages, manage templates, and track message delivery history.",
        "badges": ["Send", "Templates", "History"],
    },
    {
        "key": "ai-tools",
        "endpoint": "pages.ai_tools_page",
        "route": "/ai-tools",
        "template": "ai-tools.html",
        "label": "AI Poster Generator",
        "eyebrow": "Creative Assist",
        "description": "Generate posters, captions, and promotional messages tuned for local-business campaigns.",
        "badges": ["Poster", "Caption", "Offers"],
    },
    {
        "key": "api-settings",
        "endpoint": "pages.api_settings_page",
        "route": "/api-settings",
        "template": "api-settings.html",
        "label": "API Key Management",
        "eyebrow": "Integration Vault",
        "description": "Store encrypted API keys, review masked credentials, and run lightweight connection checks.",
        "badges": ["Encrypted", "Masked", "Testing"],
    },
    {
        "key": "database",
        "endpoint": "pages.database_page",
        "route": "/database",
        "template": "database.html",
        "label": "Database Management",
        "eyebrow": "Data Control",
        "description": "View data summary, create backups, export files, and restore or clear business data safely.",
        "badges": ["Backup", "Export", "Restore"],
    },
    {
        "key": "analytics",
        "endpoint": "pages.analytics_page",
        "route": "/analytics",
        "template": "analytics.html",
        "label": "Analytics",
        "eyebrow": "Growth Insights",
        "description": "Visualize sales momentum, customer trends, and communication performance in one place.",
        "badges": ["Charts", "Growth", "Trends"],
    },
    {
        "key": "subscription",
        "endpoint": "pages.subscription_page",
        "route": "/subscription",
        "template": "subscription.html",
        "label": "Subscription Plans",
        "eyebrow": "Plan Control",
        "description": "Track your 7-day trial, apply promo codes, upgrade to Pro, and review billing history without leaving the workspace.",
        "badges": ["Trial", "Pro", "Billing"],
    },
    {
        "key": "settings",
        "endpoint": "pages.settings_page",
        "route": "/settings",
        "template": "settings.html",
        "label": "Settings",
        "eyebrow": "Account Controls",
        "description": "Manage profile details, theme preferences, session security, and account-level behavior.",
        "badges": ["Profile", "Theme", "Security"],
    },
    {
        "key": "support",
        "endpoint": "pages.support_page",
        "route": "/support",
        "template": "support.html",
        "label": "Help & Support",
        "eyebrow": "Guided Support",
        "description": "Use onboarding guides, FAQs, and direct contact options built for local business owners.",
        "badges": ["FAQ", "Guides", "Contact"],
    },
]

APP_PAGE_LOOKUP = {page["key"]: page for page in APP_PAGES}


def build_app_context(page_key):
    current_page = APP_PAGE_LOOKUP[page_key]
    return {
        "app_pages": APP_PAGES,
        "auth_required": True,
        "body_page": page_key,
        "breadcrumbs": [
            {"label": "Workspace", "href": url_for("pages.dashboard_page")},
            {"label": current_page["label"], "href": current_page["route"]},
        ],
        "current_page": current_page,
        "page_title": f"GrowFlow AI | {current_page['label']}",
        "support_email": current_app.config.get("SUPPORT_EMAIL", "support@growflowai.app"),
        "support_phone": current_app.config.get("SUPPORT_PHONE", "+91 90000 00000"),
    }


def render_app_page(page_key):
    page = APP_PAGE_LOOKUP[page_key]
    return render_template(page["template"], **build_app_context(page_key))


@pages_bp.get("/")
def landing_page():
    return render_template("index.html", body_page="landing", auth_required=False)


@pages_bp.get("/auth")
def auth_page():
    return render_template(
        "auth.html",
        body_page="auth",
        auth_required=False,
        support_email=current_app.config.get("SUPPORT_EMAIL", "support@growflowai.app"),
        supabase_url=current_app.config.get("SUPABASE_URL", ""),
        supabase_key=current_app.config.get("SUPABASE_KEY", ""),
        supabase_enabled=bool(
            current_app.config.get("SUPABASE_URL") and current_app.config.get("SUPABASE_KEY")
        ),
    )


@pages_bp.get("/dashboard")
def dashboard_page():
    return render_app_page("dashboard")


@pages_bp.get("/app")
def app_home_page():
    return render_app_page("dashboard")


@pages_bp.get("/employees")
def employees_page():
    return render_app_page("employees")


@pages_bp.get("/attendance")
def attendance_page():
    return render_app_page("attendance")


@pages_bp.get("/customers")
def customers_page():
    return render_app_page("customers")


@pages_bp.get("/billing")
def billing_page():
    return render_app_page("billing")


@pages_bp.get("/whatsapp")
def whatsapp_page():
    return render_app_page("whatsapp")


@pages_bp.get("/whatsapp/settings")
def whatsapp_settings_page():
    return render_app_page("whatsapp-settings")


@pages_bp.get("/whatsapp/dashboard")
def whatsapp_dashboard_page():
    return render_app_page("whatsapp-dashboard")


@pages_bp.get("/ai-tools")
def ai_tools_page():
    return render_app_page("ai-tools")


@pages_bp.get("/api-settings")
def api_settings_page():
    return render_app_page("api-settings")


@pages_bp.get("/database")
def database_page():
    return render_app_page("database")


@pages_bp.get("/analytics")
def analytics_page():
    return render_app_page("analytics")


@pages_bp.get("/subscription")
def subscription_page():
    return render_app_page("subscription")


@pages_bp.get("/settings")
def settings_page():
    return render_app_page("settings")


@pages_bp.get("/support")
def support_page():
    return render_app_page("support")


@pages_bp.get("/health")
def health_check():
    return {"status": "ok", "app": "GrowFlow AI"}


@pages_bp.get("/qr/onboarding")
def onboarding_qr():
    qr = qrcode.QRCode(box_size=8, border=2)
    qr.add_data("https://growflowai.app/auth")
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return Response(buffer.getvalue(), mimetype="image/png")


@pages_bp.get("/manifest.webmanifest")
def manifest_webmanifest():
    icon_png = url_for("static", filename="img/20851361-e614-4795-8051-7a6b75d3d2c3-removebg-preview.png")
    icon_svg = url_for("static", filename="img/growflow-logo.svg")
    manifest = {
        "name": "GrowFlow AI",
        "short_name": "GrowFlow",
        "description": "Mobile-first SaaS workspace for sales, staff, billing, WhatsApp, analytics, and AI.",
        "id": "/dashboard",
        "start_url": url_for("pages.dashboard_page"),
        "scope": "/",
        "display": "standalone",
        "orientation": "any",
        "background_color": "#07120d",
        "theme_color": "#07120d",
        "categories": ["business", "productivity"],
        "icons": [
            {
                "src": icon_png,
                "sizes": "192x192",
                "type": "image/png",
                "purpose": "any",
            },
            {
                "src": icon_png,
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "any",
            },
            {
                "src": icon_svg,
                "sizes": "any",
                "type": "image/svg+xml",
                "purpose": "any",
            },
        ],
        "shortcuts": [
            {
                "name": "Dashboard",
                "short_name": "Dashboard",
                "description": "Open the business overview and live metrics.",
                "url": url_for("pages.dashboard_page"),
                "icons": [
                    {
                        "src": icon_png,
                        "sizes": "192x192",
                        "type": "image/png",
                    }
                ],
            },
            {
                "name": "WhatsApp",
                "short_name": "WhatsApp",
                "description": "Jump into messaging and campaign tools.",
                "url": url_for("pages.whatsapp_dashboard_page"),
                "icons": [
                    {
                        "src": icon_png,
                        "sizes": "192x192",
                        "type": "image/png",
                    }
                ],
            },
            {
                "name": "Subscription",
                "short_name": "Billing",
                "description": "Review trial, plan, and payment state.",
                "url": url_for("pages.subscription_page"),
                "icons": [
                    {
                        "src": icon_png,
                        "sizes": "192x192",
                        "type": "image/png",
                    }
                ],
            },
            {
                "name": "Support",
                "short_name": "Support",
                "description": "Open onboarding and help resources.",
                "url": url_for("pages.support_page"),
                "icons": [
                    {
                        "src": icon_png,
                        "sizes": "192x192",
                        "type": "image/png",
                    }
                ],
            },
        ],
    }
    response = current_app.response_class(
        json.dumps(manifest, separators=(",", ":")),
        mimetype="application/manifest+json",
    )
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response


@pages_bp.get("/sw.js")
def service_worker():
    response = current_app.send_static_file("sw.js")
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response
