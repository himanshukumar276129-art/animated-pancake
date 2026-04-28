# GrowFlow AI

GrowFlow AI is a full-stack Flask SaaS starter for local businesses. It combines attendance, customers, billing, WhatsApp marketing, dashboard analytics, authentication, and AI-generated marketing content in one mobile-friendly dashboard.

## Included

- Landing page with hero, feature grid, pricing, QR onboarding, and contact/support sections
- Supabase email/password authentication with backend JWT session exchange
- Local fallback auth routes retained for development compatibility
- SQLite development database with PostgreSQL-ready configuration
- Employee, attendance, customer, invoice, marketing log, and subscription models
- Dashboard analytics with weekly growth chart
- WhatsApp Cloud API integration with safe dry-run fallback when credentials are missing
- Per-user encrypted WhatsApp API settings with connect, disconnect, status, and test message flows
- Groq API integration with secure backend-only credential handling and fallback content generation when credentials are missing
- Installable PWA shell with home-screen support, offline basic mode, browser notifications, and cached app assets
- Mobile-first responsive shell with a drawer navigation pattern for phones and tablets
## Local Run

1. Create a virtual environment and activate it.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Copy `.env.example` to `.env` and fill in any optional API keys.
4. Start the app:

```bash
python app.py
```

5. Open `http://127.0.0.1:5000`

## Environment Variables

- `SECRET_KEY`
- `JWT_SECRET_KEY`
- `DATABASE_URL`
- `SUPABASE_URL`
- `SUPABASE_KEY`
- `GROQ_API_KEY`
- `GROQ_MODEL`
- `GROQ_BASE_URL`
- `GROQ_TIMEOUT_SECONDS`
- `OPENAI_API_KEY`
- `OPENAI_MODEL`
- `WHATSAPP_API_KEY`
- `WHATSAPP_PHONE_NUMBER_ID`
- `WHATSAPP_BUSINESS_ACCOUNT_ID`
- `WHATSAPP_VERIFY_TOKEN`
- `WHATSAPP_API_VERSION`
- `WHATSAPP_SETTINGS_ENCRYPTION_KEY`

## Deployment Notes

- Frontend can remain served by Flask for simple deployment.
- Backend is ready for Render or Railway using `python app.py` or a WSGI entrypoint.
- Set `DATABASE_URL` to a PostgreSQL connection string in production.
- Set `SUPABASE_URL` and `SUPABASE_KEY` so the authentication page can verify sign-ins and exchange them for GrowFlow sessions.
- If you split frontend later, keep the `/api/*` routes on the Flask service and point the UI to that backend.
