"use client";

import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { ApiError, loginUser, registerUser, resetPassword } from "../lib/api";
import type { UserDetail } from "../lib/api";

export function AuthForm({ onAuthenticated }: { onAuthenticated: (user: UserDetail) => void }) {
  const [mode, setMode] = useState<"login" | "register" | "reset">("login");
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [retryAt, setRetryAt] = useState(0);
  const [waitSeconds, setWaitSeconds] = useState(0);
  useEffect(() => {
    if (!retryAt) return;
    const tick = () => setWaitSeconds(Math.max(0, Math.ceil((retryAt-Date.now())/1000)));
    tick();
    const timer = window.setInterval(tick,1000);
    return () => window.clearInterval(timer);
  }, [retryAt]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || waitSeconds > 0) return;
    const form = event.currentTarget;
    const data = new FormData(form);
    const password = String(data.get("password") ?? "");
    setError("");
    setMessage("");
    setBusy(true);
    try {
      if (mode === "reset") {
        if (password !== data.get("confirmPassword")) throw new Error("Passwords do not match.");
        setMessage((await resetPassword(String(data.get("token") ?? "").trim(), password, email.trim())).message);
        form.reset();
        setMode("login");
      } else if (mode === "register") {
        if (password !== data.get("confirmPassword")) throw new Error("Passwords do not match.");
        const user = await registerUser({
          email: email.trim(), password,
          display_name: String(data.get("displayName") ?? "").trim(),
          time_zone: String(data.get("timeZone") ?? "Asia/Kolkata"),
          participant_type: String(data.get("participantType") ?? "student"),
          primary_task_focus: String(data.get("primaryTaskFocus") ?? "study"),
          preferred_nudge_style: String(data.get("preferredNudgeStyle") ?? "supportive"),
          consent_to_research: data.get("consentToResearch") === "on" ? "true" : "false"
        });
        form.reset();
        onAuthenticated(user);
      } else {
        const user = await loginUser(email.trim(), password);
        form.reset();
        onAuthenticated(user);
      }
    } catch (failure) {
      if (failure instanceof ApiError && failure.status === 429) {
        setRetryAt(Date.now()+failure.retryAfterSeconds*1000);
        setWaitSeconds(failure.retryAfterSeconds);
      }
      setError(failure instanceof Error ? failure.message : "Please try again.");
    } finally {
      setBusy(false);
    }
  }

  function changeMode(next: typeof mode) {
    setMode(next);
    setError("");
    setMessage("");
  }

  return (
    <form key={mode} className="onboarding-card welcome-onboarding-card" onSubmit={submit}>
      <h2>{mode === "login" ? "Log in to your workspace" : mode === "register" ? "Create your account" : "Password setup/reset"}</h2>
      {waitSeconds > 0 && <p role="status">Please wait {Math.floor(waitSeconds/60)}m {waitSeconds%60}s before another attempt. Repeated attempts will not restore access sooner.</p>}
      <div className="session-action-row">
        <button type="button" className="ghost-button" aria-pressed={mode === "login"} disabled={busy} onClick={() => changeMode("login")}>Log in</button>
        <button type="button" className="ghost-button" aria-pressed={mode === "register"} disabled={busy} onClick={() => changeMode("register")}>Register</button>
      </div>
      <label>Email
        <input name="email" type="email" autoComplete="username" required value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@example.com" />
      </label>
      {mode === "reset" ? <>
        <p>Enter the account email and the administrator's recovery key to set a password. The recovery key works across accounts and remains valid until replaced.</p>
        <label>Recovery key<input name="token" type="password" autoComplete="off" required /></label>
      </> : null}
      <label>{mode === "reset" ? "New password" : "Password"}
        <input name="password" type="password" autoComplete={mode === "login" ? "current-password" : "new-password"} minLength={1} maxLength={1024} required />
      </label>
      {mode !== "login" ? <>
        <p className="subtle-copy">Choose a password and enter it again to confirm.</p>
        <label>Confirm password<input name="confirmPassword" type="password" autoComplete="new-password" minLength={1} maxLength={1024} required /></label>
      </> : null}
      {mode === "register" ? <>
        <label>Name<input name="displayName" autoComplete="name" maxLength={120} required /></label>
        <label>Time zone<input name="timeZone" defaultValue="Asia/Kolkata" required /></label>
        <div className="form-grid">
          <label>I am mainly a<select name="participantType" defaultValue="student">
            <option value="student">Student</option><option value="developer">Developer</option>
            <option value="working_professional">Working professional</option><option value="other">Other</option>
          </select></label>
          <label>I mostly want to track<select name="primaryTaskFocus" defaultValue="study">
            <option value="study">Study tasks</option><option value="coding">Coding tasks</option>
            <option value="assignments">Assignments</option><option value="writing">Writing</option>
            <option value="daily_admin">Daily admin</option><option value="mixed">Mixed work</option>
          </select></label>
        </div>
        <label>Reminder style<select name="preferredNudgeStyle" defaultValue="supportive">
          <option value="supportive">Supportive</option><option value="direct">Direct</option><option value="minimal">Minimal</option>
        </select></label>
        <label className="consent-card"><input name="consentToResearch" type="checkbox" /><span>I agree to the optional use of my task timing, feedback, and app activity (if I enable monitoring) for the academic project.</span></label>
      </> : null}
      <button type="submit" disabled={busy || waitSeconds > 0}>{busy ? "Please wait…" : mode === "login" ? "Log in securely" : mode === "register" ? "Create account" : "Save password"}</button>
      {mode !== "reset" ? <button className="ghost-button" type="button" disabled={busy} onClick={() => changeMode("reset")}>Password setup/reset</button> : null}
      {error ? <p role="alert" className="error-banner">{error}</p> : null}
      {message ? <p role="status">{message}</p> : null}
    </form>
  );
}
