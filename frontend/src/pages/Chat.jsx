import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api } from "../api.js";

export default function Chat() {
  const { clientId } = useParams();
  const [client, setClient] = useState(null);
  const [cfg, setCfg] = useState(null);
  const [model, setModel] = useState("sonnet");
  const [detail, setDetail] = useState(() => {
    try { return localStorage.getItem("qual_detail") || "short"; } catch { return "short"; }
  });
  const [messages, setMessages] = useState([]); // {role, content, trace?}
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const endRef = useRef(null);

  useEffect(() => {
    api.getClient(clientId).then(setClient).catch((e) => setError(e.message));
    api.config().then((c) => {
      setCfg(c);
      setModel(c.default_model);
    });
  }, [clientId]);

  const pickDetail = (d) => {
    setDetail(d);
    try { localStorage.setItem("qual_detail", d); } catch {}
  };

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);

  async function send(e) {
    e.preventDefault();
    const text = input.trim();
    if (!text || busy) return;
    const next = [...messages, { role: "user", content: text }];
    setMessages(next);
    setInput("");
    setBusy(true);
    setError("");
    try {
      const res = await api.chat(
        clientId,
        next.map(({ role, content }) => ({ role, content })),
        model,
        detail
      );
      setMessages([...next, { role: "assistant", content: res.answer, trace: res.trace }]);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="chat">
      <div className="chat-head">
        <div>
          <Link to="/" className="muted">← Clients</Link>
          <h2>{client ? client.name : "…"}</h2>
        </div>
        <div className="controls">
          <label className="switch" title="Off = short answers, on = detailed answers">
            <span className={detail === "short" ? "on" : ""}>Short</span>
            <input
              type="checkbox"
              role="switch"
              checked={detail === "detailed"}
              onChange={(e) => pickDetail(e.target.checked ? "detailed" : "short")}
            />
            <i aria-hidden="true" />
            <span className={detail === "detailed" ? "on" : ""}>Detailed</span>
          </label>
        {cfg && (
          <select value={model} onChange={(e) => setModel(e.target.value)} aria-label="Model">
            {cfg.models.map((m) => (
              <option key={m} value={m}>{m[0].toUpperCase() + m.slice(1)}</option>
            ))}
          </select>
        )}
        </div>
      </div>

      <div className="messages">
        {messages.length === 0 && (
          <p className="muted">Ask a question about {client?.name || "this client"}'s panel data.</p>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`msg ${m.role}`}>
            {m.role === "assistant" ? (
              <>
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown>
                {m.trace?.length > 0 && (
                  <details className="trace">
                    <summary>{m.trace.length} data step{m.trace.length > 1 ? "s" : ""}</summary>
                    {m.trace.map((t, j) => (
                      <pre key={j} className={t.error ? "err" : ""}>
                        {t.tool === "run_sql" ? t.input.sql : t.tool}
                      </pre>
                    ))}
                  </details>
                )}
              </>
            ) : (
              m.content
            )}
          </div>
        ))}
        {busy && <div className="msg assistant muted">Analysing data…</div>}
        {error && <p className="error">{error}</p>}
        <div ref={endRef} />
      </div>

      <form className="composer" onSubmit={send}>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about activities, members, responses…"
          disabled={busy}
        />
        <button disabled={busy || !input.trim()}>Send</button>
      </form>
    </div>
  );
}
