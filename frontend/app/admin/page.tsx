"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useAuth } from "../../lib/use-auth";
import { logoutUser } from "../../lib/api";
import { AuthForm } from "../../components/auth-form";

type User = { id: string; email: string; display_name: string; created_at: string };
type Entries = { user: User; task_count: number; session_count: number;
  tasks: Array<{ id: string; title: string; status: string; estimated_minutes: number | null; actual_minutes: number | null }>;
  sessions: Array<{ id: string; started_at: string; status: string; elapsed_minutes: number | null }> };
type Records = { table: string; tables: string[]; columns: string[]; total: number; data_source: string; dataset_id: string | null; rows: Record<string, unknown>[] };

async function read<T>(path: string): Promise<T> {
  const response = await fetch(`/api/v1/admin/${path}`, { credentials: "same-origin", cache: "no-store" });
  if (!response.ok) throw new Error(response.status === 401 ? "Log in to your administrator account first." : response.status === 403 ? "This account does not have administrator access." : `Could not load entries (HTTP ${response.status}). The user count is unavailable, not zero.`);
  return response.json();
}

export default function AdminPage() {
  const { user: currentUser, setUser: setCurrentUser, loading } = useAuth();
  const [users, setUsers] = useState<User[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState("");
  const [entryOffset, setEntryOffset] = useState(0);
  const [entries, setEntries] = useState<Entries | null>(null);
  const [error, setError] = useState("");
  const [table, setTable] = useState("tasks");
  const [recordOffset, setRecordOffset] = useState(0);
  const [records, setRecords] = useState<Records | null>(null);
  useEffect(() => {
    if (!selected || !currentUser?.is_admin) return;
    let cancelled = false;
    setRecords(null);
    void read<Records>(`users/${selected}/records?table=${table}&offset=${recordOffset}`).then((data) => {
      if (!cancelled) setRecords(data);
    }).catch((failure: Error) => { if (!cancelled) setError(failure.message); });
    return () => { cancelled = true; };
  }, [selected, table, recordOffset, currentUser]);
  useEffect(() => {
    if (!currentUser?.is_admin) return;
    let cancelled = false;
    void read<{ users: User[]; total: number }>(`users?offset=${offset}`).then((data) => {
      if (!cancelled) { setUsers(data.users); setTotal(data.total); setError(""); }
    }).catch((failure: Error) => { if (!cancelled) { setError(failure.message); setUsers([]); setEntries(null); } });
    return () => { cancelled = true; };
  }, [offset, currentUser]);
  useEffect(() => {
    if (!selected || !currentUser?.is_admin) return;
    let cancelled = false;
    setEntries(null);
    void read<Entries>(`users/${selected}?offset=${entryOffset}`).then((data) => {
      if (!cancelled) { setEntries(data); setError(""); }
    }).catch((failure: Error) => { if (!cancelled) setError(failure.message); });
    return () => { cancelled = true; };
  }, [selected, entryOffset, currentUser]);
  if (loading) return <main className="content-shell"><p role="status">Checking administrator access…</p></main>;
  if (!currentUser) return <main className="content-shell"><h1>Administrator login</h1><p>Log in using aman23077@iiitd.ac.in to view all users and export datasets.</p><AuthForm onAuthenticated={setCurrentUser} /></main>;
  if (!currentUser.is_admin) return <main className="content-shell"><section className="panel">
    <h1>Administrator account required</h1><p>You are signed in as {currentUser.email}. Log in as aman23077@iiitd.ac.in to open administration.</p>
    <button onClick={async () => { try { await logoutUser(); setCurrentUser(null); setUsers([]); setEntries(null); setSelected(""); } catch { setError("Could not sign out. Check the backend connection."); } }}>Switch account</button>
    {error && <p role="alert">{error}</p>}<Link href="/">Back to app</Link>
  </section></main>;
  return <main className="content-shell">
    <section className="panel"><h1>Administration</h1><Link href="/">Back to app / log in</Link>
      <p><Link href="/study/admin">Open pilot results and research export</Link> · <Link href="/study">Participant study page</Link></p>
      <p><Link href="/admin/simulation">Synthetic demonstration results</Link> (separate from human pilot results)</p>
      <p>Signed in as {currentUser.email}</p>
      <div className="session-action-row"><a className="task-link-button" href="/api/v1/admin/export">Download all entries (ZIP)</a><a className="task-link-button" href="/api/v1/admin/export?source=synthetic">Download synthetic entries (ZIP)</a></div>
      <p>Exports contain linked CSV tables and provenance labels. Existing records are marked unverified. Review research consent and identifying text before using or sharing real-user data.</p>
      {error && <p role="alert" className="error-banner">{error}</p>}
      <h2>Users ({error && !users.length ? "unavailable" : total})</h2>
      {users.map((user) => <div className="result-row" key={user.id}>
        <span>{user.display_name} — {user.email}</span>
        <button onClick={() => { setSelected(user.id); setEntryOffset(0); setRecordOffset(0); }}>View entries</button>
      </div>)}
      <div className="session-action-row"><button disabled={offset === 0} onClick={() => setOffset(offset - 50)}>Previous users</button><button disabled={offset + 50 >= total} onClick={() => setOffset(offset + 50)}>Next users</button></div>
    </section>
    {entries && <section className="panel"><h2>{entries.user.display_name}</h2><p>{entries.user.email}</p><a href={`/api/v1/admin/export?user_id=${entries.user.id}`}>Download this user's entries</a>
      {records && <section aria-label="Dataset records"><h3>Browse dataset tables</h3>
        <p>Source: {records.data_source} {records.dataset_id ? `· ${records.dataset_id}` : ""}</p>
        <label>Table <select value={table} onChange={(event) => { setTable(event.target.value); setRecordOffset(0); }}>
          {records.tables.map((name) => <option key={name} value={name}>{name.replace(/_/g, " ")}</option>)}
        </select></label>
        <p>{records.total} records</p>
        <div style={{ overflowX: "auto", maxHeight: "32rem" }}><table><thead><tr>{records.columns.map((column) => <th key={column} style={{ padding: 8, textAlign: "left" }}>{column}</th>)}</tr></thead>
          <tbody>{records.rows.map((row, index) => <tr key={String(row.id ?? index)}>{records.columns.map((column) => <td key={column} style={{ padding: 8, minWidth: 120, maxWidth: 400, overflowWrap: "anywhere" }}>{String(row[column] ?? "—")}</td>)}</tr>)}</tbody></table></div>
        {records.total === 0 && <p>No entries in this table.</p>}
        <div className="session-action-row"><button disabled={recordOffset === 0} onClick={() => setRecordOffset(recordOffset - 50)}>Previous records</button><button disabled={recordOffset + 50 >= records.total} onClick={() => setRecordOffset(recordOffset + 50)}>Next records</button></div>
      </section>}
      <h3>Tasks ({entries.task_count})</h3>
      {entries.tasks.map((task) => <div className="result-card" key={task.id}><strong>{task.title}</strong><p>{task.status} · Planned {task.estimated_minutes ?? "—"} min · Actual {task.actual_minutes ?? "—"} min</p></div>)}
      <h3>Sessions ({entries.session_count})</h3>
      {entries.sessions.map((session) => <div className="result-row" key={session.id}><span>{session.started_at} · {session.status}</span><strong>{session.elapsed_minutes ?? "—"} min</strong></div>)}
      <div className="session-action-row"><button disabled={entryOffset === 0} onClick={() => setEntryOffset(entryOffset - 50)}>Previous entries</button><button disabled={entryOffset + 50 >= Math.max(entries.task_count, entries.session_count)} onClick={() => setEntryOffset(entryOffset + 50)}>Next entries</button></div>
    </section>}
  </main>;
}
