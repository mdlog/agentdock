import { useEffect, useState } from "react";
import { AlertTriangle, ArrowLeft, Globe2, LockKeyhole, Zap } from "lucide-react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { api, messageFromError } from "@/lib/api";
import type { B402Resource } from "@/types";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
import { AgentAvatar } from "@/components/AgentAvatar";
import { WalletButton } from "@/components/WalletButton";
import { useAccount } from "wagmi";

export default function HirePage() {
  const { resourceId } = useParams();
  const navigate = useNavigate();
  const { address } = useAccount();
  const [resource, setResource] = useState<B402Resource | null>(null);
  const [loadError, setLoadError] = useState("");
  const [objective, setObjective] = useState("");
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    api.get("/b402/resources")
      .then(r => {
        const found = (r.data.items as B402Resource[]).find(i => i.id === resourceId);
        if (!found) setLoadError("This service is no longer listed in the b402 catalog.");
        setResource(found ?? null);
      })
      .catch(e => setLoadError(messageFromError(e)));
  }, [resourceId]);

  const createTask = async () => {
    setCreating(true);
    try {
      const r = await api.post("/tasks", { agent_id: resourceId, objective, constraints: "", wallet_address: address ?? null });
      navigate(`/tasks/${r.data.id}`);
    } catch (e) {
      toast.error(messageFromError(e));
    } finally {
      setCreating(false);
    }
  };

  if (loadError) return <div className="page-wrap empty-state" data-testid="hire-error"><AlertTriangle size={28} /><h1>Service unavailable</h1><p>{loadError}</p><Button asChild><Link to="/">Back to marketplace</Link></Button></div>;
  if (!resource) return <div className="page-wrap detail-loading" data-testid="hire-loading"><Skeleton className="h-40" /><Skeleton className="h-64" /></div>;

  return <div className="page-wrap hire-page">
    <Link to="/" className="back-link" data-testid="back-to-marketplace"><ArrowLeft size={15} /> Back to marketplace</Link>

    <section className="agent-profile-band">
      <AgentAvatar name={resource.resource} size={68} testId="hire-avatar" className="profile-avatar" />
      <div className="profile-title">
        <div className="profile-name"><h1 data-testid="hire-heading">{resource.host}</h1><span className="status-live">x402</span></div>
        <p data-testid="hire-description">{resource.description}</p>
        <div className="capability-row"><span>{resource.type?.toUpperCase() || "HTTP"}</span><span>x402 v{resource.x402_version}</span><span>BNB Chain</span></div>
      </div>
      <div className="profile-price"><span>Per call</span><strong data-testid="hire-price">Quoted at run</strong></div>
    </section>

    <div className="detail-layout">
      <div className="evidence-column">
        <section className="plain-section">
          <div className="section-title"><h2><Globe2 size={17} /> Endpoint</h2></div>
          <div className="identity-list">
            <div><span>Resource</span><strong data-testid="hire-endpoint">{resource.resource}</strong></div>
            <div><span>Settlement</span><strong>BNB Chain · 56</strong></div>
            <div><span>Recipient</span><strong data-testid="hire-payto">{resource.pay_to[0] ?? "Quoted at run"}</strong></div>
            <div><span>Listed by</span><strong>{resource.source_label}</strong></div>
          </div>
        </section>

        <section className="risk-band" data-testid="hire-safety-boundary">
          <LockKeyhole size={20} />
          <div>
            <strong>You approve the payment, nobody else</strong>
            <p>AgentDock never holds a key. The merchant quotes its price when the task runs; the exact token, amount and recipient are shown before your wallet is asked to sign anything.</p>
          </div>
        </section>
      </div>

      <aside className="task-panel" data-testid="hire-composer">
        <div className="task-panel-heading"><span><Zap size={14} /> Hire agent</span><strong>Pay per call</strong></div>
        <label htmlFor="objective">What should the agent do?</label>
        <Textarea id="objective" data-testid="hire-objective-input" value={objective} onChange={e => setObjective(e.target.value)} rows={6} placeholder="Describe the request. It is sent to the agent as its query." />
        <div className="transaction-preview">
          <h3>Before you sign</h3>
          <div><span>Network</span><strong>BNB Chain · 56</strong></div>
          <div><span>Price</span><strong>Quoted by the merchant</strong></div>
          <div><span>Gas from you</span><strong>None · EIP-3009</strong></div>
          <div><span>Permissions</span><strong>Single payment · no approval</strong></div>
        </div>
        {!address && <WalletButton />}
        <Button data-testid="create-hire-task-button" className="w-full" onClick={createTask} disabled={creating || objective.trim().length < 12}>
          {creating ? "Creating task…" : "Create task & get price"}
        </Button>
        {objective.trim().length > 0 && objective.trim().length < 12 && <p className="payment-locked" data-testid="hire-objective-warning"><AlertTriangle size={14} /> Describe the request in at least 12 characters.</p>}
      </aside>
    </div>
  </div>;
}
