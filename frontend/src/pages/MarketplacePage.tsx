import { useEffect, useMemo, useState } from "react";
import { ArrowRight, Search, ShieldAlert, SlidersHorizontal, Sparkles } from "lucide-react";
import { Link } from "react-router-dom";
import { api } from "@/lib/api";
import type { Agent, Readiness } from "@/types";
import { AgentCard } from "@/components/AgentCard";
import { useCompare } from "@/hooks/useCompare";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";

export default function MarketplacePage() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [readiness, setReadiness] = useState<Readiness | null>(null);
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("all");
  const [status, setStatus] = useState("active");
  const [sort, setSort] = useState("reputation");
  const [loading, setLoading] = useState(true);
  const { selected, toggle } = useCompare();

  useEffect(() => { Promise.all([api.get("/agents"), api.get("/integrations/readiness")]).then(([a, r]) => { setAgents(a.data.items); setReadiness(r.data); }).catch(() => setAgents([])).finally(() => setLoading(false)); }, []);
  const categories = useMemo(() => Array.from(new Set(agents.map(a => a.category))), [agents]);
  const visible = useMemo(() => agents.filter(a => (status === "all" || a.status === status) && (category === "all" || a.category === category) && `${a.name} ${a.tagline} ${a.capabilities.join(" ")}`.toLowerCase().includes(search.toLowerCase())).sort((a,b) => sort === "price_low" ? a.price_usd-b.price_usd : sort === "latency" ? a.metrics.latency_sec-b.metrics.latency_sec : b.metrics.reputation_score-a.metrics.reputation_score), [agents, search, category, status, sort]);

  return <div>
    <section className="search-stage">
      <div className="stage-copy"><span className="eyebrow"><Sparkles size={14} /> Verified research, before you act</span><h1 data-testid="marketplace-heading">Find the right agent for your next DeFi decision.</h1><p data-testid="marketplace-subheading">Compare evidence, cost, and measured performance. Agents research—your wallet stays under your control.</p></div>
      <div className="search-box"><Search size={21} /><Input data-testid="marketplace-search-input" value={search} onChange={e => setSearch(e.target.value)} placeholder="Try “low-risk stablecoin yield”" /><kbd>⌘ K</kbd></div>
      <div className="trust-row" data-testid="marketplace-stats"><span><strong>20</strong> indexed agents</span><span><strong>4</strong> research categories</span><span><strong>BSC</strong> testnet network</span></div>
    </section>

    {!readiness?.b402_ready && <div className="integration-notice" data-testid="payment-readiness-alert"><ShieldAlert size={18} /><div><strong>Browse and compare are live. Payments remain safely locked.</strong><p>Binance B402 partner configuration is required before any wallet signature can be requested.</p></div></div>}

    <section className="catalog-section">
      <div className="catalog-heading"><div><p className="section-kicker">Agent index</p><h2 data-testid="catalog-heading">Evidence-led research agents</h2></div><span data-testid="agent-result-count">{visible.length} matches</span></div>
      <div className="filter-bar" data-testid="agent-filter-bar"><SlidersHorizontal size={16} />
        <Select value={category} onValueChange={setCategory}><SelectTrigger data-testid="category-filter"><SelectValue placeholder="Category" /></SelectTrigger><SelectContent><SelectItem data-testid="category-all" value="all">All categories</SelectItem>{categories.map(x => <SelectItem data-testid={`category-${x.toLowerCase().replaceAll(" ", "-")}`} value={x} key={x}>{x}</SelectItem>)}</SelectContent></Select>
        <Select value={status} onValueChange={setStatus}><SelectTrigger data-testid="status-filter"><SelectValue /></SelectTrigger><SelectContent><SelectItem data-testid="status-active" value="active">Active only</SelectItem><SelectItem data-testid="status-all" value="all">All status</SelectItem></SelectContent></Select>
        <Select value={sort} onValueChange={setSort}><SelectTrigger data-testid="sort-filter"><SelectValue /></SelectTrigger><SelectContent><SelectItem data-testid="sort-reputation" value="reputation">Highest proof score</SelectItem><SelectItem data-testid="sort-price" value="price_low">Lowest price</SelectItem><SelectItem data-testid="sort-latency" value="latency">Fastest response</SelectItem></SelectContent></Select>
        {selected.length > 0 && <Button data-testid="open-comparison-button" asChild className="compare-floating"><Link to="/compare">Compare {selected.length}/3 <ArrowRight size={15} /></Link></Button>}
      </div>
      {loading ? <div className="agent-grid" data-testid="agents-loading">{[1,2,3,4,5,6].map(x => <Skeleton className="h-80" key={x} />)}</div> : visible.length ? <div className="agent-grid" data-testid="agent-grid">{visible.map(agent => <AgentCard key={agent.id} agent={agent} selected={selected.includes(agent.id)} toggleCompare={toggle} />)}</div> : <div className="empty-state" data-testid="agents-empty-state"><Search size={28} /><h3>No agents match this search</h3><p>Try a broader job, capability, or category.</p></div>}
    </section>
  </div>;
}