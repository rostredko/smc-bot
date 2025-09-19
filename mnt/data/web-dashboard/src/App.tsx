
import { useEffect, useMemo, useRef, useState } from "react";

type StdoutEvent = { type: "stdout"; script: string; line: string; ts: number };
type ExitEvent = { type: "exit"; script: string; returncode: number; ts: number };
type AnyEvent = StdoutEvent | ExitEvent | Record<string, any>;

const API = "http://localhost:8000";
const WS = "ws://localhost:8000/ws";

export default function App() {
  const [events, setEvents] = useState<AnyEvent[]>([]);
  const [scripts, setScripts] = useState<string[]>([]);
  const [selected, setSelected] = useState<string>("");
  const [running, setRunning] = useState<{ running: boolean; script: string | null }>({ running: false, script: null });
  const wsRef = useRef<WebSocket | null>(null);

  // load available scripts from backend
  useEffect(() => {
    fetch(`${API}/scripts`).then(r => r.json()).then(data => {
      setScripts(data.scripts ?? []);
      if ((data.scripts ?? []).length > 0) setSelected(data.scripts[0]);
    });
    fetch(`${API}/status`).then(r => r.json()).then(data => setRunning(data));
  }, []);

  // connect to websocket
  useEffect(() => {
    const ws = new WebSocket(WS);
    wsRef.current = ws;
    ws.onmessage = (e) => {
      try {
        const ev = JSON.parse(e.data) as AnyEvent;
        setEvents(prev => [ev, ...prev].slice(0, 2000));
        // update status on exit
        if ((ev as ExitEvent).type === "exit") {
          setRunning({ running: false, script: null });
        }
      } catch { /* ignore */ }
    };
    ws.onclose = () => console.log("WS closed");
    return () => ws.close();
  }, []);

  const onStart = async () => {
    if (!selected) return;
    const res = await fetch(`${API}/start`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ script: selected })
    });
    if (res.ok) {
      setRunning({ running: true, script: selected });
    } else {
      const msg = await res.text();
      alert(`Failed to start: ${msg}`);
    }
  };

  const onStop = async () => {
    await fetch(`${API}/stop`, { method: "POST" });
    setRunning({ running: false, script: null });
  };

  const lines = useMemo(() => events.filter(e => e.type === "stdout") as StdoutEvent[], [events]);

  return (
    <div style={{ fontFamily: "Inter, system-ui", padding: 16, display: "grid", gap: 16 }}>
      <header style={{ display: "flex", gap: 12, alignItems: "center" }}>
        <h1 style={{ margin: 0 }}>Trading Bot Dashboard</h1>
      </header>

      <section style={{ display: "flex", gap: 12, alignItems: "center" }}>
        <label>Script:&nbsp;</label>
        <select value={selected} onChange={e => setSelected(e.target.value)}>
          {scripts.map(s => <option key={s} value={s}>{s}</option>)}
        </select>
        <button onClick={onStart} disabled={!selected || running.running} style={{ padding: "8px 12px", borderRadius: 8, cursor: "pointer" }}>
          Start
        </button>
        <button onClick={onStop} disabled={!running.running} style={{ padding: "8px 12px", borderRadius: 8, cursor: "pointer" }}>
          Stop
        </button>
        <span style={{ opacity: 0.8 }}>
          Status: {running.running ? `running (${running.script})` : "idle"}
        </span>
      </section>

      <section>
        <h2>Live Output</h2>
        <div style={{ border: "1px solid #eee", borderRadius: 8, padding: 12, height: 400, overflow: "auto", background: "#0b0b0b", color: "#eee" }}>
          {[...lines].reverse().map((l, idx) => (
            <div key={idx} style={{ fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace", whiteSpace: "pre-wrap" }}>
              {l.line}
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
