"""
Authentication API endpoints.

Auth model: one account per (email, auth_provider). Providers: email, google, microsoft.
Email accounts require verification via code before login. Google/Microsoft are trusted.
"""
import logging
import secrets
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta, timezone
from typing import cast
from urllib.parse import urlencode, quote

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from ..core.database import get_db
from ..core.security import verify_password, get_password_hash, create_access_token, create_refresh_token, decode_token
from ..core.config import settings
from ..core.dependencies import get_current_active_user
from ..models.user import User, AuthProvider
from ..models.session import Session as SessionModel
from ..models.user_email_connection import UserEmailConnection
from ..models.oauth_state import OAuthState
from ..models.contractor_profile import ContractorProfile
from ..schemas.auth import UserRegister, UserLogin, Token, UserResponse
from ..schemas.contractor_profile import ContractorProfileUpdate, ContractorProfileResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["authentication"])

# Default token expiry for auth flows
ACCESS_TOKEN_EXPIRE = timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)


def _verification_email_html(code: str) -> str:
    """HTML body for verification email with company branding."""
    app_name = "Gov Ops Ai"
    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0; padding:0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; background-color: #f1f5f9;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background-color: #f1f5f9; padding: 32px 16px;">
    <tr><td align="center">
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width: 440px; background-color: #ffffff; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.07); overflow: hidden;">
        <tr>
          <td style="padding: 28px 32px 20px; border-bottom: 3px solid #14B8A6;">
            <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
              <tr>
                <td>
                  <span style="display: inline-block; width: 8px; height: 8px; background: #22c55e; border-radius: 2px; margin-right: 4px;"></span>
                  <span style="display: inline-block; width: 8px; height: 8px; background: #eab308; border-radius: 2px; margin-right: 4px;"></span>
                  <span style="display: inline-block; width: 8px; height: 8px; background: #3b82f6; border-radius: 2px;"></span>
                </td>
              </tr>
              <tr><td style="padding-top: 8px;"><span style="font-size: 22px; font-weight: 600; color: #1e293b;">{app_name}</span></td></tr>
            </table>
          </td>
        </tr>
        <tr>
          <td style="padding: 28px 32px;">
            <p style="margin: 0 0 8px; font-size: 18px; font-weight: 600; color: #1e293b;">Verify your email</p>
            <p style="margin: 0 0 24px; font-size: 15px; color: #64748b; line-height: 1.5;">Use this code to sign in or complete your registration:</p>
            <div style="background: linear-gradient(135deg, #f0fdfa 0%, #ccfbf1 100%); border: 2px solid #14B8A6; border-radius: 10px; padding: 20px; text-align: center; margin-bottom: 24px;">
              <span style="font-size: 28px; font-weight: 700; letter-spacing: 6px; color: #0d9488;">{code}</span>
            </div>
            <p style="margin: 0; font-size: 14px; color: #64748b;">This code expires in <strong>15 minutes</strong>. If you didn't request it, you can ignore this email.</p>
          </td>
        </tr>
        <tr>
          <td style="padding: 16px 32px 24px; border-top: 1px solid #e2e8f0;">
            <p style="margin: 0; font-size: 12px; color: #94a3b8;">{app_name} — Government Contract opportunity discovery and analysis</p>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def _send_verification_email(to_email: str, code: str) -> bool:
    """Send verification code via SMTP. Returns True if sent, False otherwise (e.g. SMTP not configured)."""
    if not getattr(settings, "SMTP_USER", None) or not getattr(settings, "SMTP_PASSWORD", None):
        logger.warning("SMTP not configured; verification email not sent (code=%s for %s)", code[:2] + "****", to_email)
        return False
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "Gov Ops Ai - Your verification code"
        msg["From"] = "Gov Ops Ai <info@govopsai.com>"
        msg["To"] = to_email
        text = (
            "Gov Ops Ai\n\n"
            "Verify your email\n\n"
            "Use this code to sign in or complete your registration:\n"
            f"{code}\n\n"
            "This code expires in 15 minutes. If you didn't request it, you can ignore this email.\n\n"
            "Gov Ops Ai — Government Contract opportunity discovery and analysis"
        )
        msg.attach(MIMEText(text, "plain"))
        msg.attach(MIMEText(_verification_email_html(code), "html"))
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail("info@govopsai.com", to_email, msg.as_string())
        return True
    except Exception as e:
        logger.exception("Failed to send verification email: %s", e)
        return False


