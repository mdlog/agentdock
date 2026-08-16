import { useEffect, useState } from "react";
import { AlertTriangle, ArrowLeft, Globe2, Loader2, LockKeyhole, Zap } from "lucide-react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { AGENT_CALL, api, messageFromError } from "@/lib/api";
import type { B402Resource, OnchainAgent } from "@/types";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
import { AgentAvatar } from "@/components/AgentAvatar";
import { UNAVAILABLE, UNCHECKED } from "@/components/OnchainAgentCard";
import { FlowRail, FREE_FLOW, PAID_FLOW } from "@/components/FlowRail";
import { WalletButton } from "@/components/WalletButton";
import { useAccount } from "wagmi";

// A common view over the two agent kinds. A b402 resource is a paid endpoint; an
// onchain 8004scan identity with a live endpoint is activatable for free. Both
// create a task the same way, so this page differs only in copy.
type HireView = {
  paid: boolean;
  title: string;
  description: string;
  tags: string[];
  endpointLabel: string;
  iconName: string;
  iconSrc?: string;
  // Whether this agent can actually be run. An onchain identity is only
  // runnable once a probe has reached its endpoint; asserting "Live endpoint"
  // from the URL alone told the user something nobody had checked.
  runnable: boolean;
  blockedReason?: string;
};

