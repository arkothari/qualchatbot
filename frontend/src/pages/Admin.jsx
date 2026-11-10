import { useEffect, useState } from "react";
import { api, getAdminToken, setAdminToken } from "../api.js";

const fmtSize = (n) => (n > 1e6 ? `${(n / 1e6).toFixed(1)} MB` : `${Math.ceil(n / 1e3)} KB`);

export default function Admin() {
  const [cfg, setCfg] = useState(null);
  const [authed, setAuthed] = useState(false);
  const [token, setToken] = useState(getAdminToken());
  const [clients, setClients] = useState([]);
  const [selId, setSelId] = useState("");
  const [newName, setNewName] = useState("");
  const [error, setError] = useState("");
  const [busyKind, setBusyKind] = useState("");

  const [versions, setVersions] = useState([]);
  const sel = clients.find((c) => c.id === selId);

  const refresh = () => api.listClients().then(setClients).catch((e) => setError(e.message));

  useEffect(() => {
    api.config().then(setCfg);
  }, []);

  useEffect(() => {
    if (!cfg) return;
    if (!cfg.admin_protected) return setAuthed(true);
    if (getAdminToken()) api.adminCheck().then(() => setAuthed(true)).catch(() => {});
  }, [cfg]);

  useEffect(() => {
    if (authed && selId) api.versions(selId).then(setVersions).catch(() => setVersions([]));
    else setVersions([]);
  }, [authed, selId, sel?.loading]);

  useEffect(() => {
    if (authed) refresh();
  }, [authed]);

  async function login(e) {
    e.preventDefault();
    setAdminToken(token);
    try {
      await api.adminCheck();
      setAuthed(true);
      setError("");
    } catch {
      setError("Invalid admin token");
    }
  }

  const guard = (fn) => async (...a) => {
    setError("");
    try {
      await fn(...a);
    } catch (e) {
      setError(e.message);
    }
  };

  const create = guard(async (e) => {
    e.preventDefault();
    if (!newName.trim()) return;
    const c = await api.createClient(newName, "");
    setNewName("");
    await refresh();
    setSelId(c.id);
  });

  const upload = guard(async (kind, file) => {
    if (!file) return;
    setBusyKind(kind);
    try {
      await api.uploadFile(sel.id, kind, file);
      await refresh();
    } finally {
      setBusyKind("");
    }
  });

  const remove = guard(async (kind) => {
    await api.deleteFile(sel.id, kind);
    await refresh();
  });

  const saveMeta = guard(async (patch) => {
    await api.patchClient(sel.id, patch);
    await refresh();
  });

  const startLoad = guard(async () => {
    await api.startLoad(sel.id);
    await refresh();
  });

  const finishLoad = guard(async () => {
    await api.finishLoad(sel.id);
    await refresh();
  });

  const restore = guard(async (v) => {
    if (!confirm(`Restore the version from ${new Date(v.created_at).toLocaleString()}? The current files are archived first.`)) return;
    await api.restoreVersion(sel.id, v.name);
    await refresh();
    setVersions(await api.versions(sel.id));
  });

  const download = guard(async (v) => {
    const url = URL.createObjectURL(await api.downloadVersion(sel.id, v.name));
    const a = document.createElement("a");
    a.href = url;
    a.download = `${sel.name}-${v.name}`;
    a.click();
    URL.revokeObjectURL(url);
  });

  const hasFiles = sel && Object.values(sel.files).some(Boolean);

  const deleteClient = guard(async () => {
    if (!confirm(`Delete client "${sel.name}" and all its files? This cannot be undone.`)) return;
    await api.deleteClient(sel.id);
    setSelId("");
    await refresh();
  });

  if (!cfg) return null;
  if (!authed)
    return (
      <div className="page narrow">
        <h1>Admin</h1>
        <form onSubmit={login} className="row">
          <input type="password" placeholder="Admin token" value={token} onChange={(e) => setToken(e.target.value)} />
          <button>Sign in</button>
        </form>
        {error && <p className="error">{error}</p>}
      </div>
    );

  return (
    <div className="page">
      <h1>Admin</h1>
      {error && <p className="error">{error}</p>}

      <div className="row">
        <select value={selId} onChange={(e) => setSelId(e.target.value)}>
          <option value="">Select a client…</option>
          {clients.map((c) => (
            <option key={c.id} value={c.id}>{c.name}</option>
          ))}
        </select>
        <span className="muted">or</span>
        <form onSubmit={create} className="row">
          <input placeholder="New client name" value={newName} onChange={(e) => setNewName(e.target.value)} />
          <button>Create client</button>
        </form>
      </div>

      {sel && (
        <section key={sel.id}>
          <h2>{sel.name}</h2>
          <label>Description (given to the model as context)</label>
          <textarea
            defaultValue={sel.description}
            rows={2}
            onBlur={(e) => e.target.value !== sel.description && saveMeta({ description: e.target.value })}
          />

          <h3>Data load</h3>
          {sel.loading ? (
            <div className="banner">
              <strong>New data load in progress</strong> — {sel.replaced.length}/5 files replaced. Previous version
              saved{sel.load_snapshot ? ` as ${sel.load_snapshot}` : ""}. The load ends automatically once all 5
              are replaced.
              <button className="link" onClick={finishLoad}>Finish load</button>
            </div>
          ) : hasFiles ? (
            <div className="banner">
              To replace existing files, start a new data load. This saves the current files as a version first
              (last 5 versions kept).
              <button onClick={startLoad}>Start new data load</button>
            </div>
          ) : (
            <p className="muted">No files yet — the first upload needs no data load.</p>
          )}
          {versions.length > 0 && (
            <details className="versions">
              <summary>Version history ({versions.length})</summary>
              <ul>
                {versions.map((v) => (
                  <li key={v.name}>
                    {new Date(v.created_at).toLocaleString()} · {fmtSize(v.size)}
                    <button className="link" onClick={() => download(v)}>Download</button>
                    <button className="link" onClick={() => restore(v)}>Restore</button>
                  </li>
                ))}
              </ul>
            </details>
          )}

          <h3>Files</h3>
          <table className="files">
            <thead>
              <tr><th>File</th><th>Status</th><th>Describe the contents (helps the model)</th><th></th></tr>
            </thead>
            <tbody>
              {Object.entries(cfg.file_kinds).map(([kind, label]) => {
                const f = sel.files[kind];
                const locked = !!f && !sel.loading;
                return (
                  <tr key={kind}>
                    <td><strong>{label}</strong><br /><code>{kind}</code></td>
                    <td>
                      {busyKind === kind ? "Uploading…" : f ? `${f.filename} · ${fmtSize(f.size)}` : <span className="muted">missing</span>}
                    </td>
                    <td>
                      <textarea
                        rows={2}
                        defaultValue={sel.notes[kind] || ""}
                        placeholder="Columns, ID fields, codes…"
                        onBlur={(e) =>
                          e.target.value !== (sel.notes[kind] || "") &&
                          saveMeta({ notes: { ...sel.notes, [kind]: e.target.value } })
                        }
                      />
                    </td>
                    <td className="actions">
                      <label className={`btn${locked ? " disabled" : ""}`} title={locked ? "Start a new data load first" : ""}>
                        {f ? "Replace" : "Upload"}
                        <input type="file" hidden disabled={locked} accept=".csv,.xlsx,.xls,.parquet"
                          onChange={(e) => { upload(kind, e.target.files[0]); e.target.value = ""; }} />
                      </label>
                      {f && <button className="link" disabled={locked} onClick={() => remove(kind)}>Remove</button>}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p className={sel.ready ? "ok" : "muted"}>
            {sel.ready ? "✓ All 5 files uploaded — client is available in the chat." : "Upload all 5 files to enable chat for this client."}
          </p>
          <button className="danger" onClick={deleteClient}>Delete client</button>
        </section>
      )}
    </div>
  );
}
