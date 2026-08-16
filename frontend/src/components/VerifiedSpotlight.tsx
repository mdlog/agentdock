import { useEffect, useState } from "react";
import { ArrowUpRight, BadgeCheck } from "lucide-react";
import { Link } from "react-router-dom";
import { api } from "@/lib/api";
import { AgentAvatar } from "@/components/AgentAvatar";

type Verified = {
  id: string;
  chain_id: number;
  token_id: number;
  name: string;
  description: string;
  endpoint_kind: string | null;
  tool_count: number;
  has_source_icon: boolean;
};

// The hero's right-hand side, showing agents whose endpoints answered when we
// called them. Deliberately not a feed of new registrations: 265 agents
// registered today, none proven callable and most named things like
// "cccccccccc", so that feed would make the registry look busy while showing
// nothing usable — the impression this product exists to correct. These few are
// the hardest thing to find in 257,000 rows, so the hero is where they belong.
//
// It changes slowly on purpose. The headline beside it already rotates, and two
// things moving at the same pace compete; this one reads as a card, not an
// animation.
export const VerifiedSpotlight = ({ intervalMs = 9000 }: { intervalMs?: number }) => {
  const [agents, setAgents] = useState<Verified[]>([]);
  const [index, setIndex] = useState(0);
  const [total, setTotal] = useState(0);
  const [catalogue, setCatalogue] = useState(0);

  useEffect(() => {
    api.get("/marketplace/verified?limit=8")
      .then(r => { setAgents(r.data.items || []); setTotal(r.data.total_live || 0); setCatalogue(r.data.catalogue_total || 0); })
      .catch(() => setAgents([]));
  }, []);

  useEffect(() => {
    if (agents.length < 2) return;
    const timer = setInterval(() => setIndex(i => (i + 1) % agents.length), intervalMs);
    return () => clearInterval(timer);
  }, [agents, intervalMs]);

  if (!agents.length) return null;
  const agent = agents[index];
  const backend = process.env.REACT_APP_BACKEND_URL;

  return (
    <aside className="verified-spotlight" data-testid="verified-spotlight">
      {/* The ratio is the argument: finding these is what the marketplace is for. */}
      <p className="spotlight-kicker"><BadgeCheck size={13} /> {total} callable of {catalogue.toLocaleString()}</p>
      {/* Keyed on the agent so React swaps the node and the entry animation
          replays, rather than mutating text in place. */}
      <article key={agent.id} data-testid={`spotlight-${agent.token_id}`}>
        <div className="spotlight-head">
          <AgentAvatar
            name={`${agent.chain_id}-${agent.token_id}-${agent.name}`}
            testId={`spotlight-avatar-${agent.token_id}`}
            src={agent.has_source_icon ? `${backend}/api/onchain/agents/mainnet/${agent.token_id}/icon` : undefined}
          />
          <div>
            <strong>{agent.name}</strong>
            <span>{agent.endpoint_kind?.toUpperCase()} · {agent.tool_count} tools it declares</span>
          </div>
        </div>
        <p>{agent.description}</p>
        <Link to={`/hire/${agent.id}`} data-testid={`spotlight-activate-${agent.token_id}`}>
          Activate <ArrowUpRight size={14} />
        </Link>
      </article>
      <div className="spotlight-dots" aria-hidden>
        {agents.map((a, i) => <span key={a.id} className={i === index ? "on" : ""} />)}
      </div>
    </aside>
  );
};
