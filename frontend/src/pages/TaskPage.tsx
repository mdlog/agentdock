import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, Clock3, ExternalLink, FileSearch, Loader2, PenLine, Play } from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { useAccount, useChainId, useSignTypedData, useSwitchChain } from "wagmi";
import { toast } from "sonner";
import { AGENT_CALL, api, messageFromError, PAID_CALL } from "@/lib/api";
import type { AuditEvent, Task, TypedData } from "@/types";
import { Button } from "@/components/ui/button";
import { WalletButton } from "@/components/WalletButton";
import { DEFAULT_CHAIN } from "@/lib/erc8004";
import { ACTION_FLOW, FlowRail, FREE_FLOW, PAID_FLOW } from "@/components/FlowRail";

// Where the task sits on its rail. A free agent is never priced or signed, so
// it runs the three-step flow; only a b402 task has a payment stage to be at.
const railPosition = (state: string, paid: boolean, busy: boolean) => {
  if (paid) return Math.max(0, PAID_FLOW.findIndex(s => s.key === state));
  if (state === "completed") return 2;
  return busy ? 1 : 0;
};

export default function TaskPage() {
  const { taskId } = useParams();
  const { address } = useAccount();
  const chainId = useChainId();
  const { switchChain, switchChainAsync } = useSwitchChain();
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
      const r = await api.post(`/tasks/${taskId}/run`, undefined, AGENT_CALL);
      toast.success(r.data.paid ? "Merchant quoted a price" : "Agent answered without charging");
      await load();
    } catch (e) {
      toast.error(messageFromError(e));
      // The server has already recorded why. Reload so the rail, the status
      // chip and the audit trail show it instead of staying frozen on step 1.
      await load().catch(() => {});
    } finally { setBusy(""); }
  };

  // Authorize and sign are deliberately one action: the merchant's window is
  // short, so the typed data is minted immediately before the wallet prompt.
  const payTask = async () => {
    if (!address) return;
    setBusy("pay");
    try {
      // The EIP-712 domain is bound to chain 56, and viem refuses to sign if the
      // wallet is on any other chain (seen: "chainId 56 must match active 677").
      // Force the switch first rather than relying on the page's chainId, which
      // can lag the wallet or miss an unknown chain.
      if (chainId !== DEFAULT_CHAIN.chainId) {
        await switchChainAsync({ chainId: DEFAULT_CHAIN.chainId });
      }
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
      await api.post(`/tasks/${taskId}/pay`, { signature }, PAID_CALL);
      toast.success("Payment settled and agent executed");
      await load();
    } catch (e: any) {
      toast.error(e?.name === "UserRejectedRequestError" ? "You rejected the signature. Nothing was paid." : messageFromError(e));
      await load().catch(() => {});
    } finally { setBusy(""); }
  };

  if (loadError) return <div className="page-wrap empty-state" data-testid="task-detail-error"><AlertTriangle size={28} /><h1>Task unavailable</h1><p>{loadError}</p><Button data-testid="task-error-home-button" asChild><Link to="/">Back to marketplace</Link></Button></div>;
  if (!task) return <div className="page-wrap" data-testid="task-loading">Loading task…</div>;

  const paidFlow = !task.endpoint_kind;
  const steps = paidFlow ? PAID_FLOW : task.agent_action ? ACTION_FLOW : FREE_FLOW;
  const failed = task.state === "failed" || task.state === "manual_resolution";
  // A failed task marks the step that actually failed, not step one: being
  // described succeeded, and a priced task that fails did so at signing.
  const current = failed
    ? (paidFlow ? (task.payment_terms ? 2 : 1) : 1)
    : railPosition(task.state, paidFlow, !!busy);
  const terms = task.payment_terms;
  const wrongChain = !!address && chainId !== DEFAULT_CHAIN.chainId;

  return <div className="page-wrap task-page">
    <div className="page-heading"><div><p className="section-kicker">Task execution</p><h1 data-testid="task-heading">{task.agent_name}</h1><p data-testid="task-id">Task {task.id}</p></div><span className={`task-status status-${task.state}`} data-testid="task-current-status">{task.state.replace("_", " ")}</span></div>

    <FlowRail steps={steps} current={current} busy={!!busy} failed={failed} testId="task-state-track" />

    {task.state === "created" && <section className="blocked-payment" data-testid="task-run-panel">
      <Play size={22} />
      {task.endpoint_kind
        ? <><div><h2>{task.agent_action ? <>Run <code>{task.agent_action}</code></> : "Run this agent"}</h2><p>{task.agent_action
            ? <>AgentDock calls this agent's <strong>{task.agent_action}</strong> tool on its live {task.endpoint_kind.toUpperCase()} endpoint and returns exactly what it answers. It does not charge — no signature, no payment.</>
            : <>AgentDock sends your request to the agent's live {task.endpoint_kind.toUpperCase()} endpoint and returns the real result. This agent does not charge — no signature, no payment.</>}</p></div>
            <Button data-testid="run-task-button" onClick={runTask} disabled={busy === "run"}>{busy === "run" ? <><Loader2 size={15} className="spin" /> Running…</> : "Run agent"}</Button></>
        : <><div><h2>Ask the agent for its price</h2><p>AgentDock calls the endpoint once without paying. The merchant answers with the exact token, amount and recipient — nothing is signed at this step.</p></div>
            <Button data-testid="run-task-button" onClick={runTask} disabled={busy === "run"}>{busy === "run" ? <><Loader2 size={15} className="spin" /> Asking…</> : "Get price"}</Button></>}
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
          : <Button data-testid="sign-and-pay-button" onClick={payTask} disabled={busy === "pay"}>{busy === "pay" ? <><Loader2 size={15} className="spin" /> Waiting for your wallet…</> : `Sign & pay ${terms.amount_tokens} ${terms.asset_name}`}</Button>}
        <p className="payment-locked"><AlertTriangle size={14} /> Your wallet signs an authorization. AgentDock never holds your key.</p>
      </div>
    </section>}

    <div className="task-grid">
      <section className="plain-section"><div className="section-title"><h2>Request</h2><FileSearch size={17} /></div><dl className="brief-list">
        <div><dt>{task.agent_action ? "Action" : "Objective"}</dt><dd data-testid="task-objective">{task.agent_action ? <code>{task.agent_action}</code> : task.objective}</dd></div>
        <div><dt>Price</dt><dd data-testid="task-max-cost">{task.estimated_price_usd === null ? "Not quoted yet" : `${task.estimated_price_usd} ${terms?.asset_name ?? ""}`.trim()}</dd></div>
        <div><dt>Network</dt><dd data-testid="task-network">{DEFAULT_CHAIN.label} · {DEFAULT_CHAIN.chainId}</dd></div>
      </dl></section>

      <section className="plain-section"><div className="section-title"><h2>Audit trail</h2><span>{events.length} events</span></div><div className="audit-list" data-testid="task-audit-list">{events.map(event => <div className="audit-event" key={event.id} data-testid={`audit-event-${event.id}`}><span><Clock3 size={14} /></span><div><strong>{event.event}</strong><p>{event.detail}</p><time>{new Date(event.created_at).toLocaleString()}</time></div></div>)}</div></section>
    </div>

    <section className="result-zone" data-testid="task-result-zone">
      <div>
        <p className="section-kicker">Result</p>
        <h2>{failed ? "The agent did not complete this" : task.result_preview ? "Agent responded" : "No result yet"}</h2>
        {task.result_preview
          ? <pre className="result-body" data-testid="task-result-body">{task.result_preview}</pre>
          : <p>{paidFlow ? "The agent runs once its payment is settled." : "The agent runs as soon as you start it."}</p>}
      </div>
      {task.tx_hash
        ? <a href={`${DEFAULT_CHAIN.explorer}/tx/${task.tx_hash}`} target="_blank" rel="noreferrer" data-testid="task-transaction-link">View settlement <ExternalLink size={14} /></a>
        : <span data-testid="task-no-transaction">No settlement recorded</span>}
    </section>
  </div>;
}
