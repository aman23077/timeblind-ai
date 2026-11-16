"use client";

import { useEffect, useState } from "react";
import { companionCommand, disableActivity, enableActivity, getActivity } from "../lib/api";
import type { ActivitySummary, SessionRecord } from "../lib/api";

function duration(seconds: number) {
  return `${Math.floor(seconds / 60)}m ${Math.floor(seconds % 60)}s`;
}

export function SessionActivity({ session, userId }: { session: SessionRecord; userId: string }) {
  const [summary, setSummary] = useState<ActivitySummary | null>(null);
  const [token, setToken] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const running = session.status === "active" && !session.ended_at;

  useEffect(() => {
    let disposed = false;
    let timeout: ReturnType<typeof setTimeout>;
    async function refresh() {
      try {
        const result = await getActivity(session.id, userId);
        if (!disposed) {
          setSummary(result);
          setError("");
        }
      } catch {
        if (!disposed) setError("Could not refresh activity. Check the backend connection.");
      }
      if (!disposed && running) timeout = setTimeout(refresh, 3000);
    }
    void refresh();
    return () => { disposed = true; clearTimeout(timeout); };
  }, [session.id, running, userId]);

  async function toggle(enable: boolean) {
    setBusy(true);
    setError("");
    try {
      if (enable) {
        const result = await enableActivity(session.id, userId);
        setToken(result.token);
      } else {
        await disableActivity(session.id, userId);
        setToken("");
      }
      setSummary(await getActivity(session.id, userId));
    } catch {
      setError("Could not change monitoring. Check the connection and try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel neutral-panel activity-panel">
      <div className="panel-header">
        <h2>Windows app activity</h2>
        <p>Track foreground apps and inactivity during this focus session. Executable names and activity times are saved to your TimeBlindAI backend.</p>
      </div>
      <p role="status">{summary ? (summary.connected ? "Companion connected · monitoring" : summary.enabled ? "Waiting for companion" : "Monitoring off") : "Loading activity…"}</p>
      {running ? (
        <div className="session-action-row">
          <button type="button" disabled={busy || !summary} onClick={() => void toggle(!summary?.enabled)}>
            {summary?.enabled ? "Stop monitoring" : "Enable app monitoring"}
          </button>
          {summary?.enabled && !token ? <button type="button" className="ghost-button" disabled={busy} onClick={() => void toggle(true)}>Get new pairing token</button> : null}
        </div>
      ) : null}
      {running && summary?.enabled && token && !summary.connected ? (
        <div className="result-card">
          <p>In a second PowerShell window, open the TimeBlindAI project folder and run this command. Keep the companion window open.</p>
          <code className="activity-command">{companionCommand}</code>
          <label>Paste this token when the companion asks
            <input aria-label="Companion pairing token" readOnly value={token} onFocus={(event) => event.target.select()} />
          </label>
        </div>
      ) : null}
      {error ? <p role="alert" className="error-banner">{error}</p> : null}
      {summary ? (
        <div className="result-card">
          <div className="result-row"><span>Device active</span><strong>{duration(summary.active_seconds)}</strong></div>
          <div className="result-row"><span>Idle after {summary.idle_threshold_seconds}s without input</span><strong>{duration(summary.idle_seconds)}</strong></div>
          <div className="result-row"><span>Unobserved time</span><strong>{duration(summary.unobserved_seconds)}</strong></div>
          <div className="result-row"><span>App switches</span><strong>{summary.context_switches}</strong></div>
          {summary.apps.length ? <h3>Active time by app</h3> : <p>App usage appears after the companion connects.</p>}
          {summary.apps.map((app) => <div className="result-row" key={app.name}><span>{app.name}</span><strong>{duration(app.seconds)}</strong></div>)}
          <p className="subtle-copy">Input inactivity can include reading or thinking. Browser tabs share the browser app name. Sampling runs about every two seconds.</p>
        </div>
      ) : null}
    </section>
  );
}
