import { useEffect, useMemo, useState } from "react";
import { ArrowRight, Search, ShieldAlert, SlidersHorizontal, Sparkles, Zap } from "lucide-react";
import { Link } from "react-router-dom";
import { api } from "@/lib/api";
import type { B402Resource, OnchainAgent } from "@/types";
import { OnchainAgentCard } from "@/components/OnchainAgentCard";
import { B402ResourceCard } from "@/components/B402ResourceCard";
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
  const [payable, setPayable] = useState<B402Resource[]>([]);
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
    // Payable services are independent of the identity catalog: one failing must
    // not blank the other.
    api.get("/b402/resources").then(r => setPayable(r.data.items)).catch(() => setPayable([]));
  }, []);

  const protocols = useMemo(() => Array.from(new Set(onchain.flatMap(a => a.supported_protocols))).sort(), [onchain]);
  const query = search.toLowerCase();

  const visible = useMemo(() => onchain
    .filter(a => (protocol === "all" || a.supported_protocols.includes(protocol)) && `${a.name} ${a.description}`.toLowerCase().includes(query))
    .sort((a, b) => sort === "rank" ? (a.rank ?? 999999) - (b.rank ?? 999999) : sort === "feedback" ? b.total_feedbacks - a.total_feedbacks : (b.total_score ?? -1) - (a.total_score ?? -1)),
    [onchain, query, protocol, sort]);

  const visiblePayable = useMemo(() => payable.filter(r => `${r.host} ${r.description}`.toLowerCase().includes(query)), [payable, query]);

  return <div>
    <section className="search-stage">
      <div className="stage-copy"><span className="eyebrow"><Sparkles size={14} /> Verified research, before you act</span><h1 data-testid="marketplace-heading">Find the right agent for your next DeFi decision.</h1><p data-testid="marketplace-subheading">Compare evidence, cost, and measured performance. Agents research—your wallet stays under your control.</p></div>
      <div className="search-box"><Search size={21} /><Input data-testid="marketplace-search-input" value={search} onChange={e => setSearch(e.target.value)} placeholder="Try “prediction”, “trading”, or “stablecoin yield”" /><kbd>⌘ K</kbd></div>
      <div className="trust-row" data-testid="marketplace-stats"><span><strong data-testid="stat-payable-count">{payable.length}</strong> payable services</span><span><strong data-testid="stat-onchain-count">{onchain.length}</strong> onchain identities</span><span><strong>BNB</strong> Chain mainnet</span></div>
    </section>

    <section className="catalog-section">
      <div className="catalog-heading"><div><p className="section-kicker"><Zap size={13} /> Pay per call · b402 Bazaar</p><h2 data-testid="payable-heading">Agents you can hire right now</h2></div><span data-testid="payable-result-count">{visiblePayable.length} services</span></div>
      <div className="payable-notice" data-testid="payable-notice"><ShieldAlert size={18} /><div><strong>Paying is permissionless — you sign, AgentDock never holds a key.</strong><p>Each merchant quotes its own price when the task runs. The exact token, amount and recipient are shown before your wallet is asked to sign, and settlement happens on BNB Chain.</p></div></div>
      {visiblePayable.length
        ? <div className="onchain-grid" data-testid="payable-grid">{visiblePayable.map(r => <B402ResourceCard key={r.id} resource={r} />)}</div>
        : <div className="empty-state" data-testid="payable-empty-state"><Search size={28} /><h3>No payable services match this search</h3><p>Clear the search to see the full b402 catalog.</p></div>}
    </section>

    <section className="catalog-section">
      <div className="catalog-heading"><div><p className="section-kicker">Onchain identities · 8004scan</p><h2 data-testid="catalog-heading">Onchain identities on BNB Chain</h2><p className="section-note" data-testid="onchain-hire-note">Discovered from 8004scan. These publish identity and reputation but no payable endpoint, so they cannot be hired yet.</p></div><span data-testid="agent-result-count">{visible.length} matches</span></div>
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
