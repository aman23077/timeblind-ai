"use client";

import { useEffect, useState } from "react";

type Policy = { sessions?: Array<{ session_id: string; switches: number; coverage: number; slippage_factor: number; overrun_minutes: number }>;
  nudges: Array<{ id: string; message: string; kind: string }> };

async function call(path: string, body?: unknown) {
  const response = await fetch("/api/v1/policy/" + path, {
    method: "POST", credentials: "same-origin",
    headers: { "Content-Type": "application/json", "X-TimeBlind-Client": "web" },
    body: body ? JSON.stringify(body) : undefined
  });
  if (!response.ok) throw new Error("Could not update adaptive planning.");
  return response.json();
}

export function AdaptiveAssistant({ sessionId }: { sessionId?: string }) {
  const [policy, setPolicy] = useState<Policy | null>(null);
  const [remaining, setRemaining] = useState(15);
  const [error, setError] = useState("");
  const [notifications, setNotifications] = useState(false);
  useEffect(() => {
    let disposed = false;
    let timeout: ReturnType<typeof setTimeout>;
    const shown = new Set<string>();
    async function refresh() {
      try {
        const result: Policy = await call("tick");
        if (disposed) return;
        setPolicy(result);
        setError("");
        window.dispatchEvent(new Event("timeblind-plan-updated"));
        for (const nudge of result.nudges) {
          if (notifications && !shown.has(nudge.id) && Notification.permission === "granted") {
            new Notification("TimeBlindAI", { body: nudge.message, tag: nudge.id });
            shown.add(nudge.id);
          }
        }
      } catch (failure) {
        if (!disposed) setError((failure as Error).message);
      }
      if (!disposed) timeout = setTimeout(refresh, 30000);
    }
    void refresh();
    return () => { disposed = true; clearTimeout(timeout); };
  }, [sessionId, notifications]);

  async function action(path: string, body: unknown) {
    try {
      await call(path, body);
      setPolicy(await call("tick"));
      setError("");
      window.dispatchEvent(new Event("timeblind-plan-updated"));
    } catch (failure) { setError((failure as Error).message); }
  }
  const metrics = policy?.sessions?.find((item) => item.session_id === sessionId);
  return <section className="panel activity-panel">
    <h2>Adaptive planning</h2>
    <p>Unfinished work is fitted into the remaining hours. Plans refresh as the session and task list change.</p>
    {metrics && <p>Past planned finish {metrics.overrun_minutes} min · Slippage {Math.round(metrics.slippage_factor * 100)}% · Sustained app switches in five minutes {metrics.switches} · Monitoring coverage {Math.round(metrics.coverage * 100)}%</p>}
    {sessionId && <form className="session-action-row" onSubmit={(event) => { event.preventDefault(); void action("sessions/" + sessionId + "/remaining", { remaining_minutes: remaining }); }}>
      <label>Estimated minutes remaining<input type="number" min={1} max={1440} value={remaining} onChange={(event) => setRemaining(Number(event.target.value))} required /></label>
      <button type="submit">Update remaining time</button>
    </form>}
    {!notifications && <button type="button" className="ghost-button" onClick={async () => {
      if (!("Notification" in window)) { setError("Browser notifications are unavailable. Reminders appear here."); return; }
      const permission = await Notification.requestPermission();
      setNotifications(permission === "granted");
      if (permission !== "granted") setError("Browser notifications are off. Reminders appear here.");
    }}>Enable browser reminders</button>}
    {policy?.nudges.map((nudge) => <div className="result-card" role="status" key={nudge.id}>
      <p>{nudge.message}</p><div className="session-action-row">
        <button onClick={() => void action("nudges/" + nudge.id, { action: "dismiss" })}>Dismiss</button>
      </div></div>)}
    {error && <p role="alert" className="error-banner">{error}</p>}
  </section>;
}
