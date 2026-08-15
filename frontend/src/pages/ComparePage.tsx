import { useEffect, useState } from "react";
import { CheckCircle2, Info, Plus, Trash2 } from "lucide-react";
import { Link } from "react-router-dom";
import { api } from "@/lib/api";
import type { Agent } from "@/types";
import { useCompare } from "@/hooks/useCompare";
import { Button } from "@/components/ui/button";
import { AgentAvatar } from "@/components/AgentAvatar";

const Row = ({ label, hint, agents, render }: { label: string; hint?: string; agents: Agent[]; render: (a: Agent) => React.ReactNode }) => <div className="compare-row"><div className="compare-label" data-testid={`compare-label-${label.toLowerCase().replaceAll(" ", "-")}`}><span>{label}</span>{hint && <small><Info size={12} />{hint}</small>}</div>{agents.map(agent => <div className="compare-value" data-testid={`compare-${label.toLowerCase().replaceAll(" ", "-")}-${agent.id}`} key={agent.id}>{render(agent)}</div>)}</div>;

export default function ComparePage() {
  const { selected, toggle, clear } = useCompare();
  const [agents, setAgents] = useState<Agent[]>([]);
  useEffect(() => { if (selected.length >= 2) api.post("/agents/compare", { agent_ids: selected }).then(r => setAgents(r.data)); else setAgents([]); }, [selected.join(",")]);
  if (selected.length < 2) return <div className="page-wrap empty-state compare-empty" data-testid="comparison-empty"><Plus size={30} /><h1>Select at least two agents</h1><p>Choose up to three agents from the marketplace to inspect their evidence side by side.</p><Button data-testid="browse-agents-button" asChild><Link to="/">Browse agents</Link></Button></div>;
  return <div className="page-wrap">
    <div className="page-heading"><div><p className="section-kicker">Side-by-side proof</p><h1 data-testid="comparison-heading">Compare agents</h1><p data-testid="comparison-subheading">Scores combine task success, uptime, recency, feedback, volume, and latency.</p></div><Button data-testid="clear-comparison-button" variant="outline" onClick={clear}><Trash2 size={15} /> Clear</Button></div>
    <div className="compare-table" data-testid="comparison-table" style={{"--columns": agents.length} as React.CSSProperties}>
      <div className="compare-row compare-head"><div className="compare-label">Agent</div>{agents.map(agent => <div className="compare-value compare-agent-head" key={agent.id}><button data-testid={`remove-comparison-${agent.id}`} onClick={() => toggle(agent.id)} aria-label={`Remove ${agent.name}`}>×</button><AgentAvatar name={`${agent.name}-${agent.id}`} testId={`comparison-avatar-${agent.id}`} /><strong data-testid={`comparison-name-${agent.id}`}>{agent.name}</strong><span>{agent.category}</span></div>)}</div>
      <Row label="Price" agents={agents} render={a => <strong>${a.price_usd.toFixed(2)} / run</strong>} />
      <Row label="Proof score" hint="Weighted objective metrics" agents={agents} render={a => <strong className="large-score">{a.metrics.reputation_score}</strong>} />
      <Row label="Task success" hint="Completed ÷ eligible tasks" agents={agents} render={a => `${a.metrics.success_rate}%`} />
      <Row label="Uptime" hint="Successful health checks, 30d" agents={agents} render={a => `${a.metrics.uptime_pct}%`} />
      <Row label="Median latency" hint="Measured task runtime" agents={agents} render={a => `${a.metrics.latency_sec}s`} />
      <Row label="Task volume" hint="Audited eligible runs" agents={agents} render={a => a.metrics.task_volume.toLocaleString()} />
      <Row label="Capabilities" agents={agents} render={a => <div className="compare-caps">{a.capabilities.map(x => <span key={x}><CheckCircle2 size={13} />{x}</span>)}</div>} />
      <div className="compare-row compare-cta"><div className="compare-label" />{agents.map(a => <div className="compare-value" key={a.id}><Button data-testid={`hire-from-compare-${a.id}`} asChild disabled={a.status !== "active"}><Link to={`/agents/${a.id}`}>View and hire</Link></Button></div>)}</div>
    </div>
  </div>;
}