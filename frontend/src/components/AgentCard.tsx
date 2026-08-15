import { ArrowUpRight, Check, Clock3, ShieldCheck } from "lucide-react";
import { Link } from "react-router-dom";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { Agent } from "@/types";

export const AgentCard = ({ agent, selected, toggleCompare }: { agent: Agent; selected: boolean; toggleCompare: (id: string) => void }) => (
  <article className="agent-card" data-testid={`agent-card-${agent.id}`}>
    <div className="agent-card-top">
      <div className={`agent-avatar tone-${agent.identity.agent_id % 5}`} data-testid={`agent-avatar-${agent.id}`}>{agent.name.split(" ").map(x => x[0]).join("")}</div>
      <div className="agent-card-heading"><div className="agent-name-line"><h3 data-testid={`agent-name-${agent.id}`}>{agent.name}</h3>{agent.identity.metadata_verified && <ShieldCheck size={15} aria-label="Metadata verified" />}</div><p data-testid={`agent-category-${agent.id}`}>{agent.category}</p></div>
      <Badge data-testid={`agent-status-${agent.id}`} className={agent.status === "active" ? "status-live" : "status-offline"}>{agent.status === "active" ? "Live" : "Offline"}</Badge>
    </div>
    <p className="agent-tagline" data-testid={`agent-tagline-${agent.id}`}>{agent.tagline}</p>
    <div className="capability-row" data-testid={`agent-capabilities-${agent.id}`}>{agent.capabilities.slice(0, 3).map(item => <span key={item}>{item}</span>)}</div>
    <div className="metric-strip">
      <div><strong data-testid={`agent-score-${agent.id}`}>{agent.metrics.reputation_score}</strong><span>Proof score</span></div>
      <div><strong data-testid={`agent-success-${agent.id}`}>{agent.metrics.success_rate}%</strong><span>Success</span></div>
      <div><strong data-testid={`agent-latency-${agent.id}`}><Clock3 size={13} />{agent.metrics.latency_sec}s</strong><span>Median</span></div>
    </div>
    <div className="agent-card-footer">
      <div><strong data-testid={`agent-price-${agent.id}`}>${agent.price_usd.toFixed(2)}</strong><span>per run</span></div>
      <div className="card-actions"><Button data-testid={`compare-agent-${agent.id}`} variant="outline" size="sm" className={selected ? "selected-compare" : ""} onClick={() => toggleCompare(agent.id)}>{selected && <Check size={14} />}{selected ? "Selected" : "Compare"}</Button><Button data-testid={`view-agent-${agent.id}`} size="icon" asChild><Link to={`/agents/${agent.id}`} aria-label={`View ${agent.name}`}><ArrowUpRight size={16} /></Link></Button></div>
    </div>
  </article>
);