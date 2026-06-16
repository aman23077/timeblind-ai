"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useState, useTransition } from "react";

import {
  createSession,
  endSession,
  getTask,
  getTimeBlock,
  listSessions,
  recoverScheduleFromBlock,
  startTimeBlockSession
} from "../../lib/api";
import type { ScheduleGenerationResponse, ScheduleRecoveryResponse, SessionRecord, TaskDetail, UserDetail } from "../../lib/api";

const SESSION_KEY = "timeblind-user";
const THEME_KEY = "timeblind-theme";
const LONGER_REASONS = [
  "Harder than expected",
  "Interrupted",
  "Lost focus",
  "Took a break",
  "Needed to switch context",
  "Environment distraction",
  "Other"
] as const;
const SHORTER_REASONS = [
  "Easier than expected",
  "Already familiar with it",
  "Estimate was too high",
  "Worked with strong focus"
] as const;

type CompletionOutcome = "less_than_expected" | "as_expected" | "longer_than_expected";

export function SessionPageClient() {
  const searchParams = useSearchParams();
  const taskId = searchParams.get("taskId");
  const timeBlockId = searchParams.get("timeBlockId");

  const [user, setUser] = useState<UserDetail | null>(null);
  const [task, setTask] = useState<TaskDetail | null>(null);
  const [timeBlock, setTimeBlock] = useState<ScheduleGenerationResponse["time_blocks"][number] | null>(null);
  const [sessions, setSessions] = useState<SessionRecord[]>([]);
  const [activeSession, setActiveSession] = useState<SessionRecord | null>(null);
  const [seconds, setSeconds] = useState(0);
  const [useManualDuration, setUseManualDuration] = useState(true);
  const [manualHours, setManualHours] = useState(1);
  const [manualMinutes, setManualMinutes] = useState(0);
  const [showCompletionModal, setShowCompletionModal] = useState(false);
  const [recoveryPlan, setRecoveryPlan] = useState<ScheduleRecoveryResponse | null>(null);
  const [showRecoveryModal, setShowRecoveryModal] = useState(false);
  const [showBreakModal, setShowBreakModal] = useState(false);
  const [showResumeModal, setShowResumeModal] = useState(false);
  const [breakSecondsLeft, setBreakSecondsLeft] = useState(0);
  const [completionOutcome, setCompletionOutcome] = useState<CompletionOutcome>("as_expected");
  const [feedbackReasons, setFeedbackReasons] = useState<string[]>([]);
  const [feedbackNotes, setFeedbackNotes] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();
  const [theme, setTheme] = useState<"light" | "dark">("light");

  useEffect(() => {
    const stored = window.localStorage.getItem(SESSION_KEY);
    if (!stored) {
      return;
    }

    try {
      const parsed = JSON.parse(stored) as UserDetail;
      setUser(parsed);
    } catch {
      window.localStorage.removeItem(SESSION_KEY);
    }

    const storedTheme = window.localStorage.getItem(THEME_KEY);
    if (storedTheme === "light" || storedTheme === "dark") {
      setTheme(storedTheme);
    }
  }, []);

  useEffect(() => {
    if (!taskId || !user) {
      return;
    }

    startTransition(() => {
      void loadTaskContext(taskId, user.id, timeBlockId);
    });
  }, [taskId, timeBlockId, user]);

  useEffect(() => {
    if (!activeSession) {
      return;
    }

    const updateElapsed = () => {
      setSeconds(
        Math.max(0, Math.floor((Date.now() - parseApiDate(activeSession.actual_start ?? activeSession.started_at).getTime()) / 1000))
      );
    };

    updateElapsed();
    const interval = window.setInterval(updateElapsed, 1000);

    return () => window.clearInterval(interval);
  }, [activeSession]);

  useEffect(() => {
    if (!showBreakModal || breakSecondsLeft <= 0) {
      if (showBreakModal && breakSecondsLeft <= 0) {
        setShowBreakModal(false);
        setShowResumeModal(true);
      }
      return;
    }

    const timer = window.setTimeout(() => {
      setBreakSecondsLeft((current) => Math.max(0, current - 1));
    }, 1000);

    return () => window.clearTimeout(timer);
  }, [breakSecondsLeft, showBreakModal]);

  async function loadTaskContext(nextTaskId: string, userId: string, nextTimeBlockId?: string | null) {
    try {
      setError(null);
      const [taskDetail, taskSessions, blockDetail] = await Promise.all([
        getTask(nextTaskId),
        listSessions(userId, nextTaskId),
        nextTimeBlockId ? getTimeBlock(nextTimeBlockId) : Promise.resolve(null)
      ]);
      setTask(taskDetail);
      setTimeBlock(blockDetail);
      setSessions(taskSessions);
      const runningSession =
        taskSessions.find(
          (session) =>
            session.status === "active" &&
            !session.ended_at &&
            (!nextTimeBlockId || session.time_block_id === nextTimeBlockId)
        ) ?? null;
      setActiveSession(runningSession);
      setSeconds(
        runningSession
          ? Math.max(
              0,
              Math.floor((Date.now() - parseApiDate(runningSession.actual_start ?? runningSession.started_at).getTime()) / 1000)
            )
          : 0
      );
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Could not load task session.");
    }
  }

  async function handleStart() {
    if (!user || !taskId || activeSession) {
      return;
    }

    startTransition(() => {
      void (async () => {
        try {
          setError(null);
          const session = timeBlockId
            ? (
                await startTimeBlockSession(timeBlockId, {
                  user_id: user.id,
                  started_at: new Date().toISOString()
                })
              ).session
            : await createSession({
                user_id: user.id,
                task_id: taskId,
                started_at: new Date().toISOString(),
                status: "active"
              });
          setActiveSession(session);
          setSeconds(0);
          await loadTaskContext(taskId, user.id, timeBlockId);
        } catch (startError) {
          setError(startError instanceof Error ? startError.message : "Could not start focus session.");
        }
      })();
    });
  }

  async function completeSessionWithFeedback() {
    if (!user || !taskId || !activeSession) {
      return;
    }

    startTransition(() => {
      void (async () => {
        try {
          setError(null);
          const startedAt = parseApiDate(activeSession.started_at);
          const manualDurationMinutes = Math.max(0, manualHours * 60 + manualMinutes);
          const effectiveEndedAt =
            useManualDuration && manualDurationMinutes > 0
              ? new Date(startedAt.getTime() + manualDurationMinutes * 60 * 1000)
              : new Date();

          await endSession(activeSession.id, {
            ended_at: effectiveEndedAt.toISOString(),
            actual_end: effectiveEndedAt.toISOString(),
            status: "completed",
            difficulty_feedback: completionOutcome,
            feedback_reasons: feedbackReasons,
            feedback_notes: feedbackNotes.trim()
          });

          setActiveSession(null);
          setSeconds(0);
          resetCompletionFeedback();
          setShowCompletionModal(false);
          const recovered = await handleScheduleRecovery(user.id, effectiveEndedAt.toISOString());
          if (!recovered) {
            await loadTaskContext(taskId, user.id, timeBlockId);
          }
        } catch (stopError) {
          setError(stopError instanceof Error ? stopError.message : "Could not stop focus session.");
        }
      })();
    });
  }

  async function handleCancelSession() {
    if (!user || !taskId || !activeSession) {
      return;
    }

    startTransition(() => {
      void (async () => {
        try {
          setError(null);
          await endSession(activeSession.id, {
            ended_at: new Date().toISOString(),
            actual_end: new Date().toISOString(),
            status: "cancelled",
            difficulty_feedback: "as_expected",
            feedback_reasons: [],
            feedback_notes: ""
          });
          setActiveSession(null);
          setSeconds(0);
          await loadTaskContext(taskId, user.id, timeBlockId);
        } catch (stopError) {
          setError(stopError instanceof Error ? stopError.message : "Could not cancel focus session.");
        }
      })();
    });
  }

  function openCompletionModal() {
    if (!activeSession) {
      return;
    }

    resetCompletionFeedback();
    setShowCompletionModal(true);
  }

  function closeCompletionModal() {
    if (isPending) {
      return;
    }

    setShowCompletionModal(false);
  }

  function resetCompletionFeedback() {
    setCompletionOutcome("as_expected");
    setFeedbackReasons([]);
    setFeedbackNotes("");
  }

  function toggleFeedbackReason(reason: string) {
    setFeedbackReasons((current) =>
      current.includes(reason) ? current.filter((item) => item !== reason) : [...current, reason]
    );
  }

  function handleOutcomeChange(value: CompletionOutcome) {
    setCompletionOutcome(value);
    setFeedbackReasons([]);
    setFeedbackNotes("");
  }

  async function handleScheduleRecovery(userId: string, resumedFrom: string) {
    if (!timeBlock) {
      return false;
    }

    try {
      const recovery = await recoverScheduleFromBlock(timeBlock.id, {
        user_id: userId,
        resumed_from: resumedFrom,
        suggested_break_minutes: 10
      });
      setRecoveryPlan(recovery);
      setShowRecoveryModal(true);
      return true;
    } catch (advanceError) {
      setError(advanceError instanceof Error ? advanceError.message : "Could not move to the next scheduled block.");
      return false;
    }
  }

  async function beginRecoveredBlock() {
    if (!user || !recoveryPlan?.next_time_block?.task_id) {
      return;
    }

    const nextBlock = recoveryPlan.next_time_block;
    const nextTaskId = nextBlock.task_id!;
    setShowRecoveryModal(false);
    setShowBreakModal(false);
    setShowResumeModal(false);
    await startTimeBlockSession(nextBlock.id, {
      user_id: user.id,
      started_at: new Date().toISOString()
    });

    window.location.href = `/session?taskId=${encodeURIComponent(nextTaskId)}&timeBlockId=${encodeURIComponent(nextBlock.id)}`;
  }

  function startRecoveryBreak() {
    const breakMinutes = recoveryPlan?.suggested_break_minutes ?? 0;
    setShowRecoveryModal(false);
    setShowResumeModal(false);
    setBreakSecondsLeft(breakMinutes * 60);
    setShowBreakModal(true);
  }

  const reasonOptions =
    completionOutcome === "longer_than_expected"
      ? LONGER_REASONS
      : completionOutcome === "less_than_expected"
        ? SHORTER_REASONS
        : [];

  if (!user) {
    return (
      <div className="app-shell session-app-shell" data-theme={theme}>
        <main className="content-shell session-content-shell">
          <section className="panel neutral-panel">
            <div className="panel-header">
              <h1>Focus Session</h1>
              <p>Start from the dashboard after signing in so the timer can attach to your task.</p>
            </div>
            <Link className="ghost-button task-link-button" href="/">
              Back to dashboard
            </Link>
          </section>
        </main>
      </div>
    );
  }

  if (!taskId) {
    return (
      <div className="app-shell session-app-shell" data-theme={theme}>
        <main className="content-shell session-content-shell">
          <section className="panel neutral-panel">
            <div className="panel-header">
              <h1>No task selected</h1>
              <p>Open a task from the dashboard to start a task-linked focus session.</p>
            </div>
            <Link className="ghost-button task-link-button" href="/">
              Back to dashboard
            </Link>
          </section>
        </main>
      </div>
    );
  }

  return (
    <div className="app-shell session-app-shell" data-theme={theme}>
      <main className="content-shell session-content-shell">
        <section className="dashboard-header">
          <div className="panel-header">
            <div>
              <p className="eyebrow">Task Session</p>
              <h1>{task?.title ?? "Loading task..."}</h1>
              <p className="lede">
                Start a focus session for this task and compare the planned effort with the actual time you spend.
              </p>
            </div>
            <div className="header-actions">
              <Link className="ghost-button task-link-button" href="/">
                Back to dashboard
              </Link>
            </div>
          </div>
        </section>

      {error ? <p className="error-banner">{error}</p> : null}

      <section className="dashboard-grid">
        <article className="panel warm-panel compact-panel">
          <div className="panel-header">
            <h2>Focus timer</h2>
            <p>Use the timer below to log the actual time spent on this task.</p>
          </div>

          <div className="result-card">
            <div className="result-row">
              <span>Status</span>
              <strong>{activeSession ? "Running" : "Idle"}</strong>
            </div>
            <div className="timer-display">
              {formatElapsed(seconds)}
            </div>
            <div className="session-action-row">
              <button type="button" onClick={handleStart} disabled={isPending || Boolean(activeSession)}>
                {activeSession ? "Session running" : "Start focus"}
              </button>
              <button
                type="button"
                className="ghost-button"
                onClick={openCompletionModal}
                disabled={isPending || !activeSession}
              >
                Complete session
              </button>
              <button
                type="button"
                className="ghost-button"
                onClick={() => void handleCancelSession()}
                disabled={isPending || !activeSession}
              >
                Cancel session
              </button>
            </div>
            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={useManualDuration}
                onChange={(event) => setUseManualDuration(event.target.checked)}
              />
              Use manual logged time for testing
            </label>
            {useManualDuration ? (
              <div className="manual-duration-grid">
                <label>
                  Hours
                  <input
                    type="number"
                    min={0}
                    value={manualHours}
                    onChange={(event) => setManualHours(Math.max(0, Number(event.target.value) || 0))}
                  />
                </label>
                <label>
                  Minutes
                  <input
                    type="number"
                    min={0}
                    max={59}
                    value={manualMinutes}
                    onChange={(event) =>
                      setManualMinutes(Math.min(59, Math.max(0, Number(event.target.value) || 0)))
                    }
                  />
                </label>
              </div>
            ) : null}
            <p className="subtle-copy">
              {useManualDuration
                ? `Testing override is on: completing this session will log ${formatDurationMinutes(
                    manualHours * 60 + manualMinutes
                  )}.`
                : "Manual override is off: logged time matches the real session duration."}
            </p>
          </div>
        </article>

        <article className="panel cool-panel compact-panel">
          <div className="panel-header">
            <h2>Time comparison</h2>
            <p>Planned effort comes from the task decomposition. Actual effort comes from completed focus sessions.</p>
          </div>

          <div className="result-card">
            <div className="result-row">
              <span>Planned</span>
              <strong>{formatDurationMinutes(task?.estimated_minutes ?? null)}</strong>
            </div>
            <div className="result-row">
              <span>Actual</span>
              <strong>{formatDurationMinutes(task?.actual_minutes ?? null)}</strong>
            </div>
            <div className="result-row">
              <span>Difference</span>
              <strong>{formatDelta(task?.estimated_minutes ?? null, task?.actual_minutes ?? null)}</strong>
            </div>
            <div className="result-row">
              <span>Sessions logged</span>
              <strong>{sessions.filter((session) => session.status === "completed").length}</strong>
            </div>
            <p className="subtle-copy">
              For now, completing a session marks the task finished. We can relax that later when scheduling supports
              multi-block work.
            </p>
          </div>

          {timeBlock ? (
            <div className="result-card">
              <div className="panel-header">
                <h3>Scheduled vs actual</h3>
                <p>Use this block to compare what was planned in the schedule with what actually happened.</p>
              </div>
              <div className="result-row">
                <span>Scheduled start</span>
                <strong>{formatDate(timeBlock.start_at)}</strong>
              </div>
              <div className="result-row">
                <span>Actual start</span>
                <strong>{timeBlock.actual_start ? formatDate(timeBlock.actual_start) : "Not started yet"}</strong>
              </div>
              <div className="result-row">
                <span>Scheduled duration</span>
                <strong>
                  {formatDurationMinutes(timeBlock.planned_duration_minutes ?? getScheduledDurationMinutes(timeBlock))}
                </strong>
              </div>
              <div className="result-row">
                <span>Actual duration</span>
                <strong>{formatDurationMinutes(activeSession?.elapsed_minutes ?? latestElapsedMinutes(sessions, timeBlock.id))}</strong>
              </div>
              <div className="result-row">
                <span>Delay</span>
                <strong>{timeBlock.delay_minutes ? formatDurationMinutes(timeBlock.delay_minutes) : "On time"}</strong>
              </div>
              <div className="result-row">
                <span>Overrun</span>
                <strong>{timeBlock.overrun_minutes ? formatDurationMinutes(timeBlock.overrun_minutes) : "Within block"}</strong>
              </div>
              {timeBlock.delay_minutes > 0 ? (
                <p className="subtle-copy">Started late by {formatDurationMinutes(timeBlock.delay_minutes)}.</p>
              ) : null}
              {timeBlock.overrun_minutes > 0 ? (
                <p className="subtle-copy">Overran by {formatDurationMinutes(timeBlock.overrun_minutes)}.</p>
              ) : null}
            </div>
          ) : null}

          {task?.steps.length ? (
            <ul className="timeline-list">
              {task.steps.map((step) => (
                <li key={step.id}>
                  <strong>{step.title}</strong>
                  <span>{formatDurationMinutes(step.suggested_minutes)}</span>
                  <p>{step.rationale || "Task step"}</p>
                </li>
              ))}
            </ul>
          ) : null}
        </article>
      </section>

      <section className="dashboard-stack secondary-grid">
        <article className="panel neutral-panel">
          <div className="panel-header">
            <h2>Session history</h2>
            <p>Each completed timer contributes to the task&apos;s actual minutes.</p>
          </div>
          <ul className="compact-list">
            {sessions.length ? (
              sessions.map((session) => (
                <li key={session.id}>
                  <strong>{session.status}</strong>
                  <span>{formatDate(session.started_at)}</span>
                  <p>{describeSessionDuration(session)}</p>
                  {session.status === "completed" ? <p>{describeFeedback(session)}</p> : null}
                </li>
              ))
            ) : (
              <li>
                <strong>No sessions yet</strong>
                <p>Start your first focus block for this task.</p>
              </li>
            )}
          </ul>
        </article>
      </section>

      {showCompletionModal ? (
        <div className="modal-backdrop">
          <div className="panel warm-panel session-flow-modal">
            <div className="panel-header">
              <div>
                <h2>Wrap up this session</h2>
                <p>Quick reflection helps the app understand what happened without making this feel heavy.</p>
              </div>
            </div>
            <div className="stack-form">
              <div>
                <p className="modal-question">How did this block feel compared to the estimate?</p>
                <div className="feedback-card-grid">
                  <button
                    type="button"
                    className={completionOutcome === "less_than_expected" ? "feedback-option-card active" : "feedback-option-card"}
                    onClick={() => handleOutcomeChange("less_than_expected")}
                  >
                    <strong>Smoother than expected</strong>
                    <span>You got through it faster than planned.</span>
                  </button>
                  <button
                    type="button"
                    className={completionOutcome === "as_expected" ? "feedback-option-card active" : "feedback-option-card"}
                    onClick={() => handleOutcomeChange("as_expected")}
                  >
                    <strong>About right</strong>
                    <span>The estimate felt close to reality.</span>
                  </button>
                  <button
                    type="button"
                    className={completionOutcome === "longer_than_expected" ? "feedback-option-card active" : "feedback-option-card"}
                    onClick={() => handleOutcomeChange("longer_than_expected")}
                  >
                    <strong>Heavier than expected</strong>
                    <span>It stretched beyond what the plan expected.</span>
                  </button>
                </div>
              </div>

              <p className="subtle-copy feedback-helper">
                {completionOutcome === "less_than_expected"
                  ? "Nice. What helped this block go smoothly?"
                  : completionOutcome === "as_expected"
                    ? "Nice. The estimate felt close."
                    : "What got in the way this time?"}
              </p>

              {reasonOptions.length ? (
                <div className="feedback-reason-grid">
                    {reasonOptions.map((option) => (
                      <label key={option} className={feedbackReasons.includes(option) ? "feedback-chip active" : "feedback-chip"}>
                        <input
                          type="checkbox"
                          checked={feedbackReasons.includes(option)}
                          onChange={() => toggleFeedbackReason(option)}
                        />
                        {option}
                      </label>
                    ))}
                </div>
              ) : null}

              <label>
                Notes (optional)
                <textarea
                  rows={3}
                  value={feedbackNotes}
                  onChange={(event) => setFeedbackNotes(event.target.value)}
                  placeholder="Add anything useful about why the estimate matched, ran short, or ran long."
                />
              </label>

              <div className="feedback-actions">
                <button type="button" onClick={() => void completeSessionWithFeedback()} disabled={isPending}>
                  Save feedback and finish
                </button>
                <button type="button" className="ghost-button" onClick={closeCompletionModal} disabled={isPending}>
                  Keep session open
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : null}

      <div className="notification-tray" aria-live="polite">
        {showRecoveryModal && recoveryPlan ? (
          <div className="notification-card">
            <p className="eyebrow">Schedule adjusted</p>
            <strong>{recoveryPlan.next_time_block ? "Nice work. The rest of the day was reshaped." : "That window is wrapped."}</strong>
            <p>{recoveryPlan.message}</p>
            {recoveryPlan.next_time_block ? (
              <p className="subtle-copy">
                Next: {recoveryPlan.next_time_block.title}
                {recoveryPlan.suggested_break_minutes ? ` after a ${recoveryPlan.suggested_break_minutes}m reset.` : "."}
              </p>
            ) : null}
            <div className="notification-actions">
              {recoveryPlan.next_time_block ? (
                <>
                  {recoveryPlan.suggested_break_minutes ? (
                    <button type="button" onClick={startRecoveryBreak}>
                      Take break
                    </button>
                  ) : (
                    <button type="button" onClick={() => void beginRecoveredBlock()}>
                      Start next
                    </button>
                  )}
                  <button className="ghost-button" type="button" onClick={() => void beginRecoveredBlock()}>
                    Skip break
                  </button>
                </>
              ) : (
                <button className="ghost-button" type="button" onClick={() => setShowRecoveryModal(false)}>
                  Dismiss
                </button>
              )}
            </div>
          </div>
        ) : null}

        {showBreakModal && recoveryPlan ? (
          <div className="notification-card">
            <p className="eyebrow">Break</p>
            <strong>Take a breath</strong>
            <p>The next task is ready. Use this reset so the schedule stays calm instead of rushed.</p>
            <div className="notification-timer">{formatElapsed(breakSecondsLeft)}</div>
            <div className="notification-actions">
              <button
                type="button"
                onClick={() => {
                  setShowBreakModal(false);
                  setShowResumeModal(true);
                }}
              >
                I&apos;m ready
              </button>
            </div>
          </div>
        ) : null}

        {showResumeModal && recoveryPlan?.next_time_block ? (
          <div className="notification-card">
            <p className="eyebrow">Back in</p>
            <strong>Get to it</strong>
            <p>{recoveryPlan.next_time_block.title} is lined up and ready when you are.</p>
            <div className="notification-actions">
              <button type="button" onClick={() => void beginRecoveredBlock()}>
                Start next task
              </button>
              <button className="ghost-button" type="button" onClick={() => setShowResumeModal(false)}>
                Later
              </button>
            </div>
          </div>
        ) : null}
      </div>
      </main>
    </div>
  );
}

function formatElapsed(totalSeconds: number) {
  const minutes = Math.floor(totalSeconds / 60);
  const remainingSeconds = totalSeconds % 60;

  return `${minutes}:${remainingSeconds.toString().padStart(2, "0")}`;
}

function formatDelta(estimatedMinutes: number | null, actualMinutes: number | null) {
  if (estimatedMinutes === null || actualMinutes === null) {
    return "Pending";
  }

  const delta = actualMinutes - estimatedMinutes;
  if (delta === 0) {
    return "On target";
  }

  return `${delta > 0 ? "+" : ""}${formatDurationMinutes(Math.abs(delta))}`;
}

function describeSessionDuration(session: SessionRecord) {
  if (!session.ended_at && session.elapsed_minutes === null) {
    return "In progress";
  }

  const minutes =
    session.elapsed_minutes ??
    Math.max(0, Math.round((parseApiDate(session.ended_at!).getTime() - parseApiDate(session.started_at).getTime()) / 60000));

  return formatDurationMinutes(minutes);
}

function latestElapsedMinutes(sessions: SessionRecord[], timeBlockId: string) {
  const matching = sessions.find((session) => session.time_block_id === timeBlockId && session.status === "completed");
  return matching?.elapsed_minutes ?? null;
}

function getScheduledDurationMinutes(block: ScheduleGenerationResponse["time_blocks"][number]) {
  return Math.max(0, Math.round((parseApiDate(block.end_at).getTime() - parseApiDate(block.start_at).getTime()) / 60000));
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("en-IN", {
    dateStyle: "medium",
    timeStyle: "short"
  }).format(parseApiDate(value));
}

function parseApiDate(value: string) {
  const hasExplicitTimezone = /[zZ]|[+-]\d{2}:\d{2}$/.test(value);
  return new Date(hasExplicitTimezone ? value : `${value}Z`);
}

function formatDurationMinutes(value: number | null) {
  if (value === null) {
    return "Not set";
  }

  const hours = Math.floor(value / 60);
  const minutes = value % 60;

  if (hours === 0) {
    return `${minutes}m`;
  }

  if (minutes === 0) {
    return `${hours}h`;
  }

  return `${hours}h ${minutes}m`;
}

function describeFeedback(session: SessionRecord) {
  const parts: string[] = [];

  if (session.difficulty_feedback) {
    switch (session.difficulty_feedback) {
      case "less_than_expected":
        parts.push("Finished faster than expected");
        break;
      case "longer_than_expected":
        parts.push("Took longer than expected");
        break;
      case "as_expected":
        parts.push("About as expected");
        break;
      default:
        parts.push(session.difficulty_feedback);
        break;
    }
  }

  if (session.feedback_reasons) {
    parts.push(session.feedback_reasons);
  }

  if (session.feedback_notes) {
    parts.push(session.feedback_notes);
  }

  return parts.length ? parts.join(" | ") : "No feedback logged";
}
