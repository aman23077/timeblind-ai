# Email and password login

Registration checks email syntax and rejects duplicate addresses after trimming whitespace and lowercasing. It immediately creates a password-protected account. Email mailbox ownership verification is optional future work, outside this registration flow.

Passwords must be nonempty. Requests accept up to 1,024 characters. The backend stores salted PBKDF2-HMAC-SHA256 hashes with 600,000 iterations. Login issues a random session token in an HttpOnly, SameSite=Lax cookie. Only the token hash is stored in the database, and the session expires after seven days. Logout revokes that login session. Password reset revokes all login sessions and companion upload tokens for the account.

## Start after updating

Restart both backend and frontend. The backend startup creates credential, session, password-reset and attempt-limit tables alongside existing data. Open the app and select **Register** for a new account or **Log in** for an account with a password.

The frontend proxies `/api/v1/*` requests through Next.js to keep authentication cookies on the frontend origin. Set `TIMEBLIND_BACKEND_URL` in the frontend server environment to select the backend. Existing `NEXT_PUBLIC_API_BASE_URL` remains a fallback and supplies the Windows companion's address. The default is `http://127.0.0.1:8000`.

## Persistent recovery key

Open **Password setup/reset**, enter the existing account email, paste the administrator's recovery key, and choose a password. The same key works for all accounts, is reusable, and remains valid until rotated. The backend stores its SHA-256 hash in the recovery_keys table. Anyone holding this key can reset any account, including an administrator account.

The local database owner can create the key with this command.

    .venv/Scripts/python.exe -m scripts.account_recovery

The command prints the newly generated key once. To replace it, run the command with --rotate. The previous key stops working immediately. Password resets preserve account IDs and saved work, and revoke the target account's login sessions and companion credentials.

Administrator access is assigned independently of password recovery. Use --email YOUR_EMAIL --admin with the recovery command to grant an existing account administrator access.

## Optional email delivery for password recovery

The existing email-recovery API remains available for integrations that use expiring account-specific codes. The app's recovery form uses the persistent administrator key. Email API integrations can configure these variables.

```dotenv
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=your-mail-account
SMTP_PASSWORD=your-mail-service-credential
SMTP_FROM=TimeBlindAI <no-reply@example.com>
SMTP_SSL=false
```

Port 587 uses STARTTLS with certificate verification. For implicit TLS, use port 465 and `SMTP_SSL=true`. Restart the backend after changing these settings. The application returns a clear configuration error when email delivery has not been set up. Registration and password login work independently of mail delivery.

## API access and deployment

- Browser requests use the login cookie and `X-TimeBlind-Client: web` on writes. Origins must appear in `CORS_ORIGINS`. A non-browser API client can use the same login endpoint and a cookie jar.
- `/api/v1/auth/register`, `/login`, `/me`, `/logout`, `/forgot-password` and `/reset-password` implement account access. The old unauthenticated `/users/ensure` flow has been removed. User lookup returns only the authenticated user's profile.
- Workspace routes authenticate the user and validate resource ownership. Lists without an explicit user filter return the authenticated user's records. Referenced task, goal, event, session, schedule, time-block and reminder IDs are checked before requests run. New resource reference fields must also be added to the shared authorization guard.
- Windows companion uploads continue using their session-scoped pairing token. Creating or stopping a pairing and reading activity summaries require browser authentication.
- Authentication requests are limited to 10 per email and 50 per directly connected IP per 15-minute window. Counters live in the database. When deploying behind a proxy, configure Uvicorn's trusted proxy addresses so forwarded client IPs come only from that proxy.
- Set backend `ENVIRONMENT=production` for Secure cookies, serve the frontend over HTTPS, and set `CORS_ORIGINS` to its exact origin. Deploy the Next.js server with its API proxy enabled.

Password storage and cookie choices follow the [OWASP password storage guidance](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html) and [session management guidance](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html).
