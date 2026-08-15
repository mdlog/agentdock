import { useEffect, useMemo, useState } from "react";
import { ArrowRight, Search, ShieldAlert, SlidersHorizontal, Sparkles } from "lucide-react";
import { Link } from "react-router-dom";
import { api } from "@/lib/api";
import type { OnchainAgent, Readiness } from "@/types";
import { OnchainAgentCard } from "@/components/OnchainAgentCard";
import { useCompare } from "@/hooks/useCompare";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";

// The catalog is real BSC Mainnet ERC-8004 identities only. 8004scan publishes
// no price and no callable endpoint, so hiring stays visibly unavailable rather
// than being backed by invented figures.
export default function MarketplacePage() {
  const [onchain, setOnchain] = useState<OnchainAgent[]>([]);
  const [readiness, setReadiness] = useState<Readiness | null>(null);
  const [search, setSearch] = useState("");
  const [protocol, setProtocol] = useState("all");
  const [sort, setSort] = useState("score");
  const [loading, setLoading] = useState(true);
  const { selected, toggle } = useCompare();

  useEffect(() => {
    api.get("/onchain/agents?network=mainnet")
      .then(o => setOnchain(o.data.items))
      .catch(() => setOnchain([]))
      .finally(() => setLoading(false));
    // Readiness drives an advisory banner only; a slow check must never keep the
    // catalog from rendering.
    api.get("/integrations/readiness").then(r => setReadiness(r.data)).catch(() => setReadiness(null));
  }, []);

  const protocols = useMemo(() => Array.from(new Set(onchain.flatMap(a => a.supported_protocols))).sort(), [onchain]);
  const query = search.toLowerCase();

  const visible = useMemo(() => onchain
    .filter(a => (protocol === "all" || a.supported_protocols.includes(protocol)) && `${a.name} ${a.description}`.toLowerCase().includes(query))
    .sort((a, b) => sort === "rank" ? (a.rank ?? 999999) - (b.rank ?? 999999) : sort === "feedback" ? b.total_feedbacks - a.total_feedbacks : (b.total_score ?? -1) - (a.total_score ?? -1)),
    [onchain, query, protocol, sort]);

  return <div>
    <section className="search-stage">
      <div className="stage-copy"><span className="eyebrow"><Sparkles size={14} /> Verified research, before you act</span><h1 data-testid="marketplace-heading">Find the right agent for your next DeFi decision.</h1><p data-testid="marketplace-subheading">Compare evidence, cost, and measured performance. Agents research—your wallet stays under your control.</p></div>
      <div className="search-box"><Search size={21} /><Input data-testid="marketplace-search-input" value={search} onChange={e => setSearch(e.target.value)} placeholder="Try “prediction”, “trading”, or “stablecoin yield”" /><kbd>⌘ K</kbd></div>
      <div className="trust-row" data-testid="marketplace-stats"><span><strong data-testid="stat-onchain-count">{onchain.length}</strong> onchain agents</span><span><strong data-testid="stat-protocol-count">{protocols.length}</strong> declared protocols</span><span><strong>BSC</strong> mainnet identities</span></div>
    </section>

    {!readiness?.b402_ready && <div className="integration-notice" data-testid="payment-readiness-alert"><ShieldAlert size={18} /><div><strong>Browse and compare are live. Payments remain safely locked.</strong><p>Binance B402 partner configuration is required before any wallet signature can be requested.</p></div></div>}

    <section className="catalog-section">
      <div className="catalog-heading"><div><p className="section-kicker">Onchain identities · 8004scan</p><h2 data-testid="catalog-heading">Real ERC-8004 agents on BSC Mainnet</h2></div><span data-testid="agent-result-count">{visible.length} matches</span></div>
      <div className="filter-bar" data-testid="agent-filter-bar"><SlidersHorizontal size={16} />
        <Select value={protocol} onValueChange={setProtocol}><SelectTrigger data-testid="protocol-filter"><SelectValue placeholder="Protocol" /></SelectTrigger><SelectContent><SelectItem data-testid="protocol-all" value="all">All protocols</SelectItem>{protocols.map(p => <SelectItem data-testid={`protocol-${p.toLowerCase()}`} value={p} key={p}>{p}</SelectItem>)}</SelectContent></Select>
        <Select value={sort} onValueChange={setSort}><SelectTrigger data-testid="sort-filter"><SelectValue /></SelectTrigger><SelectContent><SelectItem data-testid="sort-score" value="score">8004scan score</SelectItem><SelectItem data-testid="sort-rank" value="rank">Network rank</SelectItem><SelectItem data-testid="sort-feedback" value="feedback">Feedback volume</SelectItem></SelectContent></Select>
        <span />
        {selected.length > 0 && <Button data-testid="open-comparison-button" asChild className="compare-floating"><Link to="/compare">Compare {selected.length}/3 <ArrowRight size={15} /></Link></Button>}
      </div>
      {loading
        ? <div className="onchain-grid" data-testid="agents-loading">{[1,2,3,4,5,6].map(x => <Skeleton className="h-72" key={x} />)}</div>
        : visible.length
          ? <div className="onchain-grid" data-testid="agent-grid">{visible.map(agent => <OnchainAgentCard key={agent.id} agent={agent} network="mainnet" compare={{ selected: selected.includes(agent.id), toggle }} />)}</div>
          : <div className="empty-state" data-testid="agents-empty-state"><Search size={28} /><h3>No onchain agents match this search</h3><p>Try a broader term, or clear the protocol filter.</p></div>}
    </section>
  </div>;
}
