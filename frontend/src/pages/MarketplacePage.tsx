import { useEffect, useMemo, useState } from "react";
import { ArrowRight, Search, ShieldAlert, SlidersHorizontal, Sparkles, Zap } from "lucide-react";
import { Link } from "react-router-dom";
import { api } from "@/lib/api";
import type { AgentCategory, B402Resource, OnchainAgent } from "@/types";
import { OnchainAgentCard } from "@/components/OnchainAgentCard";
import { B402ResourceCard } from "@/components/B402ResourceCard";
import { CategoryBrowse } from "@/components/CategoryBrowse";
import { Pagination } from "@/components/Pagination";
import { useCompare } from "@/hooks/useCompare";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";

// The marketplace leads with the four judged categories (Rebalancing, Grid
// Trading, Yield Optimisation, Health Factor Monitoring). Picking one filters
// the real onchain catalogue AND the hireable b402 services server-side, so a
// judge can land, choose a category, and drill into agents that do that job.
export default function MarketplacePage() {
  const PAGE = 60;
  const [onchain, setOnchain] = useState<OnchainAgent[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [payable, setPayable] = useState<B402Resource[]>([]);
  const [categories, setCategories] = useState<AgentCategory[]>([]);
  const [category, setCategory] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");
  const [protocol, setProtocol] = useState("all");
  const [sort, setSort] = useState("score");
  const [loading, setLoading] = useState(true);
  const { selected, toggle } = useCompare();

  // Typing must not fire a query per keystroke against a 256k catalogue.
  useEffect(() => { const id = setTimeout(() => { setDebounced(search); setOffset(0); }, 350); return () => clearTimeout(id); }, [search]);

  useEffect(() => {
    setLoading(true);
    const params = new URLSearchParams({ network: "mainnet", sort, offset: String(offset), limit: String(PAGE) });
    if (debounced) params.set("search", debounced);
    if (protocol !== "all") params.set("protocol", protocol);
    if (category) params.set("category", category);
    // Searching, filtering and sorting all happen server-side: the browser only
    // ever holds one page.
    api.get(`/onchain/agents?${params}`)
      .then(o => { setOnchain(o.data.items); setTotal(o.data.total); })
      .catch(() => { setOnchain([]); setTotal(0); })
      .finally(() => setLoading(false));
  }, [debounced, protocol, sort, offset, category]);

  useEffect(() => {
    api.get("/b402/resources").then(r => setPayable(r.data.items)).catch(() => setPayable([]));
    api.get("/categories").then(r => setCategories(r.data.categories)).catch(() => setCategories([]));
  }, []);

  const selectCategory = (key: string | null) => { setCategory(key); setOffset(0); };
  const activeCat = categories.find(c => c.key === category) || null;

  const protocols = ["MCP", "A2A", "Web", "Email", "OASF"];
  const query = search.toLowerCase();
  const visiblePayable = useMemo(() => payable.filter(r =>
    (!category || (r.categories || []).includes(category)) &&
    `${r.host} ${r.description}`.toLowerCase().includes(query)
  ), [payable, query, category]);

  return <div>
    <section className="search-stage">
      <div className="stage-copy"><span className="eyebrow"><Sparkles size={14} /> Agent marketplace on BNB Chain</span><h1 data-testid="marketplace-heading">Find the right agent for your next DeFi move.</h1><p data-testid="marketplace-subheading">Browse by what the agent does—rebalancing, grid trading, yield, or health-factor monitoring—on real BNB Chain identities. Your wallet stays under your control.</p></div>
      <div className="search-box"><Search size={21} /><Input data-testid="marketplace-search-input" value={search} onChange={e => setSearch(e.target.value)} placeholder="Search agents by name or what they do" /><kbd>⌘ K</kbd></div>
      <div className="trust-row" data-testid="marketplace-stats"><span><strong data-testid="stat-payable-count">{payable.length}</strong> hireable now</span><span><strong data-testid="stat-onchain-count">{total.toLocaleString()}</strong> onchain agents</span><span><strong>BNB</strong> Chain mainnet</span></div>
    </section>

    <CategoryBrowse categories={categories} selected={category} onSelect={selectCategory} />

    {visiblePayable.length > 0 && <section className="catalog-section">
      <div className="catalog-heading"><div><p className="section-kicker"><Zap size={13} /> Pay per call · b402 Bazaar</p><h2 data-testid="payable-heading">{activeCat ? `Hireable ${activeCat.label} agents` : "Agents you can hire right now"}</h2></div><span data-testid="payable-result-count">{visiblePayable.length} services</span></div>
      <div className="payable-notice" data-testid="payable-notice"><ShieldAlert size={18} /><div><strong>Paying is permissionless — you sign, AgentDock never holds a key.</strong><p>Each merchant quotes its own price when the task runs. The exact token, amount and recipient are shown before your wallet is asked to sign, and settlement happens on BNB Chain.</p></div></div>
      <div className="onchain-grid" data-testid="payable-grid">{visiblePayable.map(r => <B402ResourceCard key={r.id} resource={r} />)}</div>
    </section>}

    <section className="catalog-section">
      <div className="catalog-heading"><div><p className="section-kicker">Onchain identities · 8004scan</p><h2 data-testid="catalog-heading">{activeCat ? `${activeCat.label} agents` : "All onchain agents on BNB Chain"}</h2><p className="section-note" data-testid="onchain-hire-note">{activeCat ? activeCat.blurb + " Discovered from 8004scan by each agent's own onchain metadata." : "Discovered from 8004scan. Pick a category above to narrow to agents that do a specific job."}</p></div><span data-testid="agent-result-count">{total.toLocaleString()} matches</span></div>
      <div className="filter-bar" data-testid="agent-filter-bar"><SlidersHorizontal size={16} />
        <Select value={protocol} onValueChange={v => { setProtocol(v); setOffset(0); }}><SelectTrigger data-testid="protocol-filter"><SelectValue placeholder="Protocol" /></SelectTrigger><SelectContent><SelectItem data-testid="protocol-all" value="all">All protocols</SelectItem>{protocols.map(p => <SelectItem data-testid={`protocol-${p.toLowerCase()}`} value={p} key={p}>{p}</SelectItem>)}</SelectContent></Select>
        <Select value={sort} onValueChange={v => { setSort(v); setOffset(0); }}><SelectTrigger data-testid="sort-filter"><SelectValue /></SelectTrigger><SelectContent><SelectItem data-testid="sort-score" value="score">8004scan score</SelectItem><SelectItem data-testid="sort-rank" value="rank">Network rank</SelectItem><SelectItem data-testid="sort-feedback" value="feedback">Feedback volume</SelectItem></SelectContent></Select>
        <span />
        {selected.length > 0 && <Button data-testid="open-comparison-button" asChild className="compare-floating"><Link to="/compare">Compare {selected.length}/3 <ArrowRight size={15} /></Link></Button>}
      </div>
      {loading
        ? <div className="onchain-grid" data-testid="agents-loading">{[1,2,3,4,5,6].map(x => <Skeleton className="h-72" key={x} />)}</div>
        : onchain.length
          ? <><div className="onchain-grid" data-testid="agent-grid">{onchain.map(agent => <OnchainAgentCard key={agent.id} agent={agent} network="mainnet" compare={{ selected: selected.includes(agent.id), toggle }} />)}</div>
            <Pagination total={total} offset={offset} limit={PAGE} onChange={setOffset} testId="onchain-pagination" /></>
          : <div className="empty-state" data-testid="agents-empty-state"><Search size={28} /><h3>No agents match</h3><p>{activeCat ? "No agents in this category match your search yet." : "Try a broader term, or clear the protocol filter."}</p></div>}
    </section>
  </div>;
}
