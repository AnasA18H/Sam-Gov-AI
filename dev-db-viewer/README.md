# Dev DB Viewer (temporary)

Standalone, **separate** from the main frontend/backend. Live view of all database tables to verify data and debug.

## Run

**Option A – with start.sh (recommended)**  
From project root, run `./start.sh`. The DB viewer starts automatically (using the project venv) and is stopped by `./stop.sh` or Ctrl+C. Open **http://localhost:5050** (or set `DB_VIEWER_PORT` to use another port).

**Option B – manually**  
1. From project root, ensure DB is running and `.env` has `DATABASE_URL` (or it defaults to `postgresql://postgres:postgres@localhost:5432/samgov_db`).
2. Run the viewer (project venv has dependencies):
   ```bash
   cd dev-db-viewer
   pip install -r requirements.txt   # or use project venv
   python server.py
   ```
   Or from project root: `./venv/bin/python dev-db-viewer/server.py`
3. Open **http://localhost:5050** in a browser (or `http://localhost:${DB_VIEWER_PORT}` if set).
4. Use **Refresh** to reload data from the DB.

## What it shows

- **users** – id, email, auth_provider (email | google | microsoft), full_name, role, is_verified, etc. (`password_hash` masked)
- **sessions** – user_id, is_active, expires_at, etc. (`token`, `refresh_token` masked)
- **user_email_connections** – user_id, provider (google | microsoft), sender_email, etc. (tokens masked)
- **oauth_states** – temporary OAuth state for sign-in/connect. **Both Google and Microsoft** use this table:
  - **state** – random token sent to provider, validated on callback
  - **user_id** – `0` = sign-in (no user yet), otherwise = connect flow (existing user)
  - **provider** – `google` or `microsoft`
  - Rows are **deleted** when the OAuth callback runs. Any row you see is either an in-progress flow or an abandoned one (user closed the window before callback). Backend also deletes states older than 15 minutes when starting a new flow.
- **opportunities** – full rows (`user_id`, `sam_gov_url`; unique per user so same URL can exist for different users)
- **documents** – full rows
- **deadlines** – full rows
- **clins** – full rows (including JSON columns)
- **draft_quote_emails** – persisted quote email drafts per opportunity (to, to_name, subject, body, contact_type, clin_number); generate saves, send/discard delete.

Sensitive fields are replaced with `***`. Remove this app or restrict access when not developing.
