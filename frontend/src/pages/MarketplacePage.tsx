import { useEffect, useMemo, useState } from "react";
import { ArrowRight, Search, ShieldAlert, Sparkles, Zap } from "lucide-react";
import { Link } from "react-router-dom";
import { api, messageFromError } from "@/lib/api";
import type { AgentCategory, B402Resource, MarketplaceTheme, OnchainAgent } from "@/types";
import { OnchainAgentCard } from "@/components/OnchainAgentCard";
import { B402ResourceCard } from "@/components/B402ResourceCard";
import { CategoryBrowse } from "@/components/CategoryBrowse";
import { RotatingWord } from "@/components/RotatingWord";
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
  const [readyTotal, setReadyTotal] = useState(0);
  // True when the count is a floor: an unindexed substring search stops
  // counting past a ceiling rather than walking 256k documents.
  const [totalCapped, setTotalCapped] = useState(false);
  const [offset, setOffset] = useState(0);
  const [payable, setPayable] = useState<B402Resource[]>([]);
  const [categories, setCategories] = useState<AgentCategory[]>([]);
  const [themes, setThemes] = useState<MarketplaceTheme[]>([]);
  const [category, setCategory] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");
  const [protocol, setProtocol] = useState("all");
  const [sort, setSort] = useState("ready");
  const [loading, setLoading] = useState(true);
  // A failed fetch and an empty catalogue look identical once the list is
  // cleared, and "No agents match · 0 matches" reads as a fact about BNB Chain
  // rather than as our own outage.
  const [loadError, setLoadError] = useState("");
  // Retrying needs a value that actually changes: setOffset(o => o) writes the
  // same number, React bails out, and the effect never re-runs.
  const [retry, setRetry] = useState(0);
  // Which registry to browse. The two sources answer different questions — one
  // is a directory of services you can buy, the other a registry of onchain
  // identities — so a visitor who wants only one should not have to scroll
  // past the other.
  const [source, setSource] = useState<"all" | "b402" | "onchain">("all");
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
      .then(o => { setOnchain(o.data.items); setTotal(o.data.total); setReadyTotal(o.data.ready_total ?? 0); setTotalCapped(Boolean(o.data.total_capped)); setLoadError(""); })
      .catch(e => { setOnchain([]); setTotal(0); setReadyTotal(0); setLoadError(messageFromError(e)); })
      .finally(() => setLoading(false));
  }, [debounced, protocol, sort, offset, category, retry]);

  useEffect(() => {
    api.get("/b402/resources").then(r => setPayable(r.data.items)).catch(() => setPayable([]));
    api.get("/categories")
      .then(r => { setCategories(r.data.categories); setThemes(r.data.themes || []); })
      .catch(() => { setCategories([]); setThemes([]); });
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
      <div className="stage-copy"><span className="eyebrow"><Sparkles size={14} /> Agent marketplace on BNB Chain</span><h1 data-testid="marketplace-heading">Find the right agent on BNB Chain for{" "}
        {themes.length > 1
          ? <RotatingWord words={themes.map(theme => theme.label)} />
          : <span>DeFi</span>}</h1><p data-testid="marketplace-subheading">Every categorised agent in the registry has been called to see whether it answers. Pick a job, compare the evidence, and activate the one that fits.</p></div>
      <div className="search-box"><Search size={21} /><Input data-testid="marketplace-search-input" value={search} onChange={e => setSearch(e.target.value)} placeholder="Search agents by name or what they do" /><kbd>⌘ K</kbd></div>
      <div className="trust-row" data-testid="marketplace-stats"><span><strong data-testid="stat-payable-count">{payable.length}</strong> hireable now</span><span><strong data-testid="stat-onchain-count">{total.toLocaleString()}</strong> onchain agents</span><span><strong>BNB</strong> Chain mainnet</span></div>
    </section>

    <CategoryBrowse
      categories={categories}
      selected={category}
      onSelect={selectCategory}
      leading={<nav className="source-switch" data-testid="source-switch" aria-label="Agent source">
        {/* The source each option names is spelled out in the section kicker
            directly below it ("Pay per call · b402 Bazaar"), so the control
            itself only needs the choice and its size. */}
        {([
          { key: "all", label: "All sources", count: null },
          { key: "b402", label: "Pay per call", count: visiblePayable.length },
          { key: "onchain", label: "Onchain", count: loadError ? null : total },
        ] as const).map(option =>
          <button
            key={option.key}
            type="button"
            data-testid={`source-${option.key}`}
            className={source === option.key ? "active" : ""}
            aria-pressed={source === option.key}
            onClick={() => setSource(option.key)}
          >
            {option.label}{option.count !== null && <em>{option.count.toLocaleString()}</em>}
          </button>)}
      </nav>}
    />


    {source !== "onchain" && visiblePayable.length > 0 && <section className="catalog-section">
      <div className="catalog-heading"><div><p className="section-kicker"><Zap size={13} /> Pay per call · b402 Bazaar</p><h2 data-testid="payable-heading">{activeCat ? `Hireable ${activeCat.label} agents` : "Agents you can hire right now"}</h2></div><span data-testid="payable-result-count">{visiblePayable.length} services</span></div>
      <p className="payable-notice" data-testid="payable-notice"><ShieldAlert size={14} /><span><strong>You sign with your own wallet.</strong> Price, token and recipient are shown before anything is signed — settlement on BNB Chain.</span></p>
      <div className="onchain-grid" data-testid="payable-grid">{visiblePayable.map(r => <B402ResourceCard key={r.id} resource={r} />)}</div>
    </section>}

    {source !== "b402" && <section className="catalog-section">
      <div className="catalog-heading"><div><p className="section-kicker">Onchain identities · 8004scan</p><h2 data-testid="catalog-heading">{activeCat ? `${activeCat.label} agents` : "All onchain agents on BNB Chain"}</h2><p className="section-note" data-testid="onchain-hire-note">{activeCat ? activeCat.blurb + " Discovered from 8004scan by each agent's own onchain metadata." : "Discovered from 8004scan. Pick a category above to narrow to agents that do a specific job."}</p></div><span data-testid="agent-result-count">{loadError ? "Count unavailable" : <><strong data-testid="agent-ready-count">{readyTotal}</strong> ready to hire · {total.toLocaleString()}{totalCapped ? "+" : ""} registered</>}</span></div>
      <div className="filter-bar" data-testid="agent-filter-bar">
        <Select value={protocol} onValueChange={v => { setProtocol(v); setOffset(0); }}><SelectTrigger data-testid="protocol-filter"><SelectValue placeholder="Protocol" /></SelectTrigger><SelectContent><SelectItem data-testid="protocol-all" value="all">All protocols</SelectItem>{protocols.map(p => <SelectItem data-testid={`protocol-${p.toLowerCase()}`} value={p} key={p}>{p}</SelectItem>)}</SelectContent></Select>
        <Select value={sort} onValueChange={v => { setSort(v); setOffset(0); }}><SelectTrigger data-testid="sort-filter"><SelectValue /></SelectTrigger><SelectContent><SelectItem data-testid="sort-ready" value="ready">Ready to hire first</SelectItem><SelectItem data-testid="sort-score" value="score">8004scan score</SelectItem><SelectItem data-testid="sort-rank" value="rank">Network rank</SelectItem><SelectItem data-testid="sort-feedback" value="feedback">Feedback volume</SelectItem></SelectContent></Select>
        {selected.length > 0 && <Button data-testid="open-comparison-button" asChild className="compare-floating"><Link to="/compare">Compare {selected.length}/3 <ArrowRight size={15} /></Link></Button>}
      </div>
      {!loading && !loadError && onchain.length > 0 && readyTotal === 0 && <p className="ready-none" data-testid="no-ready-agents">
        No agent in this category has a callable endpoint yet. Every identity below is registered on BNB Chain, and AgentDock probed each one — the card says what its endpoint actually did.
      </p>}
      {loading
        ? <div className="onchain-grid" data-testid="agents-loading">{[1,2,3,4,5,6].map(x => <Skeleton className="h-72" key={x} />)}</div>
        : onchain.length
          ? <><div className="onchain-grid" data-testid="agent-grid">{onchain.map(agent => <OnchainAgentCard key={agent.id} agent={agent} network="mainnet" compare={{ selected: selected.includes(agent.id), toggle }} />)}</div>
            <Pagination total={total} offset={offset} limit={PAGE} onChange={setOffset} testId="onchain-pagination" /></>
          : loadError
            ? <div className="empty-state" data-testid="agents-load-error"><ShieldAlert size={28} /><h3>Could not load the catalogue</h3><p>{loadError}</p><Button onClick={() => setRetry(n => n + 1)} data-testid="agents-retry-button">Try again</Button></div>
            : <div className="empty-state" data-testid="agents-empty-state"><Search size={28} /><h3>No agents match</h3><p>{activeCat ? "No agents in this category match your search yet." : "Try a broader term, or clear the protocol filter."}</p></div>}
    </section>}

    {source === "b402" && visiblePayable.length === 0 && <section className="catalog-section">
      <div className="empty-state" data-testid="payable-empty-state">
        <Zap size={28} />
        <h3>No paid service matches</h3>
        <p>{activeCat ? `No b402 service does ${activeCat.label.toLowerCase()} yet. The onchain registry may still have agents for it.` : "Try a broader search term."}</p>
        <Button variant="outline" onClick={() => setSource("onchain")}>Browse onchain identities</Button>
      </div>
    </section>}
  </div>;
}
