import { Activity, BadgeCheck, Check, ExternalLink, Zap } from "lucide-react";
import { Link } from "react-router-dom";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { AgentAvatar } from "@/components/AgentAvatar";
import type { OnchainAgent } from "@/types";

export const compactNumber = (value?: number) =>
  typeof value === "number" ? Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 }).format(value) : "—";

// Rendered by both the marketplace catalog and the Onchain explorer. Passing
// `compare` switches on the marketplace-only row: 8004scan publishes no price,
// so hiring stays visibly unavailable instead of silently missing.
export const OnchainAgentCard = ({ agent, network, compare }: {
  agent: OnchainAgent;
  network: "mainnet" | "testnet";
  compare?: { selected: boolean; toggle: (id: string) => void };
}) => {
  const backendUrl = process.env.REACT_APP_BACKEND_URL;
  const iconSrc = agent.has_source_icon ? `${backendUrl}/api/onchain/agents/${network}/${agent.token_id}/icon` : undefined;
  const scanBase = agent.is_testnet ? "https://testnet.bscscan.com" : "https://bscscan.com";

  return (
    <article className="onchain-card" data-testid={`onchain-agent-${agent.token_id}`}>
      <div className="onchain-card-top">
        <AgentAvatar name={`${agent.chain_id}-${agent.token_id}-${agent.name}`} testId={`onchain-avatar-${agent.token_id}`} src={iconSrc} />
        <div>
          <div className="onchain-name"><h2 data-testid={`onchain-name-${agent.token_id}`}>{agent.name}</h2>{agent.is_verified && <BadgeCheck size={15} />}</div>
          <span data-testid={`onchain-id-${agent.token_id}`}>ERC-8004 #{agent.token_id}</span>
        </div>
        {agent.x402_supported && <Badge data-testid={`onchain-x402-${agent.token_id}`} className="x402-badge"><Zap size={10} /> x402 claim</Badge>}
      </div>

      <p data-testid={`onchain-description-${agent.token_id}`}>{agent.description}</p>
      <div className="protocol-list" data-testid={`onchain-protocols-${agent.token_id}`}>
        {agent.supported_protocols.length ? agent.supported_protocols.map(p => <span key={p}>{p}</span>) : <span>No protocol declared</span>}
      </div>

      <div className="onchain-metrics">
        <div><strong data-testid={`onchain-score-${agent.token_id}`}>{agent.total_score ?? "—"}</strong><span>8004scan score</span></div>
        <div><strong data-testid={`onchain-rank-${agent.token_id}`}>{agent.rank ? `#${agent.rank}` : "—"}</strong><span>Network rank</span></div>
        <div><strong data-testid={`onchain-feedback-${agent.token_id}`}>{compactNumber(agent.total_feedbacks)}</strong><span>Feedbacks</span></div>
      </div>

      {compare && (
        <div className="onchain-hire-row" data-testid={`onchain-hire-row-${agent.token_id}`}>
          <div>
            {agent.activatable
              ? <><strong data-testid={`onchain-status-${agent.token_id}`} className="activatable-tag">Live {agent.endpoint_kind?.toUpperCase()} endpoint</strong><span>Free to activate</span></>
              : <><strong data-testid={`onchain-price-${agent.token_id}`}>Identity only</strong><span>No callable endpoint</span></>}
          </div>
          <div className="card-actions">
            <Button
              data-testid={`compare-onchain-${agent.token_id}`}
              variant="outline"
              size="sm"
              className={compare.selected ? "selected-compare" : ""}
              onClick={() => compare.toggle(agent.id)}
            >
              {compare.selected && <Check size={14} />}{compare.selected ? "Selected" : "Compare"}
            </Button>
            {agent.activatable
              ? <Button data-testid={`activate-onchain-${agent.token_id}`} size="sm" asChild><Link to={`/hire/${agent.id}`}>Activate</Link></Button>
              : <Button data-testid={`hire-onchain-${agent.token_id}`} size="sm" disabled title="This agent publishes no callable endpoint, so it cannot be activated yet.">Activate</Button>}
          </div>
        </div>
      )}

      <div className="onchain-footer">
        <span><Activity size={12} />{agent.source_label}</span>
        <div>
          <Button data-testid={`onchain-detail-${agent.token_id}`} variant="ghost" size="sm" asChild>
            <Link to={`/onchain/${network}/${agent.token_id}`}>Details</Link>
          </Button>
          {agent.contract_address && (
            <a data-testid={`onchain-contract-${agent.token_id}`} href={`${scanBase}/address/${agent.contract_address}`} target="_blank" rel="noreferrer" aria-label="View contract on BscScan">
              <ExternalLink size={14} />
            </a>
          )}
        </div>
      </div>
    </article>
  );
};
