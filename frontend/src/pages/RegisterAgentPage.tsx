import { useState } from "react";
import { ArrowLeft, ExternalLink } from "lucide-react";
import { Link } from "react-router-dom";
import { AgentMetadataEditor } from "@/components/AgentMetadataEditor";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { scanCreateUrl } from "@/lib/erc8004";

export default function RegisterAgentPage(){
  const [network,setNetwork]=useState<"mainnet"|"testnet">("testnet");
  return <div className="page-wrap register-page"><Link to="/my-agents" className="back-link" data-testid="back-my-agents"><ArrowLeft size={15}/> My Agents</Link><div className="page-heading"><div><p className="section-kicker">ERC-8004 onboarding</p><h1 data-testid="register-agent-heading">Register an agent</h1><p data-testid="register-agent-subheading">Create a portable identity using an embedded registration JSON. Start on Testnet before Mainnet.</p></div><Select value={network} onValueChange={(v:any)=>setNetwork(v)}><SelectTrigger data-testid="register-network-select" className="w-48"><SelectValue/></SelectTrigger><SelectContent><SelectItem value="testnet">BSC Testnet</SelectItem><SelectItem value="mainnet">BSC Mainnet</SelectItem></SelectContent></Select></div><AgentMetadataEditor mode="register" network={network}/><a className="scan-manage-link" data-testid="register-on-8004scan-link" href={scanCreateUrl()} target="_blank" rel="noreferrer">Prefer the 8004scan builder? Open Create Agent <ExternalLink size={13}/></a></div>;
}