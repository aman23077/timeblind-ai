"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { AuthForm } from "../../components/auth-form";
import { logoutUser } from "../../lib/api";
import { useAuth } from "../../lib/use-auth";
import { PilotScheduler, PilotDesktop } from "../../components/pilot-extras";
import styles from "./study.module.css";

type StudyTask = { id: string; title: string; outcome: string; user_estimate_minutes: number; rules_estimate_minutes: number;
  started_at: string | null; actual_minutes: number | null; timing_source: string; session_id: string | null; steps: Array<{title: string; minutes: number}> };
type Study = { enrolled: boolean; withdrawn: boolean; participant_code: string | null; schedule_trials: import("../../components/pilot-extras").Trial[]; feedback_submitted: boolean; feedback: Record<string, string | number> | null; tasks: StudyTask[] };
async function api<T>(path: string, payload?: unknown): Promise<T> {
  const response = await fetch(`/api/v1/study${path}`, { method: payload === undefined ? "GET" : "POST", credentials: "same-origin",
    cache: "no-store", headers: { "Content-Type": "application/json", "X-TimeBlind-Client": "web" },
    body: payload === undefined ? undefined : JSON.stringify(payload) });
  const data = await response.json().catch(() => null);
  if (!response.ok) throw new Error(typeof data?.detail === "string" ? data.detail : "Could not save. Check your connection and inputs, then try again.");
  return data;
}
function fields(event: FormEvent<HTMLFormElement>) { event.preventDefault(); return new FormData(event.currentTarget); }
const labels = { ease: "The app was easy to use", clarity: "The task plan was clear", usefulness: "The app helped me plan my work",
  trust: "I could rely on the time estimates", use_again: "I would use this app again" };

