# SMTP setup for verification emails

Signup and login use **email verification codes**. The app sends these via SMTP. Without SMTP configured, verification emails are not sent and the API will return a 503 error.

## Required environment variables

Add these to your `.env` (project root):

```bash
# SMTP (for verification emails)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password
```

- **SMTP_USER**: The email address that sends the verification emails (e.g. your Gmail).
- **SMTP_PASSWORD**: For Gmail, use an **App Password**, not your normal password (see below).

## Gmail (step-by-step)

You need an **App Password** for SMTP. Google only lets you create one if **2-Step Verification** is on. Do both in this order.

### Step 1: Turn on 2-Step Verification

1. Open **[myaccount.google.com](https://myaccount.google.com)** and sign in with the Gmail you’ll use for sending (e.g. `you@gmail.com`).
2. In the left menu, click **Security**.
3. Under “How you sign in to Google”, click **2-Step Verification**.
4. Click **Get started** and follow the prompts (phone number, code from SMS or app). Finish until it says 2-Step Verification is on.

### Step 2: Create an App Password

1. Go to **[myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)** (or: Security → 2-Step Verification → scroll to “App passwords”).
2. You may need to sign in again. If you don’t see “App passwords”, double-check 2-Step Verification is really on.
3. Under “App passwords”:
   - **Select app**: choose **Mail**.
   - **Select device**: choose **Other (Custom name)** and type e.g. `Sam Gov AI` or `SMTP`.
4. Click **Generate**.
5. Google shows a **16-character password** (like `abcd efgh ijkl mnop`). Copy it. You won’t see it again.
6. In your project `.env` use that as `SMTP_PASSWORD`. You can paste it with or without spaces; both work:
   ```bash
   SMTP_HOST=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USER=you@gmail.com
   SMTP_PASSWORD=abcdefghijklmnop
   ```
   (Replace `you@gmail.com` with the same Gmail and the 16-character app password you just copied.)

## Outlook / Microsoft 365

- **SMTP_HOST**: `smtp.office365.com`
- **SMTP_PORT**: `587`
- **SMTP_USER**: Your full email (e.g. `you@outlook.com` or `you@yourcompany.com`).
- **SMTP_PASSWORD**: Your account password. If you use MFA, you may need an app password from the Microsoft account portal.

## Other providers

- **SendGrid**: Use SMTP relay (e.g. `smtp.sendgrid.net`, port 587) and your SendGrid API key as the password.
- **Mailgun / Amazon SES**: Use their documented SMTP host, port, username, and password.

After setting these, restart the backend and try signup again; the verification code will be sent to the user’s email.