# --- Send email from app (user's connected Gmail/Outlook) ---

class SendEmailBody(BaseModel):
    to: EmailStr
    subject: str
    body: str


class EmailConnectionResponse(BaseModel):
    connected: bool
    provider: str | None = None
    sender_email: str | None = None


@router.get("/google-redirect-uri")
async def get_google_redirect_uri():
    """
    Return the Google OAuth redirect URI from env. Use this exact value in
    Google Cloud Console → Credentials → your OAuth client → Authorized redirect URIs.
    """
    uri = getattr(settings, "GOOGLE_REDIRECT_URI", "") or ""
    return {
        "redirect_uri": uri,
        "instruction": "Add this EXACT string in Google Console → APIs & Services → Credentials → your OAuth 2.0 Client → Authorized redirect URIs (no trailing slash, same spelling).",
    }


class RegisterResponse(BaseModel):
    """After register we send a verification code; no tokens until email is verified."""
    message: str
    email: str


@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register(
    user_data: UserRegister,
    db: Session = Depends(get_db)
):
    """Register with email: create account, send verification code. Account is separate from Google/Microsoft."""
    existing = db.query(User).filter(
        User.email == user_data.email,
        User.auth_provider == AuthProvider.EMAIL.value,
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This email is already registered. Sign in or use a different email.",
        )
    code = "".join(secrets.choice("0123456789") for _ in range(6))
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)
    hashed_password = get_password_hash(user_data.password)
    new_user = User(
        email=user_data.email,
        auth_provider=AuthProvider.EMAIL.value,
        password_hash=hashed_password,
        full_name=user_data.full_name,
        is_verified=False,
        verification_code=code,
        verification_code_expires_at=expires_at,
    )
    db.add(new_user)
    db.commit()
    sent = _send_verification_email(user_data.email, code)
    if not sent:
        logger.warning("Verification email not sent to %s (SMTP not configured or send failed)", user_data.email)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Verification email could not be sent. The server is not configured for email (SMTP). Please contact support or try again later.",
        )
    return RegisterResponse(
        message="Verification code sent to your email. Enter it below to activate your account.",
        email=user_data.email,
    )


@router.post("/login", response_model=Token)
async def login(
    credentials: UserLogin,
    db: Session = Depends(get_db)
):
    """Login with email and password. Only for accounts that signed up with email (and are verified)."""
    user = db.query(User).filter(
        User.email == credentials.email,
        User.auth_provider == AuthProvider.EMAIL.value,
    ).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    password_hash = cast(str, user.password_hash)
    if not verify_password(credentials.password, password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    is_active = bool(user.is_active)  # type: ignore[arg-type]
    if not is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )
    is_verified = bool(user.is_verified)  # type: ignore[arg-type]
    if not is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="email_not_verified",
        )
    access_token_expires = timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.id, "email": user.email},
        expires_delta=access_token_expires,
    )
    refresh_token = create_refresh_token(data={"sub": user.id, "email": user.email})
    session = SessionModel(
        user_id=user.id,
        token=access_token,
        refresh_token=refresh_token,
        expires_at=datetime.utcnow() + access_token_expires,
        is_active=True,
    )
    db.add(session)
    db.commit()
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }


class RefreshBody(BaseModel):
    refresh_token: str


