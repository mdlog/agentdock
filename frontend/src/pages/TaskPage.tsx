import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, Check, Circle, Clock3, ExternalLink, FileSearch, PenLine, Play } from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { useAccount, useChainId, useSignTypedData, useSwitchChain } from "wagmi";
import { toast } from "sonner";
import { api, messageFromError } from "@/lib/api";
import type { AuditEvent, Task, TypedData } from "@/types";
import { Button } from "@/components/ui/button";
import { WalletButton } from "@/components/WalletButton";
import { DEFAULT_CHAIN } from "@/lib/erc8004";

const stages = ["created", "payment_pending", "paid", "completed"];
const stageLabel: Record<string, string> = { created: "created", payment_pending: "priced", paid: "paid", completed: "completed" };

export default function TaskPage() {
  const { taskId } = useParams();
  const { address } = useAccount();
  const chainId = useChainId();
  const { switchChain } = useSwitchChain();
  const { signTypedDataAsync } = useSignTypedData();
  const [task, setTask] = useState<Task | null>(null);
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [loadError, setLoadError] = useState("");
  const [busy, setBusy] = useState("");

  const load = useCallback(async () => {
    const t = await api.get(`/tasks/${taskId}`);
    setTask(t.data.task);
    setEvents(t.data.audit_events);
  }, [taskId]);

  useEffect(() => { load().catch(error => setLoadError(messageFromError(error))); }, [load]);

  const runTask = async () => {
    setBusy("run");
    try {
      const r = await api.post(`/tasks/${taskId}/run`);
      toast.success(r.data.paid ? "Merchant quoted a price" : "Agent answered without charging");
      await load();
    } catch (e) { toast.error(messageFromError(e)); } finally { setBusy(""); }
  };

  // Authorize and sign are deliberately one action: the merchant's window is
  // short, so the typed data is minted immediately before the wallet prompt.
  const payTask = async () => {
    if (!address) return;
    setBusy("pay");
    try {
      const auth = await api.post(`/tasks/${taskId}/authorize`, { payer: address });
      const td = auth.data.typed_data as TypedData;
      const signature = await signTypedDataAsync({
        account: address,
        domain: td.domain,
        types: td.types as any,
        primaryType: td.primaryType as any,
        message: {
          from: td.message.from as `0x${string}`,
          to: td.message.to as `0x${string}`,
          value: BigInt(td.message.value),
          validAfter: BigInt(td.message.validAfter),
          validBefore: BigInt(td.message.validBefore),
          nonce: td.message.nonce as `0x${string}`,
        } as any,
      });
      await api.post(`/tasks/${taskId}/pay`, { signature });
      toast.success("Payment settled and agent executed");
      await load();
    } catch (e: any) {
      toast.error(e?.name === "UserRejectedRequestError" ? "You rejected the signature. Nothing was paid." : messageFromError(e));
      await load().catch(() => {});
    } finally { setBusy(""); }
  };

  if (loadError) return <div className="page-wrap empty-state" data-testid="task-detail-error"><AlertTriangle size={28} /><h1>Task unavailable</h1><p>{loadError}</p><Button data-testid="task-error-home-button" asChild><Link to="/">Back to marketplace</Link></Button></div>;
  if (!task) return <div className="page-wrap" data-testid="task-loading">Loading task…</div>;

  const current = Math.max(0, stages.indexOf(task.state));
  const terms = task.payment_terms;
  const wrongChain = !!address && chainId !== DEFAULT_CHAIN.chainId;

  return <div className="page-wrap task-page">
    <div className="page-heading"><div><p className="section-kicker">Task execution</p><h1 data-testid="task-heading">{task.agent_name}</h1><p data-testid="task-id">Task {task.id}</p></div><span className={`task-status status-${task.state}`} data-testid="task-current-status">{task.state.replace("_", " ")}</span></div>

    <section className="state-track" data-testid="task-state-track">{stages.map((stage, index) => <div className={index <= current ? "reached" : ""} key={stage}><span>{index < current ? <Check size={15} /> : <Circle size={15} />}</span><strong data-testid={`task-stage-${stage}`}>{stageLabel[stage]}</strong></div>)}</section>

    {task.state === "created" && <section className="blocked-payment" data-testid="task-run-panel">
      <Play size={22} />
      {task.endpoint_kind
        ? <><div><h2>Run this agent</h2><p>AgentDock calls the agent's live {task.endpoint_kind.toUpperCase()} endpoint with your objective and returns the real result. This agent does not charge — no signature, no payment.</p></div>
            <Button data-testid="run-task-button" onClick={runTask} disabled={busy === "run"}>{busy === "run" ? "Running…" : "Run agent"}</Button></>
        : <><div><h2>Ask the agent for its price</h2><p>AgentDock calls the endpoint once without paying. The merchant answers with the exact token, amount and recipient — nothing is signed at this step.</p></div>
            <Button data-testid="run-task-button" onClick={runTask} disabled={busy === "run"}>{busy === "run" ? "Asking…" : "Get price"}</Button></>}
    </section>}

    {task.state === "payment_pending" && terms && <section className="payment-panel" data-testid="task-payment-panel">
      <div className="payment-terms">
        <h2><PenLine size={17} /> Confirm before signing</h2>
        <div className="detail-kv">
          <div><span>Amount</span><strong data-testid="pay-amount">{terms.amount_tokens} {terms.asset_name}</strong></div>
          <div><span>Network</span><strong data-testid="pay-network">BNB Chain · {terms.chain_id}</strong></div>
          <div><span>Token</span><strong data-testid="pay-asset">{terms.asset}</strong></div>
          <div><span>Recipient</span><strong data-testid="pay-recipient">{terms.pay_to}</strong></div>
          <div><span>Method</span><strong>{terms.transfer_method} · no gas from you</strong></div>
          <div><span>Valid for</span><strong>{terms.max_timeout_seconds}s after signing</strong></div>
        </div>
      </div>
      <div className="payment-action">
        {!address ? <WalletButton />
          : wrongChain ? <Button data-testid="switch-pay-chain-button" onClick={() => switchChain({ chainId: DEFAULT_CHAIN.chainId })}>Switch to {DEFAULT_CHAIN.label}</Button>
          : <Button data-testid="sign-and-pay-button" onClick={payTask} disabled={busy === "pay"}>{busy === "pay" ? "Waiting for your wallet…" : `Sign & pay ${terms.amount_tokens} ${terms.asset_name}`}</Button>}
        <p className="payment-locked"><AlertTriangle size={14} /> Your wallet signs an authorization. AgentDock never holds your key.</p>
      </div>
    </section>}

    <div className="task-grid">
      <section className="plain-section"><div className="section-title"><h2>Request</h2><FileSearch size={17} /></div><dl className="brief-list">
        <div><dt>Objective</dt><dd data-testid="task-objective">{task.objective}</dd></div>
        <div><dt>Price</dt><dd data-testid="task-max-cost">{task.estimated_price_usd === null ? "Not quoted yet" : `${task.estimated_price_usd} ${terms?.asset_name ?? ""}`.trim()}</dd></div>
        <div><dt>Network</dt><dd data-testid="task-network">{DEFAULT_CHAIN.label} · {DEFAULT_CHAIN.chainId}</dd></div>
      </dl></section>

      <section className="plain-section"><div className="section-title"><h2>Audit trail</h2><span>{events.length} events</span></div><div className="audit-list" data-testid="task-audit-list">{events.map(event => <div className="audit-event" key={event.id} data-testid={`audit-event-${event.id}`}><span><Clock3 size={14} /></span><div><strong>{event.event}</strong><p>{event.detail}</p><time>{new Date(event.created_at).toLocaleString()}</time></div></div>)}</div></section>
    </div>

    <section className="result-zone" data-testid="task-result-zone">
      <div>
        <p className="section-kicker">Result</p>
        <h2>{task.result_preview ? "Agent responded" : "No result yet"}</h2>
        {task.result_preview
          ? <pre className="result-body" data-testid="task-result-body">{task.result_preview}</pre>
          : <p>The agent runs once its payment is settled.</p>}
      </div>
      {task.tx_hash
        ? <a href={`${DEFAULT_CHAIN.explorer}/tx/${task.tx_hash}`} target="_blank" rel="noreferrer" data-testid="task-transaction-link">View settlement <ExternalLink size={14} /></a>
        : <span data-testid="task-no-transaction">No settlement recorded</span>}
    </section>
  </div>;
}
