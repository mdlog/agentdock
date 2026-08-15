import { useEffect, useState } from "react";
import { AlertTriangle, ArrowLeft, CheckCircle2, Clock3, ExternalLink, LockKeyhole, ShieldCheck } from "lucide-react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useAccount } from "wagmi";
import { toast } from "sonner";
import { api, messageFromError } from "@/lib/api";
import type { Agent, Readiness } from "@/types";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { WalletButton } from "@/components/WalletButton";
import { AgentAvatar } from "@/components/AgentAvatar";
import { DEFAULT_CHAIN } from "@/lib/erc8004";

export default function AgentPage() {
  const { agentId } = useParams(); const navigate = useNavigate(); const { address, chainId } = useAccount();
  const [agent, setAgent] = useState<Agent | null>(null); const [readiness, setReadiness] = useState<Readiness | null>(null);
  const [loadError, setLoadError] = useState("");
  const [objective, setObjective] = useState("Compare three PancakeSwap pools for sustainable yield, including liquidity, volume, impermanent loss, and key risks.");
  const [constraints, setConstraints] = useState("Prefer evidence from the last 30 days. Do not execute transactions or request approvals."); const [creating, setCreating] = useState(false);
  // Readiness drives an advisory banner only; keep it off the agent's critical path.
  useEffect(() => {
    api.get(`/agents/${agentId}`).then(a => setAgent(a.data)).catch(error => setLoadError(messageFromError(error)));
    api.get("/integrations/readiness").then(r => setReadiness(r.data)).catch(() => setReadiness(null));
  }, [agentId]);
  if (loadError) return <div className="page-wrap empty-state" data-testid="agent-detail-error"><AlertTriangle size={28}/><h1>Agent evidence unavailable</h1><p>{loadError}</p><Button data-testid="agent-error-back-button" asChild><Link to="/">Back to marketplace</Link></Button></div>;
  if (!agent) return <div className="page-wrap" data-testid="agent-detail-loading">Loading agent evidence…</div>;
  const createTask = async () => { setCreating(true); try { const r = await api.post("/tasks", { agent_id: agent.id, objective, constraints, wallet_address: address || null }); toast.success("Task draft created"); navigate(`/tasks/${r.data.id}`); } catch (e) { toast.error(messageFromError(e)); } finally { setCreating(false); } };
  return <div className="page-wrap agent-detail-page">
    <Link to="/" className="back-link" data-testid="back-to-marketplace"><ArrowLeft size={15} /> Back to marketplace</Link>
    <section className="agent-profile-band">
      <AgentAvatar name={`${agent.name}-${agent.id}`} size={68} testId="agent-detail-avatar" className="profile-avatar"/><div className="profile-title"><div className="profile-name"><h1 data-testid="agent-detail-name">{agent.name}</h1><span data-testid="agent-detail-status" className={agent.status === "active" ? "status-live" : "status-offline"}>{agent.status === "active" ? "Live" : "Offline"}</span></div><p data-testid="agent-detail-tagline">{agent.tagline}</p><div className="capability-row">{agent.capabilities.map(x=><span key={x}>{x}</span>)}</div></div>
      <div className="profile-price"><span>Per research run</span><strong data-testid="agent-detail-price">${agent.price_usd.toFixed(2)}</strong></div>
    </section>
    <div className="detail-layout"><div className="evidence-column">
      <section className="plain-section"><div className="section-title"><h2 data-testid="performance-heading">Measured performance</h2><span>Last 30 days</span></div><div className="performance-grid"><div><strong data-testid="detail-proof-score">{agent.metrics.reputation_score}</strong><span>Proof score</span><small>Weighted objective signals</small></div><div><strong data-testid="detail-success-rate">{agent.metrics.success_rate}%</strong><span>Task success</span><small>Completed eligible runs</small></div><div><strong data-testid="detail-uptime">{agent.metrics.uptime_pct}%</strong><span>Uptime</span><small>Endpoint health checks</small></div><div><strong data-testid="detail-latency"><Clock3 size={16}/>{agent.metrics.latency_sec}s</strong><span>Median latency</span><small>Measured processing time</small></div></div></section>
      <section className="plain-section"><div className="section-title"><h2 data-testid="identity-heading">Identity & claims</h2><span className="source-pill"><ShieldCheck size={13}/> Onchain source</span></div><div className="identity-list"><div><span>Network</span><strong data-testid="identity-network">{DEFAULT_CHAIN.label} · Chain {DEFAULT_CHAIN.chainId}</strong></div><div><span>ERC-8004 agent ID</span><strong data-testid="identity-agent-id">#{agent.identity.agent_id}</strong></div><div><span>Metadata</span><strong data-testid="identity-metadata">{agent.identity.metadata_verified ? "Registration checked" : "Claim not verified"}</strong></div><div><span>Endpoint domain</span><strong data-testid="identity-endpoint">Pending live endpoint</strong></div></div><a data-testid="registry-reference-link" href={`${DEFAULT_CHAIN.explorer}/address/${agent.identity.registry}`} target="_blank" rel="noreferrer">Registry reference <ExternalLink size={13}/></a></section>
      <section className="risk-band" data-testid="research-safety-boundary"><LockKeyhole size={20}/><div><strong>Research-only safety boundary</strong><p>This agent cannot hold funds, request token approvals, sign transactions, or execute swaps. You remain the final decision-maker.</p></div></section>
    </div><aside className="task-panel" data-testid="task-composer"><div className="task-panel-heading"><span>Hire agent</span><strong>${agent.price_usd.toFixed(2)}</strong></div><label htmlFor="objective">Research objective</label><Textarea id="objective" data-testid="task-objective-input" value={objective} onChange={e=>setObjective(e.target.value)} rows={6}/><label htmlFor="constraints">Constraints</label><Textarea id="constraints" data-testid="task-constraints-input" value={constraints} onChange={e=>setConstraints(e.target.value)} rows={4}/><div className="transaction-preview"><h3>Transaction preview</h3><div><span>Network</span><strong data-testid="preview-network">{DEFAULT_CHAIN.label}</strong></div><div><span>Maximum cost</span><strong data-testid="preview-cost">${agent.price_usd.toFixed(2)}</strong></div><div><span>Recipient</span><strong data-testid="preview-recipient">Assigned by B402 quote</strong></div><div><span>Permissions</span><strong data-testid="preview-permissions">Payment only · no approval</strong></div></div>
      {!address ? <WalletButton /> : chainId !== DEFAULT_CHAIN.chainId ? <div className="inline-warning" data-testid="wrong-network-warning"><AlertTriangle size={15}/> Switch to {DEFAULT_CHAIN.label}</div> : null}
      <Button data-testid="create-task-button" className="w-full" onClick={createTask} disabled={creating || objective.length < 12 || agent.status !== "active"}>{creating ? "Creating task…" : "Create task & review payment"}</Button>
      {!readiness?.b402_ready && <p className="payment-locked" data-testid="agent-payment-locked"><AlertTriangle size={14}/> Payment will remain locked until Binance B402 is configured.</p>}
    </aside></div>
  </div>;
}