# TimeBlindAI

TimeBlindAI is a full-stack productivity assistant for people who struggle with time estimation, planning, and task follow-through. It combines task planning, schedule generation, focus sessions, session feedback, and review insights into one workflow.

The project has a FastAPI backend and a Next.js frontend.

## Features

- User onboarding with local profile creation
- Task creation with type, difficulty, deadline, and quantity metadata
- Task decomposition into smaller steps with personalized time estimates
- Focus sessions that track actual time spent on tasks
- Post-session feedback for estimate accuracy and friction reasons
- Event preparation planning with commute, get-ready, and buffer timing
- Schedule generation with time blocks, buffers, risk levels, and recovery flows
- Review dashboard for completed tasks, prediction drift, missed blocks, and feedback patterns
- Light and dark theme support

## Tech Stack

### Backend

- Python 3.11+
- FastAPI
- SQLAlchemy
- Pydantic
- SQLite by default
- Uvicorn

### Frontend

- Next.js 14
- React 18
- TypeScript
- CSS modules/global CSS

## Project Structure

```text
TimeBlindAI/
+-- app/                         # FastAPI backend
|   +-- api/                     # API router registration
|   +-- core/                    # Config, database, shared HTTP helpers
|   +-- modules/                 # Domain modules
|   |   +-- behaviour/
|   |   +-- context/
|   |   +-- events/
|   |   +-- goals/
|   |   +-- health/
|   |   +-- insights/
|   |   +-- interventions/
|   |   +-- reasoning/
|   |   +-- schedules/
|   |   +-- sessions/
|   |   +-- tasks/
|   |   +-- users/
|   +-- main.py                  # FastAPI app entrypoint
+-- frontend/                    # Next.js frontend
|   +-- app/                     # App router pages and global styles
|   +-- components/              # Main shell and UI components
|   +-- lib/                     # API client
|   +-- package.json
+-- timeblind_ai.db              # Local SQLite database
+-- pyproject.toml               # Backend package/dependencies
+-- README.md
```

## Prerequisites

Install these before running the project:

- Python 3.11 or newer
- Node.js 18 or newer
- npm

On this machine, the working Python command may be:

```powershell
C:\Python314\python.exe
```

If `py` works correctly on your machine, you can use `py` instead.

## Backend Setup

From the project root:

```powershell
cd C:\Users\Aman\Desktop\TimeBlindAI
C:\Python314\python.exe -m pip install -e .
```

If your system Python is configured correctly, this also works:

```powershell
py -m pip install -e .
```

## Run The Backend

Start the FastAPI server:

```powershell
cd C:\Users\Aman\Desktop\TimeBlindAI
C:\Python314\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Backend URLs:

```text
API root:      http://127.0.0.1:8000
API docs:      http://127.0.0.1:8000/docs
Health check:  http://127.0.0.1:8000/health
Users:         http://127.0.0.1:8000/api/v1/users
```

If port `8000` is already in use, run on another port:

```powershell
C:\Python314\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8010
```

If you change the backend port, update the frontend API URL as described below.

## Frontend Setup

In a second terminal:

```powershell
cd C:\Users\Aman\Desktop\TimeBlindAI\frontend
npm install
```

## Run The Frontend

```powershell
cd C:\Users\Aman\Desktop\TimeBlindAI\frontend
npm run dev
```

Open:

```text
http://localhost:3000
```

The frontend calls the backend at this default URL:

```text
http://127.0.0.1:8000
```

To override it, create `frontend/.env.local`:

```env
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
```

## Database

The project uses SQLite by default. The database file is:

```text
C:\Users\Aman\Desktop\TimeBlindAI\timeblind_ai.db
```

The backend reads the database URL from `app/core/config.py`:

```python
database_url: str = "sqlite:///./timeblind_ai.db"
```

Because this is a relative path, always start the backend from the project root:

```powershell
cd C:\Users\Aman\Desktop\TimeBlindAI
```

If you run the backend from another folder, it may create or read a different empty SQLite database.

### View Database Tables

If `sqlite3` is not installed, use Python:

```powershell
cd C:\Users\Aman\Desktop\TimeBlindAI

@'
import sqlite3

conn = sqlite3.connect("timeblind_ai.db")
cur = conn.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")

for table in cur.fetchall():
    print(table[0])

conn.close()
'@ | C:\Python314\python.exe -
```

### View Users

```powershell
@'
import sqlite3

conn = sqlite3.connect("timeblind_ai.db")
conn.row_factory = sqlite3.Row
cur = conn.cursor()
cur.execute("SELECT * FROM users ORDER BY created_at DESC")

for row in cur.fetchall():
    print(dict(row))

conn.close()
'@ | C:\Python314\python.exe -
```

You can also open the database visually with DB Browser for SQLite.

## API Modules

The backend exposes these major route groups:

```text
/health
/api/v1/users
/api/v1/tasks
/api/v1/events
/api/v1/schedules
/api/v1/sessions
/api/v1/insights
/api/v1/goals
/api/v1/interventions
/api/v1/context
/api/v1/behaviour
```

Interactive API documentation is available at:

```text
http://127.0.0.1:8000/docs
```

## Demo Flow

Use this flow to show the project:

1. Open `http://localhost:3000`.
2. Create or ensure a user from the onboarding screen.
3. Show the dashboard with pending tasks and summary cards.
4. Add a task with title, deadline, type, difficulty, and quantity.
5. Show the generated task plan and task list.
6. Open a focus session for a task.
7. Start the timer, complete the session, and fill feedback.
8. Open the schedule page and generate a schedule.
9. Start or resume a scheduled block if available.
10. Open the review page and show insights from completed sessions.
11. Open settings and toggle the theme.

## Build Commands

Frontend production build:

```powershell
cd C:\Users\Aman\Desktop\TimeBlindAI\frontend
npm run build
```

Backend syntax check:

```powershell
cd C:\Users\Aman\Desktop\TimeBlindAI
C:\Python314\python.exe -m compileall app
```

## Troubleshooting

### `ModuleNotFoundError: No module named 'sqlalchemy'`

Install backend dependencies into the Python executable you are using:

```powershell
cd C:\Users\Aman\Desktop\TimeBlindAI
C:\Python314\python.exe -m pip install -e .
```

Then start the backend with the same Python:

```powershell
C:\Python314\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### Users Are Missing On Another Device

The users are stored in the local SQLite file. Copy this file to the other device:

```text
timeblind_ai.db
```

Place it in the project root next to `pyproject.toml`, then start the backend from that same root folder.

### Frontend Cannot Reach Backend

Make sure the backend is running:

```text
http://127.0.0.1:8000/health
```

If the backend is on a different port, set `NEXT_PUBLIC_API_BASE_URL` in `frontend/.env.local`.

### Port Already In Use

Use another backend port:

```powershell
C:\Python314\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8010
```

Then update `frontend/.env.local`:

```env
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8010
```

## Notes For Moving The Project

To move the project to another machine for a local demo, copy:

```text
app/
frontend/
pyproject.toml
timeblind_ai.db
README.md
```

Then install backend and frontend dependencies on that machine.
