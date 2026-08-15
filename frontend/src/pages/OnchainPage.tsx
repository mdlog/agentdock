import { useEffect, useMemo, useState } from "react";
import { Database, Search, ShieldQuestion } from "lucide-react";
import { api } from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { OnchainAgentCard, compactNumber } from "@/components/OnchainAgentCard";
import type { OnchainAgent } from "@/types";

type SyncStatus = { status:string; imported?:number; feedback_sample?:number; available_total?:number; sample_limit?:number; completed_at?:string; rate_limit?:{limit?:string;remaining?:string}; error?:string };

export default function OnchainPage() {
  const [agents,setAgents] = useState<OnchainAgent[]>([]); const [status,setStatus] = useState<SyncStatus>({status:"loading"}); const [loading,setLoading] = useState(true);
  const [loadError,setLoadError] = useState("");
  const [network,setNetwork] = useState<"mainnet"|"testnet">("mainnet");
  const [search,setSearch] = useState(""); const [protocol,setProtocol] = useState("all"); const [x402,setX402] = useState("all"); const [sort,setSort] = useState("score");
  useEffect(()=>{
    let active=true; let timer:ReturnType<typeof setTimeout>;
    setLoading(true);
    const load=async()=>{ try { const [a,s]=await Promise.all([api.get(`/onchain/agents?network=${network}`),api.get(`/integrations/8004scan/status?network=${network}`)]); if(!active)return; setAgents(a.data.items); setStatus(s.data); setLoadError(""); setLoading(false); if(["loading","running","never_run"].includes(s.data.status)) timer=setTimeout(load,2000); } catch { if(active){setLoadError("Live registry data is temporarily unavailable.");setLoading(false);} } };
    load(); return()=>{active=false;clearTimeout(timer)};
  },[network]);
  const protocols=useMemo(()=>Array.from(new Set(agents.flatMap(a=>a.supported_protocols))).sort(),[agents]);
  const visible=useMemo(()=>agents.filter(a=>(protocol==="all"||a.supported_protocols.includes(protocol))&&(x402==="all"||a.x402_supported===(x402==="yes"))&&`${a.name} ${a.description}`.toLowerCase().includes(search.toLowerCase())).sort((a,b)=>sort==="rank"?(a.rank??999999)-(b.rank??999999):sort==="feedback"?b.total_feedbacks-a.total_feedbacks:(b.total_score??-1)-(a.total_score??-1)),[agents,search,protocol,x402,sort]);
  const changeNetwork=(value:string)=>{setNetwork(value as "mainnet"|"testnet");setSearch("");setProtocol("all");setX402("all");setSort("score")};
  return <div className="page-wrap onchain-page">
    <section className="onchain-heading"><div><p className="section-kicker"><Database size={14}/> Live registry data</p><h1 data-testid="onchain-heading">BSC {network === "testnet" ? "Testnet" : "Mainnet"} agents,<br/>direct from 8004scan.</h1><p data-testid="onchain-subheading">Identity, metadata, protocol, x402, score, and feedback observations are preserved as supplied—not treated as measured AgentDock performance.</p></div><div className="sync-panel" data-testid="scan-sync-status"><span className={`sync-dot ${status.status}`}/><div><strong>{status.status === "success" ? "Synchronized" : status.status}</strong><small>{status.imported ?? 0} agents · {status.feedback_sample ?? 0} feedbacks</small></div><Badge>{compactNumber(status.available_total)} available</Badge></div></section>
    <div className="onchain-note" data-testid="onchain-source-note"><ShieldQuestion size={17}/><span>Viewing BSC {network === "testnet" ? "Testnet" : "Mainnet"} source records. Mainnet identity discovery does not enable production payments.</span></div>
    <div className="onchain-tools expanded"><div className="onchain-search"><Search size={17}/><Input data-testid="onchain-search-input" value={search} onChange={e=>setSearch(e.target.value)} placeholder="Search live agent names or descriptions"/></div><Select value={network} onValueChange={changeNetwork}><SelectTrigger data-testid="onchain-network-filter"><SelectValue/></SelectTrigger><SelectContent><SelectItem data-testid="network-mainnet-option" value="mainnet">BSC Mainnet</SelectItem><SelectItem data-testid="network-testnet-option" value="testnet">BSC Testnet</SelectItem></SelectContent></Select><Select value={protocol} onValueChange={setProtocol}><SelectTrigger data-testid="onchain-protocol-filter"><SelectValue/></SelectTrigger><SelectContent><SelectItem data-testid="protocol-all-option" value="all">All protocols</SelectItem>{protocols.map(p=><SelectItem data-testid={`protocol-${p.toLowerCase()}-option`} value={p} key={p}>{p}</SelectItem>)}</SelectContent></Select><Select value={x402} onValueChange={setX402}><SelectTrigger data-testid="onchain-x402-filter"><SelectValue/></SelectTrigger><SelectContent><SelectItem data-testid="x402-all-option" value="all">Any payment support</SelectItem><SelectItem data-testid="x402-yes-option" value="yes">x402 claimed</SelectItem><SelectItem data-testid="x402-no-option" value="no">No x402 claim</SelectItem></SelectContent></Select><Select value={sort} onValueChange={setSort}><SelectTrigger data-testid="onchain-sort-filter"><SelectValue/></SelectTrigger><SelectContent><SelectItem data-testid="sort-score-option" value="score">8004scan score</SelectItem><SelectItem data-testid="sort-rank-option" value="rank">Network rank</SelectItem><SelectItem data-testid="sort-feedback-option" value="feedback">Feedback volume</SelectItem></SelectContent></Select></div>
    <div className="onchain-count"><span data-testid="onchain-result-count">{visible.length} synchronized agents</span><span>Updated {status.completed_at ? new Date(status.completed_at).toLocaleString() : "pending"}</span></div>
    {loadError&&<div className="integration-notice" data-testid="onchain-load-error"><ShieldQuestion size={17}/><strong>{loadError}</strong></div>}
    {loading?<div className="onchain-grid">{[1,2,3,4,5,6].map(x=><Skeleton className="h-72" key={x}/>)}</div>:<div className="onchain-grid" data-testid="onchain-agent-grid">{visible.map(agent=><OnchainAgentCard key={agent.id} agent={agent} network={network}/>)}</div>}
  </div>;
}
