# Email and calendar for different account types

## Account types

- **Email (verification)**: User signs up with email + password and verifies with a 6-digit code. No OAuth; we only know their email.
- **Google**: User signs in with Google OAuth. We get email and optional tokens if they later “connect” for sending.
- **Microsoft**: User signs in with Microsoft OAuth. Same idea.

These are **separate accounts** per (email, auth_provider). A user with `user@company.com` + email verification is different from `user@company.com` + Google.

## Getting email and calendar when user logged in with email verification

Email-verification users don’t have OAuth tokens. To let the app **send email** or **use calendar** on their behalf, they must connect a provider (Gmail or Microsoft) once:

1. User is logged in (any account type).
2. In settings or profile, they choose **Connect Gmail** or **Connect Outlook**.
3. They complete OAuth; we request scopes for **email sending** and **calendar** (see below).
4. We store tokens in `UserEmailConnection` and use them for sending and (when implemented) adding events.

So: **email and calendar both come from the same “Connect Google” or “Connect Microsoft” step.** No separate “connect email” vs “connect calendar.”

## One connect vs two

| Approach | Pros | Cons |
|----------|-----|-----|
| **Email only** | Simpler; enough for “send quote request.” | No deadline/calendar features without a second connect later. |
| **Calendar only** | Rare; most apps need send-email first. | Not recommended as the only option. |
| **Both (email + calendar) in one connect** | One consent, one flow; user connects once and gets send + add-to-calendar. Standard in B2B apps. | Slightly broader scope in the consent screen. |

**Recommendation: both in one connect.** Request both Mail.Send and Calendar scopes when the user connects Google or Microsoft. That way:

- **Professional**: Single “Connect your Google/Microsoft account” for email and calendar.
- **Functional**: We can send quote emails and (when implemented) add opportunity deadlines to their calendar.
- **Future-proof**: No need to ask users to reconnect later for calendar.

## Implementation status

- **Email sending**: Implemented. Connect Google/Microsoft stores tokens; `email_sender` uses them to send mail.
- **Calendar**: Scopes are added in the connect flow so stored tokens can be used for calendar later. Backend APIs to “add event to calendar” can be added when needed (e.g. “Add deadline to my calendar” on an opportunity).

## Scopes used

- **Google connect**: `gmail.send`, `userinfo.email`, and `calendar.events` (read/write) so we can create events.
- **Microsoft connect**: `Mail.Send`, `User.Read`, `Calendars.ReadWrite`, and `offline_access` so we can send mail and create events.

Users see one consent screen per provider; no separate “email only” vs “calendar only” flows.
