import { useEffect, useMemo, useState } from "react";
import { CheckCircle2, Info, Plus, Trash2 } from "lucide-react";
import { Link } from "react-router-dom";
import { api } from "@/lib/api";
import type { Agent, OnchainAgent } from "@/types";
import { compareKind, useCompare } from "@/hooks/useCompare";
import { Button } from "@/components/ui/button";
import { AgentAvatar } from "@/components/AgentAvatar";
import { compactNumber } from "@/components/OnchainAgentCard";

const slug = (label: string) => label.toLowerCase().replaceAll(" ", "-");

function Row<T extends { id: string }>({ label, hint, agents, render }: { label: string; hint?: string; agents: T[]; render: (a: T) => React.ReactNode }) {
  return <div className="compare-row">
    <div className="compare-label" data-testid={`compare-label-${slug(label)}`}><span>{label}</span>{hint && <small><Info size={12} />{hint}</small>}</div>
    {agents.map(agent => <div className="compare-value" data-testid={`compare-${slug(label)}-${agent.id}`} key={agent.id}>{render(agent)}</div>)}
  </div>;
}

export default function ComparePage() {
  const { selected, toggle, clear } = useCompare();
  const [demo, setDemo] = useState<Agent[]>([]);
  const [onchain, setOnchain] = useState<OnchainAgent[]>([]);
  const kind = selected.length ? compareKind(selected[0]) : null;
  const key = selected.join(",");

  useEffect(() => {
    if (selected.length < 2) { setDemo([]); setOnchain([]); return; }
    if (kind === "demo") {
      api.post("/agents/compare", { agent_ids: selected }).then(r => { setDemo(r.data); setOnchain([]); }).catch(() => setDemo([]));
    } else {
      // The onchain catalog has no compare endpoint; the synchronized sample is
      // one request, so the selection is resolved from it in selection order.
      api.get("/onchain/agents?network=mainnet").then(r => {
        const byId = new Map<string, OnchainAgent>(r.data.items.map((item: OnchainAgent) => [item.id, item]));
        setOnchain(selected.map(id => byId.get(id)).filter((x): x is OnchainAgent => Boolean(x)));
        setDemo([]);
      }).catch(() => setOnchain([]));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, kind]);

  const agents = useMemo(() => (kind === "demo" ? demo : onchain), [kind, demo, onchain]);

  if (selected.length < 2) return <div className="page-wrap empty-state compare-empty" data-testid="comparison-empty"><Plus size={30} /><h1>Select at least two agents</h1><p>Choose up to three agents from the marketplace to inspect their evidence side by side.</p><Button data-testid="browse-agents-button" asChild><Link to="/">Browse agents</Link></Button></div>;

  const heading = <div className="page-heading">
    <div>
      <p className="section-kicker">{kind === "demo" ? "Simulated demo metrics" : "8004scan source observations"}</p>
      <h1 data-testid="comparison-heading">Compare agents</h1>
      <p data-testid="comparison-subheading">{kind === "demo"
        ? "These figures are generated for demonstration and are not measured performance."
        : "Values are preserved as 8004scan supplied them, not measured by AgentDock."}</p>
    </div>
    <Button data-testid="clear-comparison-button" variant="outline" onClick={clear}><Trash2 size={15} /> Clear</Button>
  </div>;

  const head = (items: { id: string; name: string; caption: string }[]) => <div className="compare-row compare-head">
    <div className="compare-label">Agent</div>
    {items.map(item => <div className="compare-value compare-agent-head" key={item.id}>
      <button data-testid={`remove-comparison-${item.id}`} onClick={() => toggle(item.id)} aria-label={`Remove ${item.name}`}>×</button>
      <AgentAvatar name={`${item.name}-${item.id}`} testId={`comparison-avatar-${item.id}`} />
      <strong data-testid={`comparison-name-${item.id}`}>{item.name}</strong>
      <span>{item.caption}</span>
    </div>)}
  </div>;

  if (kind === "onchain") return <div className="page-wrap">
    {heading}
    <div className="compare-table" data-testid="comparison-table" style={{ "--columns": onchain.length } as React.CSSProperties}>
      {head(onchain.map(a => ({ id: a.id, name: a.name, caption: `ERC-8004 #${a.token_id}` })))}
      <Row label="Price" hint="8004scan publishes no pricing" agents={onchain} render={() => <strong>Not published onchain</strong>} />
      <Row label="8004scan score" hint="Source score, not measured by AgentDock" agents={onchain} render={a => <strong className="large-score">{a.total_score ?? "—"}</strong>} />
      <Row label="Network rank" agents={onchain} render={a => a.rank ? `#${a.rank}` : "—"} />
      <Row label="Health score" agents={onchain} render={a => a.health_score ?? "—"} />
      <Row label="Feedbacks" hint="Onchain feedback entries" agents={onchain} render={a => compactNumber(a.total_feedbacks)} />
      <Row label="Average feedback" agents={onchain} render={a => a.average_score ?? "—"} />
      <Row label="Verified" agents={onchain} render={a => a.is_verified ? "Yes" : "No"} />
      <Row label="x402 claim" agents={onchain} render={a => a.x402_supported ? "Declared" : "Not declared"} />
      <Row label="Protocols" agents={onchain} render={a => <div className="compare-caps">{a.supported_protocols.length ? a.supported_protocols.map(x => <span key={x}><CheckCircle2 size={13} />{x}</span>) : <span>None declared</span>}</div>} />
      <div className="compare-row compare-cta"><div className="compare-label" />{onchain.map(a => <div className="compare-value" key={a.id}><Button data-testid={`details-from-compare-${a.id}`} asChild><Link to={`/onchain/mainnet/${a.token_id}`}>View details</Link></Button></div>)}</div>
    </div>
  </div>;

  return <div className="page-wrap">
    {heading}
    <div className="compare-table" data-testid="comparison-table" style={{ "--columns": agents.length } as React.CSSProperties}>
      {head(demo.map(a => ({ id: a.id, name: a.name, caption: a.category })))}
      <Row label="Price" agents={demo} render={a => <strong>${a.price_usd.toFixed(2)} / run</strong>} />
      <Row label="Proof score" hint="Weighted simulated metrics" agents={demo} render={a => <strong className="large-score">{a.metrics.reputation_score}</strong>} />
      <Row label="Task success" hint="Completed ÷ eligible tasks" agents={demo} render={a => `${a.metrics.success_rate}%`} />
      <Row label="Uptime" hint="Successful health checks, 30d" agents={demo} render={a => `${a.metrics.uptime_pct}%`} />
      <Row label="Median latency" hint="Simulated task runtime" agents={demo} render={a => `${a.metrics.latency_sec}s`} />
      <Row label="Task volume" agents={demo} render={a => a.metrics.task_volume.toLocaleString()} />
      <Row label="Capabilities" agents={demo} render={a => <div className="compare-caps">{a.capabilities.map(x => <span key={x}><CheckCircle2 size={13} />{x}</span>)}</div>} />
      <div className="compare-row compare-cta"><div className="compare-label" />{demo.map(a => <div className="compare-value" key={a.id}><Button data-testid={`hire-from-compare-${a.id}`} asChild={a.status === "active"} disabled={a.status !== "active"}>{a.status === "active" ? <Link to={`/agents/${a.id}`}>View and hire</Link> : <span>Offline</span>}</Button></div>)}</div>
    </div>
  </div>;
}
