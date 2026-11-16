# Deploy the TimeBlindAI pilot on Render

Deploy both existing services from the same `main` commit. Confirm the backend uses its existing persistent database before inviting participants. If previous data is stored in a SQLite file, back it up before changing database settings. A SQLite file on Render's default filesystem is lost on restart or redeploy.

| Service | Build command | Start command | Environment |
|---|---|---|---|
| Backend, from repo root | `pip install -r requirements.txt` | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` | Set `ENVIRONMENT=production`, `CORS_ORIGINS=https://timeblind-frontend.onrender.com`, and `DATABASE_URL` to the existing persistent database. |
| Frontend, root directory `frontend` | `npm ci && npm run build` | `npm run start -- --port $PORT` | Set `TIMEBLIND_BACKEND_URL` to the backend HTTPS origin, without `/api/v1`. The existing `NEXT_PUBLIC_API_BASE_URL` also works. |

Render PostgreSQL connection URLs are supported. For SQLite with a persistent disk mounted at `/var/data`, use `sqlite:////var/data/timeblind_ai.db`. Keep credentials and recovery keys in the hosted environment or administrator's password manager.

The hosted database has its own accounts and admin grant. If `aman23077@iiitd.ac.in` has no grant there, use an authorized backend shell to run `python -m scripts.account_recovery --email aman23077@iiitd.ac.in --admin` after confirming the existing account belongs to the project owner. If the account predates password login, use the operator-held key to set its password. Keep the universal key with the administrator. It can reset every account.

Verify the frontend returns 401 from `/api/v1/auth/me` and `/api/v1/admin/export` when signed out. Use an operator test account to create a task, complete a focus session with feedback, and confirm its records appear in the admin ZIP. After a normal redeploy, confirm the same records still exist. Exclude the operator account from study results.

## Collect report statistics

Ask participants to create tasks, generate schedules, and complete sessions. The optional Windows companion records activity only when users enable it. The session completion form records task friction and feedback notes. The admin ZIP links tasks, sessions, activity intervals, reminders, decisions, and schedule revisions by ID.

Use consented pilot accounts for research. Report the sample size and collection window alongside session completion rate, duration error, delay/overrun, reminder counts, and feedback themes. Keep synthetic benchmark measurements separate. See [prediction logging and evaluation](prediction-study.md) and [the synthetic benchmark protocol](synthetic-evaluation.md).
