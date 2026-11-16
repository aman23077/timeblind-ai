# Adaptive scheduling and monitoring policy

Newly generated plans save the original work window. While the app or Windows companion is running, policy evaluation runs at most once every 30 seconds per user. Replanning responds to changed tasks, event reservations, active sessions, remaining-time updates and five-minute clock intervals.

The scheduler keeps active and completed work, reserves the current session's projected completion time, respects fixed events and task dependencies, and selects fitting tasks by deadline urgency, priority and duration. During a sustained switching burst it groups similar work within urgency and priority. Tasks that no longer fit are listed with reasons. Revisions and previous block times are saved in plan_revisions. Replanning is a greedy heuristic, and improvements in user efficiency require evaluation.

Open Schedule and choose Replan remaining time for an immediate update. Existing schedules infer their window from their saved blocks when this is first used. New schedules retain the full selected window. On the focus page, enter Estimated minutes remaining to revise the current session forecast. Forecasts include measured idle intervals and reserve at least five additional minutes for unfinished work. These are estimates, and input activity does not establish task progress.

The initial rules are configurable in app/modules/interventions/policy.py.

- A sustained app switch requires consecutive active runs in different executables, each with at least six observed seconds. Gaps and idle observations break continuity. Four switches within five minutes trigger the switching rule when recent observation coverage reaches 60%.
- Input inactivity is supplied by the companion after its 60-second threshold. At least 120 observed idle seconds trigger an idle check-in. Reading and thinking can produce inactivity.
- Slippage factor is minutes past the allocated block end divided by planned task minutes. A session without a block uses its estimate from the actual start. A factor of at least 0.20 and at least five minutes overdue trigger a remaining-time prompt.
- A task at least five minutes late receives a start reminder. An upcoming task can receive a reminder within five minutes before its start.
- Precedence is slippage, late start, switching, idle, upcoming.
- There is a ten-minute global nudge cooldown, extended to twenty minutes for the minimal reminder preference. Stale signals resolve automatically.
- In-app reminders appear in Adaptive planning. Browser notifications require the Enable browser reminders button. The companion also prints new reminders in its console. Evaluation resumes when the app or companion reconnects.
- Activity must have arrived within fifteen seconds for switch/idle rules. Unobserved time is not treated as inactivity.

# Administration

The /admin page lists users and paginated task and session entries. Access requires an authenticated account with an explicit admin_access grant. The local database owner can grant access with the recovery-key command:

    .venv/Scripts/python.exe -m scripts.account_recovery --email YOUR_EMAIL --admin

The persistent recovery key works for all accounts until rotated. Enter the target email and key in Password setup/reset and choose a password. The admin endpoints expose user profiles and task/session records. Password hashes, login tokens and recovery codes are excluded.