export default function HirePage() {
  const { resourceId = "" } = useParams();
  const navigate = useNavigate();
  const { address } = useAccount();
  const [view, setView] = useState<HireView | null>(null);
  const [loadError, setLoadError] = useState("");
  const [objective, setObjective] = useState("");
  const [creating, setCreating] = useState(false);
  const isOnchain = resourceId.startsWith("bsc-");

  useEffect(() => {
    if (isOnchain) {
      const token = resourceId.split("-")[2];
      api.get(`/onchain/agents/${token}?network=mainnet`)
        .then(r => {
          const a = r.data as OnchainAgent;
          const unusable = a.activatable ? null : (a.endpoint_status && UNAVAILABLE[a.endpoint_status]) || UNCHECKED;
          setView({
            paid: false, title: a.name, description: a.description, tags: a.supported_protocols,
            endpointLabel: unusable ? unusable.label : `Live ${(a.endpoint_kind || "").toUpperCase()} endpoint`,
            iconName: `${a.chain_id}-${a.token_id}-${a.name}`,
            iconSrc: a.has_source_icon ? `${process.env.REACT_APP_BACKEND_URL}/api/onchain/agents/mainnet/${a.token_id}/icon` : undefined,
            runnable: !unusable, blockedReason: unusable?.hint,
          });
        })
        .catch(e => setLoadError(messageFromError(e)));
    } else {
      api.get("/b402/resources")
        .then(r => {
          const b = (r.data.items as B402Resource[]).find(i => i.id === resourceId);
          if (!b) { setLoadError("This service is no longer listed in the b402 catalog."); return; }
          setView({ paid: true, title: b.host, description: b.description, tags: [b.type?.toUpperCase() || "HTTP", `x402 v${b.x402_version}`, "BNB Chain"], endpointLabel: b.resource, iconName: b.resource, runnable: true });
        })
        .catch(e => setLoadError(messageFromError(e)));
    }
  }, [resourceId, isOnchain]);

  const createTask = async () => {
    setCreating(true);
    try {
      const r = await api.post("/tasks", { agent_id: resourceId, objective, constraints: "", wallet_address: address ?? null }, AGENT_CALL);
      navigate(`/tasks/${r.data.id}`);
    } catch (e) {
      toast.error(messageFromError(e));
    } finally {
      setCreating(false);
    }
  };

  if (loadError) return <div className="page-wrap empty-state" data-testid="hire-error"><AlertTriangle size={28} /><h1>Agent unavailable</h1><p>{loadError}</p><Button asChild><Link to="/">Back to marketplace</Link></Button></div>;
  if (!view) return <div className="page-wrap detail-loading" data-testid="hire-loading"><Skeleton className="h-40" /><Skeleton className="h-64" /></div>;

  return <div className="page-wrap hire-page">
    <Link to="/" className="back-link" data-testid="back-to-marketplace"><ArrowLeft size={15} /> Back to marketplace</Link>

    <FlowRail steps={view.paid ? PAID_FLOW : FREE_FLOW} current={0} testId="hire-flow-rail" />

    <section className="agent-profile-band">
      <AgentAvatar name={view.iconName} size={68} testId="hire-avatar" className="profile-avatar" src={view.iconSrc} />
      <div className="profile-title">
        <div className="profile-name"><h1 data-testid="hire-heading">{view.title}</h1><span className={view.runnable ? "status-live" : "status-idle"}>{view.paid ? "x402" : view.runnable ? "activatable" : "not activatable"}</span></div>
        <p data-testid="hire-description">{view.description}</p>
        <div className="capability-row">{view.tags.map(t => <span key={t}>{t}</span>)}</div>
      </div>
      <div className="profile-price"><span>Per call</span><strong data-testid="hire-price">{view.paid ? "Quoted at run" : view.runnable ? "Free" : "—"}</strong></div>
    </section>

    <div className="detail-layout">
      <div className="evidence-column">
        <section className="plain-section">
          <div className="section-title"><h2><Globe2 size={17} /> Endpoint</h2></div>
          <div className="identity-list">
            <div><span>{view.paid ? "Resource" : view.runnable ? "Live endpoint" : "Endpoint"}</span><strong data-testid="hire-endpoint">{view.endpointLabel}</strong></div>
            <div><span>Settlement</span><strong>{view.paid ? "BNB Chain · 56" : "None — free to run"}</strong></div>
            <div><span>Source</span><strong>{view.paid ? "b402 Bazaar · BNB Chain" : "8004scan · BNB Chain"}</strong></div>
          </div>
        </section>

        <section className="risk-band" data-testid="hire-safety-boundary">
          <LockKeyhole size={20} />
          <div>
            <strong>{view.paid ? "You approve the payment, nobody else" : view.runnable ? "You run it, nothing is charged" : "This agent cannot be run"}</strong>
            <p>{view.paid
              ? "AgentDock never holds a key. The merchant quotes its price when the task runs; the exact token, amount and recipient are shown before your wallet is asked to sign anything."
              : view.runnable
                ? "This agent exposes a live endpoint and does not charge. AgentDock calls it with your objective and returns the real result — no signature, no payment."
                : view.blockedReason}</p>
          </div>
        </section>
      </div>

      <aside className="task-panel" data-testid="hire-composer">
        <div className="task-panel-heading"><span><Zap size={14} /> {view.paid ? "Hire agent" : "Activate agent"}</span><strong>{view.paid ? "Pay per call" : "Free"}</strong></div>
        <label htmlFor="objective">What should the agent do?</label>
        <Textarea id="objective" data-testid="hire-objective-input" value={objective} onChange={e => setObjective(e.target.value)} rows={6} placeholder="Describe the request. It is sent to the agent as its query." />
        <div className="transaction-preview">
          <h3>Before you run</h3>
          <div><span>Network</span><strong>BNB Chain · 56</strong></div>
          <div><span>Price</span><strong>{view.paid ? "Quoted by the merchant" : "Free"}</strong></div>
          <div><span>Gas from you</span><strong>None</strong></div>
          <div><span>Permissions</span><strong>{view.paid ? "Single payment · no approval" : "Read-only call · no signature"}</strong></div>
        </div>
        {!address && view.paid && <WalletButton />}
        <Button data-testid="create-hire-task-button" className="w-full" onClick={createTask} disabled={!view.runnable || creating || objective.trim().length < 12}>
          {creating ? <><Loader2 size={15} className="spin" /> Creating task…</> : !view.runnable ? "Cannot be run" : view.paid ? "Create task & get price" : "Create task & run"}
        </Button>
        {!view.runnable && <p className="payment-locked" data-testid="hire-blocked-reason"><AlertTriangle size={14} /> {view.blockedReason}</p>}
        {objective.trim().length > 0 && objective.trim().length < 12 && <p className="payment-locked" data-testid="hire-objective-warning"><AlertTriangle size={14} /> Describe the request in at least 12 characters.</p>}
        {view.runnable && <p className="next-step" data-testid="hire-next-step">Next: {view.paid ? "the merchant quotes its price. Nothing is signed until you approve it." : "AgentDock calls the endpoint and shows you what it returns."}</p>}
      </aside>
    </div>
  </div>;
}
