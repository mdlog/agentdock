import { useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, Info, Plus, Trash2 } from "lucide-react";
import { Link } from "react-router-dom";
import { api, messageFromError } from "@/lib/api";
import type { OnchainAgent } from "@/types";
import { useCompare } from "@/hooks/useCompare";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { AgentAvatar } from "@/components/AgentAvatar";
import { compactNumber } from "@/components/OnchainAgentCard";

const slug = (label: string) => label.toLowerCase().replaceAll(" ", "-");

const Row = ({ label, hint, agents, render }: { label: string; hint?: string; agents: OnchainAgent[]; render: (a: OnchainAgent) => React.ReactNode }) =>
  <div className="compare-row">
    <div className="compare-label" data-testid={`compare-label-${slug(label)}`}><span>{label}</span>{hint && <small><Info size={12} />{hint}</small>}</div>
    {agents.map(agent => <div className="compare-value" data-testid={`compare-${slug(label)}-${agent.id}`} key={agent.id}>{render(agent)}</div>)}
  </div>;

export default function ComparePage() {
  const { selected, toggle, clear } = useCompare();
  const [agents, setAgents] = useState<OnchainAgent[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState("");
  const key = selected.join(",");

  useEffect(() => {
    if (selected.length < 2) { setAgents([]); setLoadError(""); return; }
    setLoading(true);
    // Each selection is fetched by id. Resolving them out of one default page
    // meant anything outside the first 60 of 256,000 silently vanished, leaving
    // a table of labels with no columns and no explanation.
    Promise.all(selected.map(id =>
      api.get(`/onchain/agents/${id.split("-")[2]}?network=mainnet`)
        .then(r => r.data as OnchainAgent)
        .catch(() => null)
    )).then(resolved => {
      const found = resolved.filter((x): x is OnchainAgent => Boolean(x));
      setAgents(found);
      // Say what could not be loaded instead of quietly dropping it.
      const missing = resolved.length - found.length;
      setLoadError(missing ? `${missing} of ${resolved.length} selected agents could not be loaded.` : "");
    }).catch(e => { setAgents([]); setLoadError(messageFromError(e)); })
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  if (selected.length < 2) return <div className="page-wrap empty-state compare-empty" data-testid="comparison-empty"><Plus size={30} /><h1>Select at least two agents</h1><p>Choose up to three agents from the marketplace to inspect their evidence side by side.</p><Button data-testid="browse-agents-button" asChild><Link to="/">Browse agents</Link></Button></div>;

  return <div className="page-wrap">
    <div className="page-heading">
      <div>
        <p className="section-kicker">8004scan source observations</p>
        <h1 data-testid="comparison-heading">Compare agents</h1>
        <p data-testid="comparison-subheading">Values are preserved as 8004scan supplied them, not measured by AgentDock.</p>
      </div>
      <Button data-testid="clear-comparison-button" variant="outline" onClick={clear}><Trash2 size={15} /> Clear</Button>
    </div>

    {loadError && <div className="integration-notice" data-testid="comparison-load-error"><AlertTriangle size={16} /><strong>{loadError}</strong></div>}
    {loading
      ? <div className="compare-loading" data-testid="comparison-loading"><Skeleton className="h-64" /></div>
      : agents.length < 2
        ? <div className="empty-state" data-testid="comparison-unavailable"><AlertTriangle size={28} /><h3>Not enough agents to compare</h3><p>The selected agents could not be loaded from the registry. Clear the selection and pick again.</p><Button variant="outline" onClick={clear}>Clear selection</Button></div>
        : <div className="compare-table" data-testid="comparison-table" style={{ "--columns": agents.length } as React.CSSProperties}>
      <div className="compare-row compare-head">
        <div className="compare-label">Agent</div>
        {agents.map(agent => <div className="compare-value compare-agent-head" key={agent.id}>
          <button data-testid={`remove-comparison-${agent.id}`} onClick={() => toggle(agent.id)} aria-label={`Remove ${agent.name}`}>×</button>
          <AgentAvatar name={`${agent.chain_id}-${agent.token_id}-${agent.name}`} testId={`comparison-avatar-${agent.id}`} src={agent.has_source_icon ? `${process.env.REACT_APP_BACKEND_URL}/api/onchain/agents/mainnet/${agent.token_id}/icon` : undefined} />
          <strong data-testid={`comparison-name-${agent.id}`}>{agent.name}</strong>
          <span>ERC-8004 #{agent.token_id}</span>
        </div>)}
      </div>
      <Row label="Price" hint="8004scan publishes no pricing" agents={agents} render={() => <strong>Not published onchain</strong>} />
      <Row label="8004scan score" hint="Source score, not measured by AgentDock" agents={agents} render={a => <strong className="large-score">{a.total_score ?? "—"}</strong>} />
      <Row label="Network rank" agents={agents} render={a => a.rank ? `#${a.rank}` : "—"} />
      <Row label="Health score" agents={agents} render={a => a.health_score ?? "—"} />
      <Row label="Feedbacks" hint="Onchain feedback entries" agents={agents} render={a => compactNumber(a.total_feedbacks)} />
      <Row label="Average feedback" agents={agents} render={a => a.average_score ?? "—"} />
      <Row label="Verified" agents={agents} render={a => a.is_verified ? "Yes" : "No"} />
      <Row label="x402 claim" agents={agents} render={a => a.x402_supported ? "Declared" : "Not declared"} />
      <Row label="Protocols" agents={agents} render={a => <div className="compare-caps">{a.supported_protocols.length ? a.supported_protocols.map(x => <span key={x}><CheckCircle2 size={13} />{x}</span>) : <span>None declared</span>}</div>} />
      <div className="compare-row compare-cta"><div className="compare-label" />{agents.map(a => <div className="compare-value" key={a.id}><Button data-testid={`details-from-compare-${a.id}`} asChild><Link to={`/onchain/mainnet/${a.token_id}`}>View details</Link></Button></div>)}</div>
        </div>}
  </div>;
}
