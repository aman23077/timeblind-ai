# Windows app activity

TimeBlindAI can record foreground executable names, device inactivity and app switches during a focus session. Activity is stored in the configured backend database and appears on the task's focus-session page, including after completion.

## Run it

1. Start the backend and frontend using the README instructions. Restart the backend after updating this code so database initialization creates the activity tables.
2. Open a task and click **Start focus**, then **Enable app monitoring**.
3. In a second PowerShell terminal, change to the TimeBlindAI project folder and run the command displayed on the page. For the default local backend the command is `py -m scripts.windows_companion`.
4. Paste the pairing token into the terminal when prompted. Token input is hidden. Leave this terminal open during the session. The page changes to **Companion connected** after the first uploaded interval.
5. Switch between apps and return to the page to see active time by executable and the switch count. Click **Stop monitoring**, complete or cancel the session, or press Ctrl+C in the companion terminal to stop collection. A newly enabled session needs a fresh token. If the page was refreshed before pairing, use **Get new pairing token**.

The companion uses Python 3.11+ and the standard library. Run it under the interactive Windows account being measured. `py -m scripts.windows_companion --check` prints one native sample and exits. For a different backend use `--server https://your-backend.example`. Remote connections require HTTPS.

## Measurements

- The companion samples roughly every two seconds. Each bounded interval is attributed to the foreground executable observed at its start. Switches shorter than the sampling period can be missed.
- After 60 seconds without input in the current Windows login session, new intervals are classified as idle. Reading and thinking can produce inactivity. App activity measures device interaction and does not establish attention to the task.
- App switches count adjacent active intervals with different executable names and at most a one-second gap. Idle and unknown intervals break the comparison. Browser tabs share the browser executable name. Different windows of the same executable share a name too.
- Access-denied processes and missing foreground windows produce unknown observations. Suspend/resume gaps over five seconds are discarded. Time before pairing, after stopping and during missing observations appears as unobserved time.
- The companion sends executable basenames and timestamps. Full executable paths are discarded locally. The backend accepts only bounded interval records. Network retries reuse sequence numbers so the same interval is counted once.
- A failed upload pauses new sampling while the pending interval is retried. A prolonged failure ends the companion with instructions to restart. Previously saved activity persists. A stopped session rejects new uploads, so the final in-flight interval can be absent.
- The page shows device-active time, idle time, unobserved time, app switches and active seconds per executable. Existing task duration uses the focus-session timer. Manual logged time is available explicitly for testing and defaults to off. If manual completion time precedes an observation, the summary clips the observation to that time.

## Storage and access

The backend creates `activity_monitors` and `activity_intervals` through the existing startup initialization. Existing sessions require no migration or backfill. Completed sessions without measurements show unobserved time.

Pairing tokens are random, stored as hashes and scoped to one focus session. Re-pairing rotates the token. Ending a session revokes it. Collection is explicitly enabled per session, and the console remains visible during collection.

Management and summary routes require an authenticated login and check session ownership. The companion token authenticates uploads independently. Password reset revokes companion tokens for the account. See the [account setup instructions](authentication.md) for existing email-only accounts.

## Verify a study session

Record reference timestamps while switching between two applications, leave input untouched beyond 60 seconds, resume input and then stop monitoring. Compare reference intervals with saved totals. Report switch precision/recall, idle-duration error and the sampling interval alongside results. Keep reading periods labeled separately if evaluating focused work. The automated tests use synthetic data and are implementation checks.

The native collector uses Microsoft's [GetForegroundWindow](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getforegroundwindow), [QueryFullProcessImageNameW](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-queryfullprocessimagenamew) and [GetLastInputInfo](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getlastinputinfo) APIs.