@router.post("/refresh", response_model=Token)
async def refresh_tokens(
    body: RefreshBody,
    db: Session = Depends(get_db),
):
    """Exchange a valid refresh token for a new access token. Call this when the access token expires (e.g. 401) to stay logged in."""
    payload = decode_token(body.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )
    sub = payload.get("sub")
    if sub is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
    try:
        user_id = int(sub)
    except (TypeError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not bool(user.is_active):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")
    access_token = create_access_token(
        data={"sub": user.id, "email": user.email},
        expires_delta=timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return {
        "access_token": access_token,
        "refresh_token": body.refresh_token,
        "token_type": "bearer",
    }


class VerifyEmailBody(BaseModel):
    email: EmailStr
    code: str


@router.post("/verify-email", response_model=Token)
async def verify_email(
    body: VerifyEmailBody,
    db: Session = Depends(get_db),
):
    """Confirm email with the code we sent; then log the user in (return tokens)."""
    user = db.query(User).filter(
        User.email == body.email,
        User.auth_provider == AuthProvider.EMAIL.value,
    ).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid email or code.")
    if bool(user.is_verified):  # type: ignore[arg-type]
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already verified. You can sign in.")
    verification_code = cast(str | None, user.verification_code)
    verification_code_expires_at = cast(datetime | None, user.verification_code_expires_at)
    if not verification_code or verification_code_expires_at is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No pending verification. Request a new code.")
    now_utc = datetime.now(timezone.utc)
    # DB may return naive or aware; make comparable
    expires_at = verification_code_expires_at
    if expires_at is not None and getattr(expires_at, "tzinfo", None) is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)  # type: ignore[union-attr]
    if expires_at is not None and now_utc > expires_at:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Code expired. Request a new code.")
    code_digits = "".join(c for c in body.code if c.isdigit())
    stored_digits = "".join(c for c in (verification_code or "") if c.isdigit())
    if code_digits != stored_digits or len(code_digits) != 6:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid code.")
    setattr(user, "is_verified", True)
    setattr(user, "verification_code", None)
    setattr(user, "verification_code_expires_at", None)
    db.commit()
    db.refresh(user)
    access_token_expires = timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.id, "email": user.email},
        expires_delta=access_token_expires,
    )
    refresh_token = create_refresh_token(data={"sub": user.id, "email": user.email})
    session = SessionModel(
        user_id=user.id,
        token=access_token,
        refresh_token=refresh_token,
        expires_at=datetime.utcnow() + access_token_expires,
        is_active=True,
    )
    db.add(session)
    db.commit()
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }


class ResendVerificationBody(BaseModel):
    email: EmailStr


@router.post("/resend-verification")
async def resend_verification(
    body: ResendVerificationBody,
    db: Session = Depends(get_db),
):
    """Send a new verification code to the given email (for email-signup accounts only)."""
    user = db.query(User).filter(
        User.email == body.email,
        User.auth_provider == AuthProvider.EMAIL.value,
    ).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No account found for this email.")
    if bool(user.is_verified):  # type: ignore[arg-type]
        return {"message": "Email already verified. You can sign in."}
    code = "".join(secrets.choice("0123456789") for _ in range(6))
    setattr(user, "verification_code", code)
    setattr(user, "verification_code_expires_at", datetime.now(timezone.utc) + timedelta(minutes=15))
    db.commit()
    sent = _send_verification_email(cast(str, user.email), code)
    if not sent:
        logger.warning("Resend verification email not sent to %s (SMTP not configured or send failed)", user.email)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Verification email could not be sent. The server is not configured for email (SMTP). Please contact support.",
        )
    return {"message": "A new verification code has been sent to your email."}


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_active_user)
):
    """Get current user information"""
    return current_user


