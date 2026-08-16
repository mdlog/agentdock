import { useEffect, useState } from "react";
import { ArrowUpRight } from "lucide-react";
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
  // The agent on its way out. Holding both for the length of the slide is what
  // makes this read as one card replacing another, rather than the same card
  // blinking with different text in it.
  const [leaving, setLeaving] = useState<Verified | null>(null);

  useEffect(() => {
    api.get("/marketplace/verified?limit=8")
      .then(r => setAgents(r.data.items || []))
      .catch(() => setAgents([]));
  }, []);

  useEffect(() => {
    if (agents.length < 2) return;
    const timer = setInterval(() => {
      setIndex(current => {
        setLeaving(agents[current]);
        return (current + 1) % agents.length;
      });
    }, intervalMs);
    return () => clearInterval(timer);
  }, [agents, intervalMs]);

  useEffect(() => {
    if (!leaving) return;
    const timer = setTimeout(() => setLeaving(null), 700);
    return () => clearTimeout(timer);
  }, [leaving]);

  if (!agents.length) return null;
  const agent = agents[index];
  const backend = process.env.REACT_APP_BACKEND_URL;

  const slide = (item: Verified, role: "in" | "out") => (
    <article
      key={`${role}-${item.id}`}
      className={`spotlight-slide ${role}`}
      data-testid={role === "in" ? `spotlight-${item.token_id}` : undefined}
      aria-hidden={role === "out"}
    >
      <div className="spotlight-head">
        <AgentAvatar
          name={`${item.chain_id}-${item.token_id}-${item.name}`}
          testId={`spotlight-avatar-${item.token_id}`}
          size={46}
          src={item.has_source_icon ? `${backend}/api/onchain/agents/mainnet/${item.token_id}/icon` : undefined}
        />
        <div>
          <strong>{item.name}</strong>
          <span>{item.endpoint_kind?.toUpperCase()} · {item.tool_count} tools it declares</span>
        </div>
      </div>
      <p>{item.description}</p>
      {/* The departing copy must not be reachable by keyboard while it slides. */}
      <Link to={`/hire/${item.id}`} data-testid={`spotlight-activate-${item.token_id}`} tabIndex={role === "out" ? -1 : 0}>
        Activate <ArrowUpRight size={14} />
      </Link>
    </article>
  );

  return (
    <aside className="verified-spotlight" data-testid="verified-spotlight">
      {/* Both slides share one grid cell, so the outgoing card travels left as
          the incoming one arrives from the right and the box never resizes. */}
      <div className="spotlight-track">
        {leaving && slide(leaving, "out")}
        {slide(agent, "in")}
      </div>
      <div className="spotlight-dots" aria-hidden>
        {agents.map((a, i) => <span key={a.id} className={i === index ? "on" : ""} />)}
      </div>
    </aside>
  );
};
