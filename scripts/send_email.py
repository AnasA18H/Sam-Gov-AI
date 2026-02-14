#!/usr/bin/env python3
"""
Send a single email using project SMTP settings (from .env).

Usage:
  python scripts/send_email.py
  python scripts/send_email.py --to someone@example.com --subject "Hello" --body "Message text"

Requires in .env (for Gmail use an App Password, not your regular password):
  SMTP_HOST=smtp.gmail.com
  SMTP_PORT=587
  SMTP_USER=your@gmail.com
  SMTP_PASSWORD=your-app-password
"""

import argparse
import os
import smtplib
import sys
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Send email via SMTP")
    parser.add_argument("--to", default="mohammadanasa18h@gmail.com", help="Recipient email")
    parser.add_argument("--subject", default="Test from Sam Gov AI", help="Subject")
    parser.add_argument("--body", default="This is a test email sent from the Sam Gov AI project.", help="Body text")
    args = parser.parse_args()

    host = os.getenv("SMTP_HOST", "").strip() or "smtp.gmail.com"
    port = int(os.getenv("SMTP_PORT", "587").strip() or "587")
    user = os.getenv("SMTP_USER", "").strip()
    password = os.getenv("SMTP_PASSWORD", "").strip()

    if not user or not password:
        print("Error: SMTP_USER and SMTP_PASSWORD must be set in .env to send email.")
        print("For Gmail: use an App Password (Google Account → Security → 2-Step Verification → App passwords).")
        return 1

    msg = MIMEMultipart()
    msg["From"] = user
    msg["To"] = args.to
    msg["Subject"] = args.subject
    msg.attach(MIMEText(args.body, "plain"))

    try:
        with smtplib.SMTP(host, port) as server:
            server.starttls()
            server.login(user, password)
            server.sendmail(user, args.to, msg.as_string())
        print(f"Email sent to {args.to}")
        return 0
    except Exception as e:
        print(f"Failed to send email: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