@router.post("/logout")
async def logout(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Logout and deactivate current session"""
    # Deactivate all active sessions for user
    db.query(SessionModel).filter(
        SessionModel.user_id == current_user.id,
        SessionModel.is_active == True
    ).update({"is_active": False})
    db.commit()
    
    return {"message": "Successfully logged out"}


# --- Contractor profile (for form fill: company, UEI, CAGE, TIN, signer, etc.) ---


@router.get("/profile", response_model=ContractorProfileResponse)
async def get_profile(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Get current user's contractor profile for form filling. Creates empty profile if none exists."""
    profile = db.query(ContractorProfile).filter(ContractorProfile.user_id == current_user.id).first()
    if not profile:
        profile = ContractorProfile(user_id=current_user.id)
        db.add(profile)
        db.commit()
        db.refresh(profile)
    return profile


@router.put("/profile", response_model=ContractorProfileResponse)
async def update_profile(
    body: ContractorProfileUpdate,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Create or update contractor profile (company name, address, UEI, CAGE, TIN, contract officer name, digital signature, email)."""
    profile = db.query(ContractorProfile).filter(ContractorProfile.user_id == current_user.id).first()
    if not profile:
        profile = ContractorProfile(user_id=current_user.id)
        db.add(profile)
        db.commit()
        db.refresh(profile)
    import json
    update = body.model_dump(exclude_unset=True)
    if "custom_stamps" in update and update["custom_stamps"] is not None:
        update["custom_stamps"] = json.dumps(update["custom_stamps"])
    for key, value in update.items():
        setattr(profile, key, value)
    db.commit()
    db.refresh(profile)
    return profile


# --- Sign in with Google / Microsoft (login or register) ---

def _cleanup_old_oauth_states(db: Session, max_age_minutes: int = 15) -> None:
    """Remove OAuth state rows older than max_age_minutes (abandoned flows). Both Google and Microsoft use oauth_states."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=max_age_minutes)
    db.query(OAuthState).filter(OAuthState.created_at < cutoff).delete()
    db.commit()


@router.get("/signin/google")
async def signin_google(db: Session = Depends(get_db)):
    """Redirect to Google OAuth for sign-in (no auth required). Requests Gmail + Calendar so user has email/calendar access without a separate Connect step."""
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_REDIRECT_URI:
        raise HTTPException(status_code=503, detail="Google OAuth not configured")
    _cleanup_old_oauth_states(db)
    state = secrets.token_urlsafe(32)
    db.add(OAuthState(state=state, user_id=0, provider="google"))
    db.commit()
    # Request Gmail + Calendar at sign-in. Use prompt=consent so we always get a refresh_token and can auto-connect
    # Gmail/Calendar (Google only returns refresh_token on first consent otherwise).
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile https://www.googleapis.com/auth/gmail.send https://www.googleapis.com/auth/userinfo.email https://www.googleapis.com/auth/calendar.events",
        "state": state,
        "access_type": "offline",
        "prompt": "consent",
    }
    return RedirectResponse(url="https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params))


@router.get("/signin/microsoft")
async def signin_microsoft(db: Session = Depends(get_db)):
    """Redirect to Microsoft OAuth for sign-in (no auth required). Requests Outlook + Calendar so user has email/calendar access without a separate Connect step."""
    if not settings.MICROSOFT_CLIENT_ID or not settings.MICROSOFT_REDIRECT_URI:
        raise HTTPException(status_code=503, detail="Microsoft OAuth not configured")
    _cleanup_old_oauth_states(db)
    state = secrets.token_urlsafe(32)
    db.add(OAuthState(state=state, user_id=0, provider="microsoft"))
    db.commit()
    # Best practice: request Outlook + Calendar at sign-in so one consent grants identity and company services (Outlook only)
    params = {
        "client_id": settings.MICROSOFT_CLIENT_ID,
        "redirect_uri": settings.MICROSOFT_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid User.Read email profile offline_access https://graph.microsoft.com/Mail.Send https://graph.microsoft.com/Calendars.ReadWrite",
        "state": state,
    }
    return RedirectResponse(
        url="https://login.microsoftonline.com/common/oauth2/v2.0/authorize?" + urlencode(params)
    )


# --- Connect email (Gmail / Outlook) for sending from app ---

@router.get("/email-connection", response_model=EmailConnectionResponse)
async def get_email_connection(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Return whether the user has connected an email account for sending."""
    conn = db.query(UserEmailConnection).filter(
        UserEmailConnection.user_id == current_user.id
    ).first()
    if not conn:
        return EmailConnectionResponse(connected=False)
    return EmailConnectionResponse(
        connected=True,
        provider=cast(str | None, conn.provider),
        sender_email=cast(str | None, conn.sender_email),
    )


@router.delete("/email-connection", response_model=EmailConnectionResponse)
async def disconnect_email_connection(
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Remove the user's connected email/calendar account."""
    conn = db.query(UserEmailConnection).filter(
        UserEmailConnection.user_id == current_user.id
    ).first()
    if conn:
        db.delete(conn)
        db.commit()
    return EmailConnectionResponse(connected=False)


def _get_user_for_connect(access_token: str, db: Session) -> User:
    """Resolve user from token (redirect flow)."""
    from ..core.security import decode_token
    payload = decode_token(access_token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    try:
        sub = payload.get("sub")
        user_id = int(sub) if sub is not None else 0
    except (ValueError, TypeError):
        raise HTTPException(status_code=401, detail="Invalid token")
    if user_id == 0:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    if not bool(user.is_active):  # type: ignore[arg-type]
        raise HTTPException(status_code=401, detail="User not found or inactive")
    return user


async def _user_for_connect_flow(
    request: Request,
    db: Session = Depends(get_db),
) -> User:
    """Get user from ?access_token= (redirect) or Authorization header."""
    token = request.query_params.get("access_token")
    if token:
        return _get_user_for_connect(token, db)
    # No query token: require Bearer (for direct API call)
    auth = request.headers.get("Authorization")
    if not auth or not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")
    return _get_user_for_connect(auth[7:], db)


@router.get("/connect-google")
async def connect_google(
    db: Session = Depends(get_db),
    current_user: User = Depends(_user_for_connect_flow),
):
    """Redirect to Google OAuth to connect Gmail (send) and Google Calendar. Use ?access_token= when redirecting from frontend."""
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_REDIRECT_URI:
        raise HTTPException(status_code=503, detail="Google OAuth not configured")
    _cleanup_old_oauth_states(db)
    state = secrets.token_urlsafe(32)
    db.add(OAuthState(state=state, user_id=current_user.id, provider="google"))
    db.commit()
    # prompt=consent so Google returns refresh_token (required for Gmail/Calendar; otherwise only returned on first consent).
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "https://www.googleapis.com/auth/gmail.send https://www.googleapis.com/auth/userinfo.email https://www.googleapis.com/auth/calendar.events",
        "state": state,
        "access_type": "offline",
        "prompt": "consent",
    }
    return RedirectResponse(url="https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params))


@router.get("/connect-microsoft")
async def connect_microsoft(
    db: Session = Depends(get_db),
    current_user: User = Depends(_user_for_connect_flow),
):
    """Redirect to Microsoft OAuth to connect Outlook (send) and Calendar. Use ?access_token= when redirecting from frontend."""
    if not settings.MICROSOFT_CLIENT_ID or not settings.MICROSOFT_REDIRECT_URI:
        raise HTTPException(status_code=503, detail="Microsoft OAuth not configured")
    _cleanup_old_oauth_states(db)
    state = secrets.token_urlsafe(32)
    db.add(OAuthState(state=state, user_id=current_user.id, provider="microsoft"))
    db.commit()
    # One connect: email (send) + calendar (add events e.g. deadlines)
    params = {
        "client_id": settings.MICROSOFT_CLIENT_ID,
        "redirect_uri": settings.MICROSOFT_REDIRECT_URI,
        "response_type": "code",
        "scope": "https://graph.microsoft.com/Mail.Send https://graph.microsoft.com/User.Read https://graph.microsoft.com/Calendars.ReadWrite offline_access",
        "state": state,
    }
    return RedirectResponse(
        url="https://login.microsoftonline.com/common/oauth2/v2.0/authorize?" + urlencode(params)
    )


def _find_or_create_oauth_user(
    db: Session, email: str, full_name: str | None, provider: str
) -> User:
    """Find or create user by (email, auth_provider). OAuth accounts are separate from email accounts."""
    user = db.query(User).filter(
        User.email == email,
        User.auth_provider == provider,
    ).first()
    if user:
        return user
    random_password = get_password_hash(secrets.token_urlsafe(32))
    user = User(
        email=email,
        auth_provider=provider,
        password_hash=random_password,
        full_name=full_name or email.split("@")[0],
        is_verified=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _redirect_signin_success(frontend: str, user: User, db: Session) -> RedirectResponse:
    """Issue JWT and redirect to frontend auth callback with tokens in hash."""
    access_token_expires = timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.id, "email": user.email},
        expires_delta=access_token_expires,
    )
    refresh_token = create_refresh_token(data={"sub": user.id, "email": user.email})
    session = SessionModel(
        user_id=user.id,
        token=access_token,
        refresh_token=refresh_token,
        expires_at=datetime.utcnow() + access_token_expires,
        is_active=True,
    )
    db.add(session)
    db.commit()
    # Use fragment so tokens are not sent to server
    redirect_url = f"{frontend}/auth/callback#access_token={access_token}&refresh_token={refresh_token}&token_type=bearer"
    return RedirectResponse(url=redirect_url)


@router.get("/google/callback")
async def google_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
):
    """OAuth callback from Google; sign-in (user_id=0) or save email connection."""
    frontend = getattr(settings, "FRONTEND_URL", "http://localhost:5173")
    def err(msg: str) -> RedirectResponse:
        return RedirectResponse(url=f"{frontend}/login?error={quote(msg)}")
    if error:
        return err(error)
    if not code or not state:
        return err("missing_code_or_state")
    row = db.query(OAuthState).filter(OAuthState.state == state).first()
    if not row:
        return err("invalid_state")
    user_id = cast(int, row.user_id)
    db.delete(row)
    db.commit()

    import requests
    _GOOGLE_TIMEOUT = 25  # seconds (avoid 500 on slow networks)
    data = {
        "code": code,
        "client_id": settings.GOOGLE_CLIENT_ID,
        "client_secret": settings.GOOGLE_CLIENT_SECRET,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "grant_type": "authorization_code",
    }
    try:
        r = requests.post("https://oauth2.googleapis.com/token", data=data, timeout=_GOOGLE_TIMEOUT)
    except (requests.exceptions.Timeout, requests.exceptions.RequestException) as e:
        logger.warning("Google token exchange failed: %s", e)
        return err("token_exchange_failed")
    if r.status_code != 200:
        return err("token_exchange_failed")
    tok = r.json()
    access_token = tok.get("access_token")
    if not access_token:
        return err("no_access_token")

    # Get user email and name from userinfo
    try:
        ui = requests.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=_GOOGLE_TIMEOUT,
        )
    except (requests.exceptions.Timeout, requests.exceptions.RequestException) as e:
        logger.warning("Google userinfo failed: %s", e)
        return err("userinfo_failed")
    if ui.status_code != 200:
        return err("userinfo_failed")
    uinfo = ui.json()
    sender_email = uinfo.get("email")
    full_name = uinfo.get("name") or uinfo.get("given_name")

    # Sign-in flow: find or create user and redirect with JWT
    if user_id == 0:
        if not sender_email:
            return err("no_email")
        user = _find_or_create_oauth_user(db, sender_email, full_name, "google")
        if not bool(user.is_active):  # type: ignore[arg-type]
            return err("account_inactive")
        # Best practice: if we got a refresh_token at sign-in, save email connection so user has Gmail/Calendar without a separate Connect step
        refresh_token = tok.get("refresh_token")
        if refresh_token:
            expires_in = tok.get("expires_in")
            token_expires_at = (datetime.now(timezone.utc) + timedelta(seconds=expires_in)) if isinstance(expires_in, (int, float)) else None
            db.query(UserEmailConnection).filter(UserEmailConnection.user_id == user.id).delete()
            db.add(UserEmailConnection(
                user_id=user.id,
                provider="google",
                refresh_token=refresh_token,
                access_token=access_token,
                token_expires_at=token_expires_at,
                sender_email=sender_email,
            ))
            db.commit()
        return _redirect_signin_success(frontend, user, db)

    # Connect-email flow: save tokens for this user
    refresh_token = tok.get("refresh_token")
    if not refresh_token:
        return err("no_refresh_token")
    expires_in = tok.get("expires_in")
    token_expires_at = (datetime.now(timezone.utc) + timedelta(seconds=expires_in)) if isinstance(expires_in, (int, float)) else None
    db.query(UserEmailConnection).filter(UserEmailConnection.user_id == user_id).delete()
    db.add(UserEmailConnection(
        user_id=user_id,
        provider="google",
        refresh_token=refresh_token,
        access_token=access_token,
        token_expires_at=token_expires_at,
        sender_email=sender_email,
    ))
    db.commit()
    return RedirectResponse(url=f"{frontend}/?email_connected=google")


@router.get("/microsoft/callback")
async def microsoft_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
):
    """OAuth callback from Microsoft; sign-in (user_id=0) or save email connection."""
    import requests

    frontend = getattr(settings, "FRONTEND_URL", "http://localhost:5173")

    def err(msg: str) -> RedirectResponse:
        return RedirectResponse(url=f"{frontend}/login?error={quote(msg)}")

    try:
        if error:
            return err(error)
        if not code or not state:
            return err("missing_code_or_state")
        row = db.query(OAuthState).filter(OAuthState.state == state).first()
        if not row:
            return err("invalid_state")
        user_id = cast(int, row.user_id)
        db.delete(row)
        db.commit()

        _OAUTH_TIMEOUT = 25
        # Use "common" to match authorize endpoint (multitenant)
        data = {
            "client_id": settings.MICROSOFT_CLIENT_ID,
            "client_secret": settings.MICROSOFT_CLIENT_SECRET,
            "code": code,
            "redirect_uri": settings.MICROSOFT_REDIRECT_URI,
            "grant_type": "authorization_code",
        }
        try:
            r = requests.post(
                "https://login.microsoftonline.com/common/oauth2/v2.0/token",
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=_OAUTH_TIMEOUT,
            )
        except (requests.exceptions.Timeout, requests.exceptions.RequestException) as e:
            logger.warning("Microsoft token exchange failed: %s", e)
            return err("token_exchange_failed")
        if r.status_code != 200:
            logger.warning("Microsoft token exchange failed: %s %s", r.status_code, r.text[:500])
            return err("token_exchange_failed")
        tok = r.json()
        if "error" in tok:
            logger.warning("Microsoft token response error: %s", tok.get("error_description", tok))
            return err("token_exchange_failed")
        access_token = tok.get("access_token")
        if not access_token:
            return err("no_access_token")

        # Get user email and name from Graph
        try:
            me = requests.get(
                "https://graph.microsoft.com/v1.0/me",
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=_OAUTH_TIMEOUT,
            )
        except (requests.exceptions.Timeout, requests.exceptions.RequestException) as e:
            logger.warning("Microsoft Graph /me failed: %s", e)
            return err("userinfo_failed")
        if me.status_code != 200:
            logger.warning("Microsoft Graph /me failed: %s %s", me.status_code, me.text[:500])
            return err("userinfo_failed")
        minfo = me.json()
        sender_email = minfo.get("mail") or minfo.get("userPrincipalName")
        full_name = minfo.get("displayName")

        # Sign-in flow: find or create user and redirect with JWT
        if user_id == 0:
            if not sender_email:
                return err("no_email")
            user = _find_or_create_oauth_user(db, sender_email, full_name, "microsoft")
            if not bool(user.is_active):  # type: ignore[arg-type]
                return err("account_inactive")
            # Best practice: if we got a refresh_token at sign-in, save email connection so user has Outlook/Calendar without a separate Connect step
            refresh_token = tok.get("refresh_token")
            if refresh_token:
                expires_in = tok.get("expires_in")
                token_expires_at = (datetime.now(timezone.utc) + timedelta(seconds=expires_in)) if isinstance(expires_in, (int, float)) else None
                db.query(UserEmailConnection).filter(UserEmailConnection.user_id == user.id).delete()
                db.add(UserEmailConnection(
                    user_id=user.id,
                    provider="microsoft",
                    refresh_token=refresh_token,
                    access_token=access_token,
                    token_expires_at=token_expires_at,
                    sender_email=sender_email,
                ))
                db.commit()
            return _redirect_signin_success(frontend, user, db)

        # Connect-email flow: save tokens for this user
        refresh_token = tok.get("refresh_token")
        if not refresh_token:
            return err("no_refresh_token")
        expires_in = tok.get("expires_in")
        token_expires_at = (datetime.now(timezone.utc) + timedelta(seconds=expires_in)) if isinstance(expires_in, (int, float)) else None
        db.query(UserEmailConnection).filter(UserEmailConnection.user_id == user_id).delete()
        db.add(UserEmailConnection(
            user_id=int(user_id),
            provider="microsoft",
            refresh_token=refresh_token,
            access_token=access_token,
            token_expires_at=token_expires_at,
            sender_email=sender_email,
        ))
        db.commit()
        return RedirectResponse(url=f"{frontend}/?email_connected=microsoft")
    except Exception as e:
        logger.exception("Microsoft callback error: %s", e)
        return err("signin_failed")


@router.post("/send-email")
async def send_email(
    body: SendEmailBody,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    """Send an email from the user's connected Gmail or Outlook."""
    conn = db.query(UserEmailConnection).filter(
        UserEmailConnection.user_id == current_user.id
    ).first()
    if not conn:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Connect your email first (Gmail or Outlook) to send from the app.",
        )
    from ..services.email_sender import send_email_as_user
    try:
        ok = send_email_as_user(conn, body.to, body.subject, body.body)
    except Exception as e:
        err_str = str(e).lower() if e else ""
        if any(x in err_str for x in ("unable to find the server", "getaddrinfo failed", "name or service not known", "timed out", "timeout", "connection", "network is unreachable", "nodename nor servname")):
            raise HTTPException(status_code=502, detail="Email send failed. This often happens with slow or unstable internet. Please check your connection and try again.")
        raise HTTPException(status_code=502, detail="Failed to send email. Try reconnecting your email.")
    if not ok:
        raise HTTPException(status_code=502, detail="Failed to send email. Try reconnecting your email.")
    return {"message": "Email sent"}
