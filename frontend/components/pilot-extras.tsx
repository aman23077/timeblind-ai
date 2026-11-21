"use client";
import { useEffect, useState } from "react";
import { listSessions } from "../lib/api";
import type { SessionRecord } from "../lib/api";
import { SessionActivity } from "./session-activity";
import styles from "../app/study/study.module.css";

export type Trial = {id: string; review: Record<string, number | string> | null; snapshot: {guidance: string; checks: Record<string, boolean>; blocks: Array<{title: string; start_at: string; end_at: string; kind: string}>; deferred: Array<{title: string; reason: string}>}};
export function PilotDesktop({sessionId, userId}: {sessionId: string | null; userId: string}) {
  const [session, setSession] = useState<SessionRecord | null>(null);
  const [show, setShow] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!show || !sessionId) return;
    let stopped = false;
    void listSessions(userId).then(rows => { if (!stopped) setSession(rows.find(s => s.id === sessionId) ?? null); }).catch(() => {if (!stopped) setError("Could not load session. Close and reopen monitoring to retry.");});
    return () => {stopped = true;};
  }, [sessionId, userId, show]);
  return <details onToggle={e => setShow(e.currentTarget.open)}><summary>Optional desktop access and monitoring</summary><p>Windows only. No screen or keystroke recording. Executable names and activity/idle intervals are stored with your session. Reading or thinking may look idle. Skip this on mobile or macOS. Monitoring requires the Python companion from the project checkout; no browser permission alone can enable it.</p><p>Choose Enable app monitoring below, then run the displayed command in PowerShell from the TimeBlindAI project folder and paste the pairing token into that terminal. Stop monitoring whenever you want. It also stops when you finish this task.</p>{error && <p role="alert">{error}</p>}{show && session && <SessionActivity session={session} userId={userId} />}</details>;
}

async function post(path: string, body: unknown) {
  const r = await fetch("/api/v1/study" + path, {method: "POST", headers: {"Content-Type":"application/json", "X-TimeBlind-Client":"web"}, body:JSON.stringify(body)});
  const data=await r.json();
  if(!r.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Check your inputs and try again.");
  return data;
}
export function PilotScheduler({attempts, trials, onSaved}: {attempts:number; trials:Trial[]; onSaved:()=>Promise<void>}) {
  const [busy,setBusy]=useState(false), [error,setError]=useState("");
  async function submit(path:string, payload:unknown) {
    if(busy)return;
    setBusy(true);setError("");
    try {await post(path,payload);await onSaved();} catch(e){setError(e instanceof Error?e.message:"Could not save.");} finally{setBusy(false);}
  }
  const trial=trials[trials.length-1];
  return <section className={styles.card}><h2>Try the scheduler</h2><p>After three task attempts, create a hypothetical schedule. Give three task scopes and planned durations, then set the available window. Try a shorter window too: does the app explain what cannot fit? You do not need to execute this schedule to review the interface.</p>
    {attempts<3 ? <p>{3-attempts} more task attempt(s) needed to unlock this exercise.</p> : <form onSubmit={e=>{e.preventDefault();const d=new FormData(e.currentTarget);void submit("/scheduler",{window_minutes:Number(d.get("window")),tasks:[0,1,2].map(i=>({title:d.get("title"+i),user_estimate_minutes:Number(d.get("minutes"+i)),task_type:"study",difficulty:"medium"}))});}}><fieldset disabled={busy}><legend>Plan three tasks</legend>{[0,1,2].map(i=><div className={styles.columns} key={i}><label>Task {i+1} scope<input name={"title"+i} minLength={5} maxLength={180} required defaultValue={["Review course notes","Practice five problems","Write a short summary"][i]}/></label><label>Planned minutes<input name={"minutes"+i} type="number" min={5} max={180} required defaultValue={[25,30,20][i]}/></label></div>)}<label>Available minutes<input name="window" type="number" min={15} max={480} required defaultValue={90}/></label><button>Generate exercise schedule</button></fieldset></form>}
    {error&&<p role="alert">{error}</p>}
    {trial&&<><h3>Your proposed schedule</h3><p>{trial.snapshot.guidance}</p><ol>{trial.snapshot.blocks.map((b,i)=><li key={i}>{b.title}: {new Date(b.start_at).toLocaleTimeString([], {hour:"2-digit",minute:"2-digit"})}–{new Date(b.end_at).toLocaleTimeString([], {hour:"2-digit",minute:"2-digit"})}</li>)}</ol>{trial.snapshot.deferred.map((t,i)=><p key={i}>Deferred: {t.title} — {t.reason}</p>)}<p>Automatic checks: {Object.entries(trial.snapshot.checks).map(([k,v])=>`${k.replace(/_/g," ")}: ${v?"pass":"fail"}`).join("; ")}. Passing these checks does not prove that the time estimates are accurate.</p>
    <form key={trial.id} onSubmit={e=>{e.preventDefault();const d=new FormData(e.currentTarget);void submit(`/scheduler/${trial.id}/review`,{...Object.fromEntries(["feasible","ordering","feedback_useful","explanation_clear"].map(k=>[k,Number(d.get(k))])),comments:d.get("comments")});}}><fieldset disabled={busy}><legend>Review this schedule — 1 strongly disagree to 5 strongly agree</legend>{Object.entries({feasible:"This plan seems feasible in the selected window",ordering:"The task order makes sense",feedback_useful:"The guidance about breaks and deferred work is useful",explanation_clear:"I understand why tasks were scheduled or deferred"}).map(([k,label])=><label key={k}>{label}<select required name={k} defaultValue={trial.review?.[k]??""}><option value="" disabled>Choose</option>{[1,2,3,4,5].map(v=><option key={v}>{v}</option>)}</select></label>)}<label>What would you change? Optional<textarea name="comments" maxLength={1000} defaultValue={trial.review?.comments??""}/></label><button>{trial.review?"Update scheduler review":"Save scheduler review"}</button>{trial.review&&<p role="status">Scheduler review saved. Continue to final feedback below.</p>}</fieldset></form></>}
  </section>;
}
