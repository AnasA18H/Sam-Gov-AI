"""
Temporary dev-only DB viewer. Standalone app – separate from main frontend/backend.
Run: cd dev-db-viewer && pip install -r requirements.txt && python server.py
Then open http://localhost:5050
"""
import os
import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import psycopg2
from psycopg2.extras import RealDictCursor

# Load .env from project root if present
_env_path = Path(__file__).resolve().parent.parent / ".env"
if _env_path.exists():
    with open(_env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip()
                if v.startswith('"') and v.endswith('"') or v.startswith("'") and v.endswith("'"):
                    v = v[1:-1]
                os.environ.setdefault(k, v)

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/samgov_db")
PORT = int(os.getenv("DB_VIEWER_PORT", "5050"))

# Columns to mask (show "***" instead of value)
MASK_COLUMNS = {
    "users": ["password_hash"],
    "sessions": ["token", "refresh_token"],
    "user_email_connections": ["refresh_token", "access_token"],
    "oauth_states": [],
}

TABLES_ORDER = [
    "users",
    "sessions",
    "user_email_connections",
    "oauth_states",
    "opportunities",
    "documents",
    "deadlines",
    "clins",
    "draft_quote_emails",
]

app = FastAPI(title="Dev DB Viewer", docs_url=None, redoc_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_connection():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)


# Table-specific ORDER BY (default: id). Use tuple (order_col, direction) for custom.
TABLE_ORDER_BY = {
    "opportunities": ("id", "DESC"),  # newest first
    "documents": ("id", "DESC"),
    "deadlines": ("id", "DESC"),
    "clins": ("id", "ASC"),
    "draft_quote_emails": ("id", "DESC"),
}


def row_to_dict(row, table):
    d = dict(row)
    for col in MASK_COLUMNS.get(table, []):
        if col in d and d[col] is not None:
            d[col] = "***"
    # Serialize dates and decimals
    for k, v in list(d.items()):
        if hasattr(v, "isoformat"):
            d[k] = v.isoformat()
        elif hasattr(v, "__float__") and not isinstance(v, (int, float)):
            d[k] = float(v) if v is not None else None
    return d


@app.get("/api/dump")
def api_dump():
    """Return all tables as JSON. Sensitive columns masked."""
    data = {}
    try:
        conn = get_connection()
        cur = conn.cursor()
        for table in TABLES_ORDER:
            try:
                order_spec = TABLE_ORDER_BY.get(table)
                if order_spec:
                    order_col, direction = order_spec
                    cur.execute(f'SELECT * FROM "{table}" ORDER BY "{order_col}" {direction}')
                else:
                    cur.execute(f'SELECT * FROM "{table}" ORDER BY id')
                rows = cur.fetchall()
                data[table] = [row_to_dict(r, table) for r in rows]
            except Exception as e:
                data[table] = {"_error": str(e)}
        cur.close()
        conn.close()
    except Exception as e:
        return JSONResponse({"error": str(e), "hint": "Check DATABASE_URL and that DB is running."}, status_code=500)
    return data


@app.get("/", response_class=HTMLResponse)
def index():
    """Serve the single-page viewer."""
    html_path = Path(__file__).parent / "index.html"
    return HTMLResponse(html_path.read_text())


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
