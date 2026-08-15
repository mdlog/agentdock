import { useEffect, useState } from "react";
import { AlertTriangle, Check, Circle, Clock3, Copy, ExternalLink, FileSearch } from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { api } from "@/lib/api";
import { messageFromError } from "@/lib/api";
import type { AuditEvent, Readiness, Task } from "@/types";
import { Button } from "@/components/ui/button";

const stages = ["created", "paid", "running", "completed"];
export default function TaskPage() {
  const { taskId } = useParams(); const [task, setTask] = useState<Task | null>(null); const [events, setEvents] = useState<AuditEvent[]>([]); const [ready, setReady] = useState<Readiness | null>(null);
  const [loadError, setLoadError] = useState("");
  // Readiness only drives an advisory banner, so it is fetched separately: a slow
  // or failing check must not hide a task that loaded fine. Leaving it null keeps
  // payment displayed as locked, which is the safe default.
  useEffect(() => {
    api.get(`/tasks/${taskId}`).then(t => { setTask(t.data.task); setEvents(t.data.audit_events); }).catch(error => setLoadError(messageFromError(error)));
    api.get("/integrations/readiness").then(r => setReady(r.data)).catch(() => setReady(null));
  }, [taskId]);
  if (loadError) return <div className="page-wrap empty-state" data-testid="task-detail-error"><AlertTriangle size={28}/><h1>Task unavailable</h1><p>{loadError}</p><Button data-testid="task-error-home-button" asChild><Link to="/">Back to marketplace</Link></Button></div>;
  if (!task) return <div className="page-wrap" data-testid="task-loading">Loading task…</div>;
  const current = Math.max(0, stages.indexOf(task.state));
  return <div className="page-wrap task-page"><div className="page-heading"><div><p className="section-kicker">Task execution</p><h1 data-testid="task-heading">{task.agent_name}</h1><p data-testid="task-id">Task {task.id}</p></div><span className={`task-status status-${task.state}`} data-testid="task-current-status">{task.state.replace("_", " ")}</span></div>
    <section className="state-track" data-testid="task-state-track">{stages.map((stage, index)=><div className={index <= current ? "reached" : ""} key={stage}><span>{index < current ? <Check size={15}/> : <Circle size={15}/>}</span><strong data-testid={`task-stage-${stage}`}>{stage}</strong></div>)}</section>
    {!ready?.b402_ready && <section className="blocked-payment" data-testid="task-payment-blocked"><AlertTriangle size={22}/><div><h2>Payment is not active yet</h2><p>Your task draft is safe. No payment request or wallet signature was created because Binance B402 partner access is not configured.</p></div><Button data-testid="payment-disabled-button" disabled>Pay ${task.estimated_price_usd.toFixed(2)}</Button></section>}
    <div className="task-grid"><section className="plain-section"><div className="section-title"><h2>Research brief</h2><FileSearch size={17}/></div><dl className="brief-list"><div><dt>Objective</dt><dd data-testid="task-objective">{task.objective}</dd></div><div><dt>Constraints</dt><dd data-testid="task-constraints">{task.constraints || "None supplied"}</dd></div><div><dt>Maximum cost</dt><dd data-testid="task-max-cost">${task.estimated_price_usd.toFixed(2)}</dd></div><div><dt>Network</dt><dd data-testid="task-network">BSC Testnet · 97</dd></div></dl></section>
      <section className="plain-section"><div className="section-title"><h2>Audit trail</h2><span>{events.length} events</span></div><div className="audit-list" data-testid="task-audit-list">{events.map(event=><div className="audit-event" key={event.id} data-testid={`audit-event-${event.id}`}><span><Clock3 size={14}/></span><div><strong>{event.event}</strong><p>{event.detail}</p><time>{new Date(event.created_at).toLocaleString()}</time></div></div>)}</div></section></div>
    <section className="result-zone" data-testid="task-result-zone"><div><p className="section-kicker">Result artifact</p><h2>{task.result ? "Research complete" : "Waiting for verified payment"}</h2><p>{task.result ? "Review the evidence and execution proof below." : "The agent will only run after B402 verifies and settles the payment."}</p></div>{task.tx_hash ? <a href={`https://testnet.bscscan.com/tx/${task.tx_hash}`} data-testid="task-transaction-link">View transaction <ExternalLink size={14}/></a> : <span data-testid="task-no-transaction"><Copy size={14}/> No transaction recorded</span>}</section>
    <Button data-testid="back-agent-button" variant="outline" asChild><Link to={`/agents/${task.agent_id}`}>Back to agent</Link></Button>
  </div>;
}