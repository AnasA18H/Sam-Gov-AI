"""
Sync opportunity deadlines to user's Google Calendar or Microsoft Outlook Calendar.
Creates calendar events for extracted solicitation due dates. Persists event ids to avoid duplicates.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple, List

from ..core.config import settings
from ..models.user_email_connection import UserEmailConnection
from ..models.deadline import Deadline

logger = logging.getLogger(__name__)


def _get_google_calendar_credentials(conn: UserEmailConnection):
    """Build full Google Credentials (with refresh_token, client_id, client_secret) and refresh if expired. Returns None if unavailable."""
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
    except ImportError:
        logger.warning("google-auth not available for Calendar sync")
        return None
    if not getattr(settings, "GOOGLE_CLIENT_ID", None) or not getattr(settings, "GOOGLE_CLIENT_SECRET", None):
        logger.warning("Google OAuth client_id/client_secret not configured; cannot sync to Google Calendar")
        return None
    if not conn.refresh_token:
        logger.warning("User email connection has no refresh_token; cannot refresh Google Calendar token")
        return None
    creds = Credentials(
        token=conn.access_token or None,
        refresh_token=conn.refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
        scopes=["https://www.googleapis.com/auth/calendar.events"],
    )
    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception as e:
            logger.warning("Failed to refresh Google Calendar token: %s", e)
            return None
    return creds


def _get_google_calendar_token(conn: UserEmailConnection) -> Optional[str]:
    """Refresh and return access token for Google (calendar scope)."""
    creds = _get_google_calendar_credentials(conn)
    return creds.token if creds else None


def _create_google_calendar_event(
    conn: UserEmailConnection,
    due_date: datetime,
    summary: str,
    description: Optional[str] = None,
) -> Optional[str]:
    """Create a calendar event in Google Calendar. Returns event id or None."""
    try:
        from googleapiclient.discovery import build
    except ImportError:
        return None
    creds = _get_google_calendar_credentials(conn)
    if not creds:
        return None
    # Ensure timezone-aware
    if due_date.tzinfo is None:
        due_date = due_date.replace(tzinfo=timezone.utc)
    end_date = due_date + timedelta(hours=1)
    body = {
        "summary": summary,
        "description": description or "",
        "start": {"dateTime": due_date.isoformat(), "timeZone": "UTC"},
        "end": {"dateTime": end_date.isoformat(), "timeZone": "UTC"},
    }
    service = build("calendar", "v3", credentials=creds)
    event = service.events().insert(calendarId="primary", body=body).execute()
    return event.get("id")


def _get_microsoft_calendar_token(conn: UserEmailConnection) -> Optional[str]:
    """Refresh and return access token for Microsoft Graph (Calendars.ReadWrite)."""
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
    result = app.acquire_token_by_refresh_token(
        conn.refresh_token,
        scopes=["https://graph.microsoft.com/Calendars.ReadWrite"],
    )
    return result.get("access_token") if isinstance(result, dict) else None


def _create_microsoft_calendar_event(
    conn: UserEmailConnection,
    due_date: datetime,
    summary: str,
    description: Optional[str] = None,
) -> Optional[str]:
    """Create a calendar event in Microsoft Outlook. Returns event id or None."""
    import requests
    token = _get_microsoft_calendar_token(conn)
    if not token:
        return None
    if due_date.tzinfo is None:
        due_date = due_date.replace(tzinfo=timezone.utc)
    end_date = due_date + timedelta(hours=1)
    # Graph API expects ISO 8601
    payload = {
        "subject": summary,
        "body": {"contentType": "text", "content": description or ""},
        "start": {"dateTime": due_date.isoformat(), "timeZone": "UTC"},
        "end": {"dateTime": end_date.isoformat(), "timeZone": "UTC"},
    }
    r = requests.post(
        "https://graph.microsoft.com/v1.0/me/events",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=payload,
        timeout=45,
    )
    if r.status_code in (200, 201):
        data = r.json()
        return data.get("id")
    logger.warning("Microsoft Graph create event failed: %s %s", r.status_code, r.text)
    return None


def create_calendar_event_for_deadline(
    conn: UserEmailConnection,
    deadline: Deadline,
    opportunity_title: Optional[str] = None,
    delivery_timeline: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """
    Create a single calendar event for a deadline. Returns (event_id, provider) or (None, None).
    delivery_timeline: optional free-text string (e.g. from CLINs) included in the event description.
    """
    title = opportunity_title or "Opportunity"
    summary = f"{deadline.deadline_type or 'Deadline'}: {title}"
    desc_parts = [deadline.description] if deadline.description else []
    if deadline.due_time:
        desc_parts.append(f"Time: {deadline.due_time}")
    if deadline.timezone:
        desc_parts.append(f"Timezone: {deadline.timezone}")
    if deadline.location:
        desc_parts.append(f"Location: {deadline.location}")
    if delivery_timeline and isinstance(delivery_timeline, str) and delivery_timeline.strip():
        desc_parts.append(f"Delivery: {delivery_timeline.strip()}")
    description = "\n".join(filter(None, desc_parts)) or None

    due_date = deadline.due_date
    if due_date.tzinfo is None:
        due_date = due_date.replace(tzinfo=timezone.utc)

    if conn.provider == "google":
        event_id = _create_google_calendar_event(conn, due_date, summary, description)
        return (event_id, "google" if event_id else None)
    if conn.provider == "microsoft":
        event_id = _create_microsoft_calendar_event(conn, due_date, summary, description)
        return (event_id, "microsoft" if event_id else None)
    return (None, None)


def sync_deadlines_to_calendar(
    conn: UserEmailConnection,
    deadlines: List[Deadline],
    opportunity_title: Optional[str] = None,
    delivery_timeline: Optional[str] = None,
) -> int:
    """
    Create calendar events for deadlines that don't already have calendar_event_id.
    Updates each deadline with calendar_event_id and calendar_provider.
    delivery_timeline: optional string (e.g. aggregated from opportunity CLINs) added to each event description.
    Returns count of events created.
    """
    created = 0
    for d in deadlines:
        if d.calendar_event_id:
            continue
        event_id, provider = create_calendar_event_for_deadline(
            conn, d, opportunity_title, delivery_timeline=delivery_timeline
        )
        if event_id and provider:
            d.calendar_event_id = event_id
            d.calendar_provider = provider
            created += 1
            logger.info("Created calendar event %s for deadline %s (%s)", event_id, d.id, provider)
    return created


def _delete_google_calendar_event(conn: UserEmailConnection, event_id: str) -> bool:
    """Delete a calendar event from Google Calendar."""
    try:
        from googleapiclient.discovery import build
    except ImportError:
        return False
    creds = _get_google_calendar_credentials(conn)
    if not creds:
        return False
    service = build("calendar", "v3", credentials=creds)
    try:
        service.events().delete(calendarId="primary", eventId=event_id).execute()
        return True
    except Exception as e:
        logger.warning("Google Calendar delete event %s failed: %s", event_id, e)
        return False


def _delete_microsoft_calendar_event(conn: UserEmailConnection, event_id: str) -> bool:
    """Delete a calendar event from Microsoft Outlook."""
    import requests
    token = _get_microsoft_calendar_token(conn)
    if not token:
        return False
    r = requests.delete(
        f"https://graph.microsoft.com/v1.0/me/events/{event_id}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=25,
    )
    if r.status_code in (200, 204):
        return True
    logger.warning("Microsoft Graph delete event %s failed: %s %s", event_id, r.status_code, r.text)
    return False


def delete_calendar_events_for_deadlines(
    conn: UserEmailConnection,
    deadlines: List[Deadline],
) -> int:
    """
    Delete from the user's calendar all events that were created for these deadlines.
    Returns count of events deleted. Failures are logged but do not raise.
    """
    deleted = 0
    for d in deadlines:
        if not d.calendar_event_id or not d.calendar_provider:
            continue
        if d.calendar_provider == "google":
            if _delete_google_calendar_event(conn, d.calendar_event_id):
                deleted += 1
                logger.info("Deleted Google Calendar event %s for deadline %s", d.calendar_event_id, d.id)
        elif d.calendar_provider == "microsoft":
            if _delete_microsoft_calendar_event(conn, d.calendar_event_id):
                deleted += 1
                logger.info("Deleted Microsoft Calendar event %s for deadline %s", d.calendar_event_id, d.id)
    return deleted
