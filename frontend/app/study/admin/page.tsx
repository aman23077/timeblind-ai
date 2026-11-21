"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { AuthForm } from "../../../components/auth-form";
import { useAuth } from "../../../lib/use-auth";
import styles from "../study.module.css";
type Method = { tasks: number; participants: number; mae_minutes: number | null; median_absolute_error_minutes: number | null; within_15_percent: number | null; participant_mean_mae_minutes: number | null };
type Summary = { ai_paired_comparison: Record<string,{n:number;mae_minutes:number|null;within_15_percent:number|null}>; adherence: Record<string,number>; ai_calls: Record<string,{attempts:number;successes:number}>; task_review_ratings: Record<string,number[]>; timing_sources: Record<string, number>; scheduler: {exercises: number; reviewed: number; constraint_pass_count: number; ratings: Record<string, number[]>}; consenting_participants: number; recorded_tasks: number; started_tasks: number; completed_tasks: number; unfinished_tasks: number; active_tasks: number; eligible_tasks: number; excluded_completed_tasks: number; feedback_responses: number; participants_with_three_completed_tasks: number; methods: Record<string, Method>; ratings: Record<string, {n: number; median: number | null; counts_1_to_5: number[]}> };
type Comment = { participant_code: string; best_part: string; biggest_problem: string; suggestion: string };
export default function StudyAdmin() {
  const {user, setUser, loading} = useAuth();
  const [summary, setSummary] = useState<Summary | null>(null);
  const [comments, setComments] = useState<Comment[]>([]);
  const [error, setError] = useState("");
  async function refresh() {
    setError("");
    setComments([]);
    try {
      const response = await fetch("/api/v1/study/admin/summary", {cache: "no-store"});
      if (!response.ok) throw new Error("Could not load study results. Check your administrator access and backend deployment.");
      setSummary(await response.json());
    } catch(e) { setError(e instanceof Error ? e.message : "Could not load results."); }
  }
  useEffect(() => { if(user?.is_admin) void refresh(); }, [user]);
  async function loadComments() {
    try { const r = await fetch("/api/v1/study/admin/comments", {cache: "no-store"}); if(!r.ok) throw new Error("Could not load comments."); setComments(await r.json()); }
    catch(e) { setError(e instanceof Error ? e.message : "Could not load comments."); }
  }
  return <main className={styles.page}><header className={styles.header}><Link href="/study">TimeBlindAI pilot</Link><Link href="/admin">Account administration</Link></header><h1>Study results</h1>
    {loading ? <p>Checking access…</p> : !user ? <AuthForm onAuthenticated={setUser}/> : !user.is_admin ? <p>Administrator access is required.</p> : <>
      <p>Consenting participants only. Withdrawn records are excluded. Empty results mean no observations yet.</p><button onClick={() => void refresh()}>Refresh results</button> <a href="/api/v1/study/admin/export">Download report data ZIP</a>
      {error && <p role="alert" className={styles.error}>{error}</p>}
      {summary && <><section className={styles.card}><h2>AI pilot evidence and scheduler testing</h2><h3>Fair paired comparison on identical AI task outcomes</h3>{Object.entries(summary.ai_paired_comparison).map(([k,v])=><p key={k}>{k}: N={v.n}; MAE {v.mae_minutes ?? "no data"} min; within 15 min {v.within_15_percent ?? "no data"}%</p>)}<h3>AI request reliability</h3>{Object.entries(summary.ai_calls).map(([k,v])=><p key={k}>{k}: {v.successes} successful / {v.attempts} requests</p>)}<h3>Per-task feedback distributions</h3>{Object.entries(summary.task_review_ratings).map(([k,v])=><p key={k}>{k}: {v.join(", ")} (counts 1–5)</p>)}<h3>Recorded schedule execution</h3>{Object.entries(summary.adherence).map(([k,v])=><p key={k}>{k.replace(/_/g," ")}: {v}</p>)}<p>{Object.entries(summary.timing_sources).map(([k,n])=>`${k.replace(/_/g," ")}: ${n}`).join(" · ")}. Only prospective live-timer records enter duration accuracy.</p><p>Scheduler exercises: {summary.scheduler.exercises}; reviewed: {summary.scheduler.reviewed}; all checked constraints passed: {summary.scheduler.constraint_pass_count}. New AI plans are saved in the original app. Constraint validity, user ratings and recorded execution are separate outcomes; historical hypothetical trials remain in the counts.</p><div className={styles.tableWrap}><table><thead><tr><th>Scheduler question</th><th>Counts for 1, 2, 3, 4, 5</th></tr></thead><tbody>{Object.entries(summary.scheduler.ratings).map(([k,v])=><tr key={k}><th>{k.replace(/_/g," ")}</th><td>{v.join(", ")}</td></tr>)}</tbody></table></div></section><section className={`${styles.card} ${styles.metricGrid}`}>
        {[ ["Consenting participants", summary.consenting_participants], ["Completed tasks", summary.completed_tasks], ["Eligible accuracy records", summary.eligible_tasks], ["Final feedback responses", summary.feedback_responses], ["People with 3 completed tasks", summary.participants_with_three_completed_tasks], ["Unfinished tasks", summary.unfinished_tasks], ["Active tasks", summary.active_tasks], ["Completed records excluded", summary.excluded_completed_tasks] ].map(([label, value]) => <div key={label}><strong>{value}</strong>{label}</div>)}
      </section><section className={styles.card}><h2>Duration estimation</h2><p>Human and rules share the eligible cohort. AI has its own explicit successful-plan cohort. Eligibility requires completion, unchanged scope, and at least one minute of recorded work. New plans use the LLM. Rules are retained as an independent baseline. AI error uses only eligible records with an AI snapshot; check sample sizes before comparisons.</p>
        <div className={styles.tableWrap}><table><thead><tr><th>Method</th><th>Tasks</th><th>People</th><th>MAE min</th><th>Median error min</th><th>Within 15 min %</th><th>Mean participant MAE min</th></tr></thead><tbody>{Object.entries(summary.methods).map(([k,m]) => <tr key={k}><th>{k}</th>{[m.tasks,m.participants,m.mae_minutes,m.median_absolute_error_minutes,m.within_15_percent,m.participant_mean_mae_minutes].map((v,i) => <td key={i}>{v ?? "No data"}</td>)}</tr>)}</tbody></table></div></section>
        <section className={styles.card}><h2>Feedback distribution</h2><p>Custom five-point questions. Report each distribution separately; do not call this SUS or a clinical score.</p><div className={styles.tableWrap}><table><thead><tr><th>Question</th><th>N</th><th>Median</th><th>Counts for 1, 2, 3, 4, 5</th></tr></thead><tbody>{Object.entries(summary.ratings).map(([k,r]) => <tr key={k}><th>{k.replace(/_/g, " ")}</th><td>{r.n}</td><td>{r.median ?? "No data"}</td><td>{r.counts_1_to_5.join(", ")}</td></tr>)}</tbody></table></div></section></>}
      <section className={styles.card}><h2>Qualitative feedback</h2><p>Comments can contain identifying details. Review and redact before quoting in the report. They are omitted from the download.</p><button onClick={() => void loadComments()}>Load private comments</button>{comments.map(c => <article key={c.participant_code}><h3>{c.participant_code}</h3><p>Helped: {c.best_part || "No response"}</p><p>Problem: {c.biggest_problem || "No response"}</p><p>Suggestion: {c.suggestion || "No response"}</p></article>)}</section>
      <p>This is a short convenience-sample pilot. Repeated tasks from the same person are not independent participants. These results cannot establish causal productivity gains or changes in timeblindness.</p>
    </>}
  </main>;
}