export default function StudyPage() {
  const { user, setUser, loading } = useAuth();
  const [study, setStudy] = useState<Study | null>(null);
  const [busy, setBusy] = useState(false);
  const saving = useRef(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [withdrawConfirm, setWithdrawConfirm] = useState(false);
  const [clock, setClock] = useState(Date.now());
  const refresh = async () => setStudy(await api<Study>("/me"));
  useEffect(() => {
    setStudy(null);
    if (!user) return;
    let disposed = false;
    void api<Study>("/me").then(s => { if (!disposed) setStudy(s); }).catch(e => { if (!disposed) setError(e.message); });
    return () => { disposed = true; };
  }, [user]);
  useEffect(() => { const id = window.setInterval(() => setClock(Date.now()), 1000); return () => window.clearInterval(id); }, []);
  async function save(path: string, payload: unknown, success: string, form?: HTMLFormElement) {
    if (saving.current) return;
    saving.current = true;
    setBusy(true); setError(""); setMessage("");
    try {
      await api(path, payload);
      form?.reset();
      setMessage(success);
      try { await refresh(); }
      catch { setError("Your submission was saved, but progress could not reload. Use Retry loading; do not submit it again."); }
    }
    catch (failure) { setError(failure instanceof Error ? failure.message : "Could not save."); }
    finally { saving.current = false; setBusy(false); }
  }
  const completed = study?.tasks.filter(t => t.outcome === "completed").length ?? 0;
  const active = study?.tasks.some(t => t.outcome === "active");
  return <main className={styles.page}>
    <header className={styles.header}><Link href="/">TimeBlindAI</Link><nav aria-label="Study navigation"><Link href="/">Open app</Link>{user?.is_admin && <Link href="/study/admin">Study results</Link>}{user && <button className={styles.secondary} disabled={busy} onClick={async () => { try { await logoutUser(); setStudy(null); setUser(null); } catch { setError("Could not sign out. Please retry."); } }}>Sign out</button>}</nav></header>
    <section className={styles.hero}><span className={styles.eyebrow}>BTP participant pilot · November 2026</span>
      <h1>Help us test better task planning.</h1><p>Try TimeBlindAI on three real tasks. Tell us what worked, what got in the way, and how the estimates compared with your actual time.</p>
      <div className={styles.facts}><span>About 10 minutes of setup and feedback</span><span>Your own everyday tasks</span><span>Participation is voluntary</span></div>
    </section>
    <section className={styles.card}><h2>What does TimeBlindAI do?</h2><p>It breaks a task into steps, estimates work time, builds a schedule around available time, and helps you review delays and friction. Estimates are suggestions, not promises.</p><ol><li>Record three task attempts and inspect their plans.</li><li>Optionally connect desktop monitoring during real work.</li><li>Try the scheduler with three tasks and a limited time window. Inspect the order, breaks and tasks that cannot fit.</li><li>Rate the schedule and its guidance, then submit your overall review.</li></ol><p>You can run a short interface rehearsal without waiting for the estimated duration. Mark rehearsal values honestly; they are excluded from real timing accuracy.</p></section>
    {error && <p className={styles.error} role="alert">{error} <button type="button" onClick={() => { setError(""); void refresh().catch(e => setError(e.message)); }}>Retry loading</button></p>}
    {message && <p className={styles.notice} role="status">{message}</p>}
    {loading ? <p role="status">Checking your account…</p> : !user ? <section className={styles.card}><h2>Sign in to join</h2><p>Create an account if this is your first visit. Study consent is a separate step after sign-in.</p><AuthForm onAuthenticated={setUser} /></section>
      : !study ? <p role="status">Loading your study progress…</p>
      : study.withdrawn ? <section className={styles.card}><h2>You have withdrawn</h2><p>Your records are excluded from the study results and study exports. You can still use the main app. Contact the team if you also want your stored records deleted.</p><Link href="/">Return to app</Link></section>
      : !study.enrolled ? <section className={styles.card}><h2>Before you begin</h2>
        <p>We are Aarush Gaur and Aman Sachdeva, studying how people use TimeBlindAI for task planning. This is a small student usability and estimation pilot, not a medical assessment.</p>
        <p>You will choose three tasks, give your own duration guess before seeing the app estimate, time each task, record breaks, and answer five feedback questions. For live measurements, choose tasks you have not started with a clear finish point, usually 15–60 minutes each. For a quick walkthrough, choose manual rehearsal when finishing. Recalled real task times are also accepted but analyzed separately. Your normal task time is additional to the setup and feedback time.</p>
        <p>We store your consent, task descriptions and categories, predictions, timing, reported breaks and feedback. Your login email identifies your account to the project team. Report exports use a random participant code and omit emails, task titles and written comments. Aggregate results may appear in our graded BTP report.</p>
        <p>Do not enter private or sensitive information in task names or comments. Optional Windows monitoring records executable names, activity timestamps and input inactivity only after you enable it and run the companion. It is not screen recording and does not measure attention. You can skip it. The study task and scheduler exercises use rules without an AI provider call.</p>
        <p>You can stop or withdraw at any time. Withdrawal excludes your records from future study analysis; contact us for deletion. The team plans to delete identifiable pilot records by December 25, 2026. Anonymous aggregate results in the report may remain. Questions or deletion requests: <a href="mailto:aman23077@iiitd.ac.in">aman23077@iiitd.ac.in</a>.</p>
        <form onSubmit={e => { const d = fields(e); void save("/enroll", { adult: d.get("adult") === "on", consent: d.get("consent") === "on", baseline_frequency: d.get("frequency") }, "You have joined the pilot."); }}>
          <fieldset disabled={busy}><legend>About your planning</legend><label>How often do tasks take longer than you initially expect?<select name="frequency" required defaultValue=""><option value="" disabled>Select one</option>{["never", "rarely", "sometimes", "often", "very_often"].map(v => <option key={v} value={v}>{v.replace(/_/g, " ")}</option>)}</select></label>
          <label className={styles.check}><input type="checkbox" name="adult" required />I am at least 18 years old.</label>
          <label className={styles.check}><input type="checkbox" name="consent" required />I have read the information above and agree to take part in this study.</label>
          <button type="submit">Join the pilot</button></fieldset>
        </form>
      </section> : <>
        <section className={styles.card}><div className={styles.sectionHead}><div><span className={styles.eyebrow}>Your progress</span><h2>{completed} of 3 tasks completed</h2></div><span className={styles.badge}>{study.feedback_submitted ? "Feedback saved" : "Feedback pending"}</span></div>
          <progress className={styles.progress} max={3} value={Math.min(3, completed)} aria-label="Completed pilot tasks" />
          {completed >= 3 && <p className={styles.notice}>Your three tasks are complete. <a href="#feedback">Submit your final feedback</a> to finish the pilot.</p>}
          <p>Participant code: <code>{study.participant_code}</code></p><ol><li>Add one task with a specific finish point, such as “Read and summarize five pages”. Enter your own estimate first.</li><li>Start the timer when you start working. Keep track of time spent on breaks or unrelated work.</li><li>Finish the record and enter those break minutes. Repeat for three tasks, then submit feedback below.</li></ol>
          <p>After adding a task, <Link href="/" target="_blank">open the main app in another tab</Link> to inspect its task plan and try generating a schedule. Use the timer on this page for pilot tasks. Do not also start a second focus timer for the same task. Return here after using the app.</p>
        </section>
        <section className={styles.card}><h2>Add a real task</h2><p>Your own estimate is saved before the app’s estimate is shown. Neither prediction can be edited afterwards. Use a new record if your task scope changes.</p>
          <form onSubmit={e => { const d = fields(e); void save("/tasks", { title: d.get("title"), task_type: d.get("task_type"), difficulty: d.get("difficulty"), user_estimate_minutes: Number(d.get("estimate")) }, "Task saved. The app estimate is shown below.", e.currentTarget); }}>
            <fieldset disabled={busy}><legend>Task details</legend><label>What exactly will you finish?<input name="title" minLength={5} maxLength={180} required placeholder="Read and summarize five pages of course notes" /></label>
            <div className={styles.columns}><label>Category<select name="task_type" defaultValue="study">{["study", "reading", "writing", "coding", "assignment", "admin", "chore", "generic"].map(v => <option key={v}>{v}</option>)}</select></label><label>Difficulty<select name="difficulty" defaultValue="medium"><option>easy</option><option>medium</option><option>hard</option></select></label><label>Your estimate in minutes<input name="estimate" type="number" min={5} max={180} step={1} required /></label></div><button type="submit">Save my estimate and show the plan</button></fieldset>
          </form>
        </section>
        <section className={styles.tasks} aria-label="Your study tasks">{[...study.tasks].reverse().map(t => <article className={styles.card} key={t.id}>
          <div className={styles.sectionHead}><h2>{t.title}</h2><span className={styles.badge}>{t.outcome}</span></div>
          <div className={styles.facts}><span>Your guess <strong>{t.user_estimate_minutes} min</strong></span><span>App rules estimate <strong>{t.rules_estimate_minutes} min</strong></span>{t.actual_minutes !== null && <span>Reported work ({t.timing_source?.replace(/_/g," ") ?? "timer"}) <strong>{t.actual_minutes.toFixed(1)} min</strong></span>}</div>
          {t.steps?.length > 0 && <details className={styles.plan}><summary>View your task plan</summary><ol>{t.steps.map((step, i) => <li key={i}>{step.title} <span>({step.minutes} min suggested)</span></li>)}</ol></details>}
          {t.outcome === "planned" && <button disabled={busy || active} onClick={() => void save(`/tasks/${t.id}/start`, {}, "Timer started. Work on your task, then return here.")}>{active ? "Finish your active task first" : "Start working"}</button>}
          {t.outcome === "active" && <><PilotDesktop sessionId={t.session_id} userId={user.id} /><p className={styles.timer} aria-label="Elapsed minutes">{Math.max(0, (clock - new Date(t.started_at!.endsWith("Z") || /[+-]\d\d:\d\d$/.test(t.started_at!) ? t.started_at! : t.started_at! + "Z").getTime()) / 60000).toFixed(1)} <span>minutes elapsed</span></p><p>The timer survives closing this tab. Enter all breaks and unrelated work when you finish. If you forgot the timer, choose unfinished so it is excluded from duration accuracy.</p>
            <form onSubmit={e => { const d = fields(e); void save(`/tasks/${t.id}/finish`, { outcome: d.get("outcome"), break_minutes: Number(d.get("breaks")), timing_source: d.get("timing_source"), manual_minutes: d.get("manual_minutes") ? Number(d.get("manual_minutes")) : null, scope_changed: d.get("scope") === "yes", friction: d.get("friction") }, "Task outcome saved."); }}>
              <fieldset disabled={busy}><legend>How did the task go?</legend><label>How was work time obtained?<select name="timing_source"><option value="timer">Live timer — real work performed now</option><option value="recalled_real">Manual — recalled time from real previous work</option><option value="rehearsal">Manual — interface rehearsal or hypothetical value</option></select></label><label>Manual work minutes, excluding breaks (only for manual modes)<input name="manual_minutes" type="number" min={1} max={1440} step="0.1" /></label><p>Manual values do not change the live elapsed clock. Recalled and rehearsal values are reported separately and excluded from prospective duration accuracy.</p><div className={styles.columns}><label>Outcome<select name="outcome"><option value="completed">I completed the original task</option><option value="unfinished">Unfinished or timer unreliable</option></select></label><label>Minutes of breaks or unrelated work<input type="number" name="breaks" min={0} max={1440} step="0.1" required defaultValue={0} /></label></div>
              <label>Did the scope change after the estimate?<select name="scope" defaultValue="" required><option value="" disabled>Select one</option><option value="no">No</option><option value="yes">Yes</option></select></label>
              <label>Main source of friction<select name="friction"><option value="none">None</option><option value="interruption">Interruption</option><option value="harder_than_expected">Harder than expected</option><option value="unclear_scope">Unclear task scope</option><option value="technical_problem">Technical problem</option><option value="other">Other</option></select></label><button type="submit">Finish and save outcome</button></fieldset>
            </form></>}
        </article>)}</section>
        <PilotScheduler attempts={study.tasks.filter(t => t.outcome === "completed" || t.outcome === "unfinished").length} trials={study.schedule_trials ?? []} onSaved={refresh} />
        <section className={styles.card} id="feedback"><h2>Final feedback</h2><p>Submit after your three tasks, or after trying the app if you need to stop early. Answer based on your own experience. These are custom pilot questions, not a standardized usability score.</p>
          <form key={JSON.stringify(study.feedback)} onSubmit={e => { const d = fields(e); void save("/feedback", { ...Object.fromEntries(Object.keys(labels).map(k => [k, Number(d.get(k))])), best_part: d.get("best_part"), biggest_problem: d.get("biggest_problem"), suggestion: d.get("suggestion") }, "Thank you. Your feedback has been saved."); }}>
            <fieldset disabled={busy || !study.tasks.some(t => t.outcome === "completed" || t.outcome === "unfinished")}><legend>1 strongly disagree · 2 disagree · 3 neutral · 4 agree · 5 strongly agree</legend>
              {Object.entries(labels).map(([k, label]) => <label key={k}>{label}<select name={k} required defaultValue={study.feedback?.[k] ?? ""}><option value="" disabled>Select a response</option>{[1, 2, 3, 4, 5].map(v => <option key={v} value={v}>{v} · {["Strongly disagree", "Disagree", "Neutral", "Agree", "Strongly agree"][v-1]}</option>)}</select></label>)}
              <label>What helped you most? Optional<textarea name="best_part" maxLength={1000} defaultValue={study.feedback?.best_part ?? ""} /></label><label>What was the biggest problem? Optional<textarea name="biggest_problem" maxLength={1000} defaultValue={study.feedback?.biggest_problem ?? ""} /></label><label>What should we improve first? Optional<textarea name="suggestion" maxLength={1000} defaultValue={study.feedback?.suggestion ?? ""} /></label>
              <button type="submit">{study.feedback_submitted ? "Update my feedback" : "Submit feedback"}</button>
            </fieldset>
          </form>
        </section>
        <section className={styles.withdraw}><h2>Your participation</h2><p>Stopping early is fine. You can withdraw your study records from future analysis and exports.</p>{!withdrawConfirm ? <button className={styles.secondary} onClick={() => setWithdrawConfirm(true)}>Withdraw from study</button> : <><p>Withdrawal is permanent for this account in this pilot. Stored records remain private until deletion by the team.</p><button disabled={busy} onClick={() => void save("/withdraw", {}, "Your participation has been withdrawn.")}>Confirm withdrawal</button> <button className={styles.secondary} onClick={() => setWithdrawConfirm(false)}>Keep participating</button></>}</section>
      </>}
    <footer className={styles.footer}>TimeBlindAI · Student research pilot · Questions: aman23077@iiitd.ac.in</footer>
  </main>;
}
