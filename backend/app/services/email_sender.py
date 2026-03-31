"""
Send email on behalf of the user via Gmail API or Microsoft Graph.
Uses stored OAuth tokens (UserEmailConnection).
"""
import base64
import logging
from email.mime.text import MIMEText
from typing import Optional, cast

from ..core.config import settings
from ..models.user_email_connection import UserEmailConnection

logger = logging.getLogger(__name__)


def _get_valid_access_token_gmail(conn: UserEmailConnection) -> Optional[str]:
    """Refresh and return access token for Google."""
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
    except ImportError:
        logger.warning("google-auth not available for Gmail send")
        return None
    creds = Credentials(
        token=conn.access_token,
        refresh_token=conn.refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
        scopes=["https://www.googleapis.com/auth/gmail.send"],
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return cast(Optional[str], creds.token)


def _send_via_gmail(conn: UserEmailConnection, to: str, subject: str, body: str) -> bool:
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except ImportError:
        logger.warning("google-api-python-client not available")
        return False
    token = _get_valid_access_token_gmail(conn)
    if not token:
        return False
    creds = Credentials(token=token)
    service = build("gmail", "v1", credentials=creds)
    subtype = "html" if ("<" in body and ">" in body) else "plain"
    message = MIMEText(body, subtype)
    message["to"] = to
    message["subject"] = subject
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    service.users().messages().send(userId="me", body={"raw": raw}).execute()
    return True


def _get_valid_access_token_microsoft(conn: UserEmailConnection) -> Optional[str]:
    """Refresh and return access token for Microsoft Graph."""
    try:
        import msal
    except ImportError:
        return None
    tenant = getattr(settings, "MICROSOFT_TENANT_ID", None) or "common"
    authority = f"https://login.microsoftonline.com/{tenant}"
    app = msal.ConfidentialClientApplication(
        settings.MICROSOFT_CLIENT_ID,
        authority=authority,
        client_credential=settings.MICROSOFT_CLIENT_SECRET,
    )
    result = app.acquire_token_by_refresh_token(conn.refresh_token, scopes=["https://graph.microsoft.com/Mail.Send"])
    return result.get("access_token") if isinstance(result, dict) else None


def _send_via_microsoft(conn: UserEmailConnection, to: str, subject: str, body: str) -> bool:
    import requests
    token = _get_valid_access_token_microsoft(conn)
    if not token:
        return False
    sender = conn.sender_email or "me"
    content_type = "HTML" if ("<" in body and ">" in body) else "Text"
    payload = {
        "message": {
            "subject": subject,
            "body": {"contentType": content_type, "content": body},
            "toRecipients": [{"emailAddress": {"address": to}}],
        },
        "saveToSentItems": True,
    }
    r = requests.post(
        "https://graph.microsoft.com/v1.0/me/sendMail",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=payload,
        timeout=30,
    )
    if r.status_code in (200, 202):
        return True
    logger.warning("Microsoft Graph sendMail failed: %s %s", r.status_code, r.text)
    return False


def send_email_as_user(conn: UserEmailConnection, to: str, subject: str, body: str) -> bool:
    """Send email using the user's connected account (Gmail or Microsoft)."""
    provider = str(conn.provider) if conn.provider is not None else ""
    if provider == "google":
        return _send_via_gmail(conn, to, subject, body)
    if provider == "microsoft":
        return _send_via_microsoft(conn, to, subject, body)
    return False
