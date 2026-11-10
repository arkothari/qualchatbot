import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";

export default function ClientSelect() {
  const [clients, setClients] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.listClients().then(setClients).catch((e) => setError(e.message));
  }, []);

  return (
    <div className="page">
      <h1>Select a client</h1>
      {error && <p className="error">{error}</p>}
      {clients && clients.length === 0 && (
        <p className="muted">No clients yet. <Link to="/admin">Create one in Admin.</Link></p>
      )}
      <div className="grid">
        {(clients || []).map((c) =>
          c.ready ? (
            <Link key={c.id} to={`/c/${c.id}`} className="card">
              <h3>{c.name}</h3>
              <p className="muted">{c.description || "Open chat"}</p>
            </Link>
          ) : (
            <div key={c.id} className="card disabled">
              <h3>{c.name}</h3>
              <p className="muted">
                Awaiting files ({Object.values(c.files).filter(Boolean).length}/5) —{" "}
                <Link to="/admin">upload in Admin</Link>
              </p>
            </div>
          )
        )}
      </div>
    </div>
  );
}
