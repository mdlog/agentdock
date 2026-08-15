import { useEffect, useMemo, useState } from "react";
import { Activity, BadgeCheck, Database, ExternalLink, Search, ShieldQuestion, Zap } from "lucide-react";
import { api } from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";

type LiveAgent = { id:string; token_id:number; name:string; description:string; image_url?:string; owner_address?:string; contract_address?:string; supported_protocols:string[]; x402_supported:boolean; is_verified:boolean; total_score?:number; rank?:number; health_score?:number; total_feedbacks:number; average_score?:number; source_label:string; synced_at:string };
type SyncStatus = { status:string; imported?:number; available_total?:number; sample_limit?:number; completed_at?:string; rate_limit?:{limit?:string;remaining?:string}; error?:string };

const compact = (value?:number) => typeof value === "number" ? Intl.NumberFormat("en", { notation:"compact", maximumFractionDigits:1 }).format(value) : "—";

export default function OnchainPage() {
  const [agents,setAgents] = useState<LiveAgent[]>([]); const [status,setStatus] = useState<SyncStatus>({status:"loading"}); const [loading,setLoading] = useState(true);
  const [loadError,setLoadError] = useState("");
  const [search,setSearch] = useState(""); const [protocol,setProtocol] = useState("all"); const [x402,setX402] = useState("all"); const [sort,setSort] = useState("score");
  useEffect(()=>{
    let active=true; let timer:ReturnType<typeof setTimeout>;
    const load=async()=>{ try { const [a,s]=await Promise.all([api.get("/onchain/agents"),api.get("/integrations/8004scan/status")]); if(!active)return; setAgents(a.data.items); setStatus(s.data); setLoadError(""); setLoading(false); if(["loading","running","never_run"].includes(s.data.status)) timer=setTimeout(load,2000); } catch { if(active){setLoadError("Live registry data is temporarily unavailable.");setLoading(false);} } };
    load(); return()=>{active=false;clearTimeout(timer)};
  },[]);
  const protocols=useMemo(()=>Array.from(new Set(agents.flatMap(a=>a.supported_protocols))).sort(),[agents]);
  const visible=useMemo(()=>agents.filter(a=>(protocol==="all"||a.supported_protocols.includes(protocol))&&(x402==="all"||a.x402_supported===(x402==="yes"))&&`${a.name} ${a.description}`.toLowerCase().includes(search.toLowerCase())).sort((a,b)=>sort==="rank"?(a.rank??999999)-(b.rank??999999):sort==="feedback"?b.total_feedbacks-a.total_feedbacks:(b.total_score??-1)-(a.total_score??-1)),[agents,search,protocol,x402,sort]);
  return <div className="page-wrap onchain-page">
    <section className="onchain-heading"><div><p className="section-kicker"><Database size={14}/> Live registry data</p><h1 data-testid="onchain-heading">BSC Mainnet agents,<br/>direct from 8004scan.</h1><p data-testid="onchain-subheading">Source observations are shown as supplied. Scores, claims, and x402 support are not treated as measured AgentDock performance.</p></div><div className="sync-panel" data-testid="scan-sync-status"><span className={`sync-dot ${status.status}`}/><div><strong>{status.status === "success" ? "Synchronized" : status.status}</strong><small>{status.imported ?? 0} sampled · {compact(status.available_total)} available</small></div><Badge>{status.rate_limit?.limit ? `${status.rate_limit.limit} req/min` : "API connected"}</Badge></div></section>
    <div className="onchain-note" data-testid="onchain-source-note"><ShieldQuestion size={17}/><span>This view is BSC Mainnet identity discovery. AgentDock payments remain on BSC Testnet until settlement safety is proven.</span></div>
    <div className="onchain-tools"><div className="onchain-search"><Search size={17}/><Input data-testid="onchain-search-input" value={search} onChange={e=>setSearch(e.target.value)} placeholder="Search live agent names or descriptions"/></div><Select value={protocol} onValueChange={setProtocol}><SelectTrigger data-testid="onchain-protocol-filter"><SelectValue/></SelectTrigger><SelectContent><SelectItem value="all">All protocols</SelectItem>{protocols.map(p=><SelectItem value={p} key={p}>{p}</SelectItem>)}</SelectContent></Select><Select value={x402} onValueChange={setX402}><SelectTrigger data-testid="onchain-x402-filter"><SelectValue/></SelectTrigger><SelectContent><SelectItem value="all">Any payment support</SelectItem><SelectItem value="yes">x402 claimed</SelectItem><SelectItem value="no">No x402 claim</SelectItem></SelectContent></Select><Select value={sort} onValueChange={setSort}><SelectTrigger data-testid="onchain-sort-filter"><SelectValue/></SelectTrigger><SelectContent><SelectItem value="score">8004scan score</SelectItem><SelectItem value="rank">Network rank</SelectItem><SelectItem value="feedback">Feedback volume</SelectItem></SelectContent></Select></div>
    <div className="onchain-count"><span data-testid="onchain-result-count">{visible.length} synchronized agents</span><span>Updated {status.completed_at ? new Date(status.completed_at).toLocaleString() : "pending"}</span></div>
    {loadError&&<div className="integration-notice" data-testid="onchain-load-error"><ShieldQuestion size={17}/><strong>{loadError}</strong></div>}
    {loading?<div className="onchain-grid">{[1,2,3,4,5,6].map(x=><Skeleton className="h-72" key={x}/>)}</div>:<div className="onchain-grid" data-testid="onchain-agent-grid">{visible.map(agent=><article className="onchain-card" data-testid={`onchain-agent-${agent.token_id}`} key={agent.id}>
      <div className="onchain-card-top"><div className="agent-avatar" data-testid={`onchain-avatar-${agent.token_id}`}>{agent.name.slice(0,2).toUpperCase()}</div><div><div className="onchain-name"><h2 data-testid={`onchain-name-${agent.token_id}`}>{agent.name}</h2>{agent.is_verified&&<BadgeCheck size={15}/>}</div><span data-testid={`onchain-id-${agent.token_id}`}>ERC-8004 #{agent.token_id}</span></div>{agent.x402_supported&&<Badge data-testid={`onchain-x402-${agent.token_id}`} className="x402-badge"><Zap size={10}/> x402 claim</Badge>}</div>
      <p data-testid={`onchain-description-${agent.token_id}`}>{agent.description}</p><div className="protocol-list" data-testid={`onchain-protocols-${agent.token_id}`}>{agent.supported_protocols.length?agent.supported_protocols.map(p=><span key={p}>{p}</span>):<span>No protocol declared</span>}</div>
      <div className="onchain-metrics"><div><strong>{agent.total_score ?? "—"}</strong><span>8004scan score</span></div><div><strong>{agent.rank ? `#${agent.rank}` : "—"}</strong><span>Network rank</span></div><div><strong>{compact(agent.total_feedbacks)}</strong><span>Feedbacks</span></div></div>
      <div className="onchain-footer"><span><Activity size={12}/>{agent.source_label}</span>{agent.contract_address&&<a data-testid={`onchain-contract-${agent.token_id}`} href={`https://bscscan.com/address/${agent.contract_address}`} target="_blank" rel="noreferrer" aria-label="View contract on BscScan"><ExternalLink size={14}/></a>}</div>
    </article>)}</div>}
  </div>;
}