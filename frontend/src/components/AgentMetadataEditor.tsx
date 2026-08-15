import { useMemo, useState } from "react";
import { AlertTriangle, CheckCircle2, ExternalLink, FileJson, PenLine, ShieldCheck } from "lucide-react";
import { useAccount, useChainId, useReadContract, useSimulateContract, useSwitchChain, useWaitForTransactionReceipt, useWriteContract } from "wagmi";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { WalletButton } from "@/components/WalletButton";
import { AgentMetadataInput, ERC8004_NETWORKS, identityAbi, metadataToDataUri } from "@/lib/erc8004";

const defaults:AgentMetadataInput={name:"",description:"",image:"",serviceName:"Web",serviceEndpoint:"",serviceVersion:"1.0.0",x402Support:false,active:true,supportedTrust:"reputation"};

export const AgentMetadataEditor=({mode,network,tokenId,initial}:{mode:"register"|"edit";network:"mainnet"|"testnet";tokenId?:number;initial?:Partial<AgentMetadataInput>})=>{
  const target=ERC8004_NETWORKS[network]; const {address}=useAccount(); const chainId=useChainId(); const {switchChain}=useSwitchChain();
  const [form,setForm]=useState<AgentMetadataInput>({...defaults,...initial}); const [mainnetConfirmed,setMainnetConfirmed]=useState(false);
  const payload=useMemo(()=>metadataToDataUri(form),[form]); const endpointValid=/^https:\/\//i.test(form.serviceEndpoint); const imageValid=!form.image||/^https:\/\//i.test(form.image);
  const valid=form.name.trim().length>=2&&form.description.trim().length>=12&&endpointValid&&imageValid&&payload.bytes<=3500;
  const owner=useReadContract({address:target.registry,abi:identityAbi,functionName:"ownerOf",args:[BigInt(tokenId||0)],chainId:target.chainId,query:{enabled:mode==="edit"&&!!address&&tokenId!==undefined}});
  const isOwner=mode==="register"||String(owner.data||"").toLowerCase()===address?.toLowerCase();
  const functionName=mode==="register"?"register":"setAgentURI"; const args=mode==="register"?[payload.uri]:[BigInt(tokenId||0),payload.uri];
  const enabled=!!address&&chainId===target.chainId&&valid&&isOwner&&(network!=="mainnet"||mainnetConfirmed);
  const simulation=useSimulateContract({address:target.registry,abi:identityAbi,functionName,args,chainId:target.chainId,query:{enabled}} as any);
  const write=useWriteContract(); const receipt=useWaitForTransactionReceipt({hash:write.data,chainId:target.chainId});
  const update=(key:keyof AgentMetadataInput,value:string|boolean)=>setForm(current=>({...current,[key]:value}));
  return <section className="metadata-editor" data-testid={`${mode}-metadata-editor`}>
    <div className="editor-heading"><div><span><PenLine size={14}/>{mode==="register"?"New identity":"Update registration"}</span><h2>{mode==="register"?"Publish agent metadata":"Edit agent metadata"}</h2></div><strong>{target.label}</strong></div>
    <div className="metadata-grid"><label>Name<Input data-testid="metadata-name-input" value={form.name} onChange={e=>update("name",e.target.value)} placeholder="Agent name"/></label><label>Image URL<Input data-testid="metadata-image-input" value={form.image} onChange={e=>update("image",e.target.value)} placeholder="https://..."/></label><label className="full">Description<Textarea data-testid="metadata-description-input" value={form.description} onChange={e=>update("description",e.target.value)} rows={4}/></label><label>Service protocol<Select value={form.serviceName} onValueChange={v=>update("serviceName",v)}><SelectTrigger data-testid="metadata-service-select"><SelectValue/></SelectTrigger><SelectContent><SelectItem value="Web">Web</SelectItem><SelectItem value="A2A">A2A</SelectItem><SelectItem value="MCP">MCP</SelectItem></SelectContent></Select></label><label>Version<Input data-testid="metadata-version-input" value={form.serviceVersion} onChange={e=>update("serviceVersion",e.target.value)}/></label><label className="full">Service endpoint<Input data-testid="metadata-endpoint-input" value={form.serviceEndpoint} onChange={e=>update("serviceEndpoint",e.target.value)} placeholder="https://agent.example/api"/></label><label className="full">Supported trust models<Input data-testid="metadata-trust-input" value={form.supportedTrust} onChange={e=>update("supportedTrust",e.target.value)} placeholder="reputation, validation"/></label></div>
    <div className="metadata-toggles"><label><input data-testid="metadata-active-checkbox" type="checkbox" checked={form.active} onChange={e=>update("active",e.target.checked)}/> Active agent</label><label><input data-testid="metadata-x402-checkbox" type="checkbox" checked={form.x402Support} onChange={e=>update("x402Support",e.target.checked)}/> Declares x402 support</label></div>
    <div className="write-preview" data-testid="metadata-transaction-preview"><h3><FileJson size={15}/> Transaction preview</h3><div><span>Network</span><strong>{target.label} · {target.chainId}</strong></div><div><span>Registry</span><strong>{target.registry.slice(0,8)}…{target.registry.slice(-6)}</strong></div><div><span>Function</span><strong>{functionName}</strong></div><div><span>Metadata size</span><strong className={payload.bytes>3500?"danger":""}>{payload.bytes} / 3,500 bytes</strong></div><div><span>Permissions</span><strong>No token approval</strong></div></div>
    {!endpointValid&&form.serviceEndpoint&&<p className="form-warning" data-testid="endpoint-validation-warning"><AlertTriangle size={14}/> Service endpoint must use HTTPS.</p>}
    {network==="mainnet"&&<label className="mainnet-confirm"><input data-testid="mainnet-confirm-checkbox" type="checkbox" checked={mainnetConfirmed} onChange={e=>setMainnetConfirmed(e.target.checked)}/> I understand this writes permanent metadata to BSC Mainnet and costs real BNB gas.</label>}
    {mode==="edit"&&address&&!owner.isLoading&&!isOwner&&<p className="form-warning" data-testid="not-owner-warning"><AlertTriangle size={14}/> Connected wallet is not the onchain owner.</p>}
    {!address?<WalletButton/>:chainId!==target.chainId?<Button data-testid="switch-write-network-button" onClick={()=>switchChain({chainId:target.chainId})}>Switch to {target.label}</Button>:<Button data-testid="submit-metadata-transaction" disabled={!simulation.data?.request||write.isPending||receipt.isLoading} onClick={()=>simulation.data?.request&&write.writeContract(simulation.data.request as any)}>{write.isPending?"Confirm in wallet…":receipt.isLoading?"Confirming onchain…":mode==="register"?"Review & register":"Review & update"}</Button>}
    {simulation.error&&enabled&&<p className="form-warning" data-testid="simulation-error"><AlertTriangle size={14}/> Transaction simulation failed. Verify ownership, gas, and registry metadata.</p>}
    {receipt.isSuccess&&write.data&&<div className="write-success" data-testid="metadata-write-success"><CheckCircle2 size={18}/><div><strong>Onchain confirmation received</strong><a href={`${target.explorer}/tx/${write.data}`} target="_blank" rel="noreferrer">View transaction <ExternalLink size={13}/></a></div></div>}
    <p className="editor-safety"><ShieldCheck size={13}/> Your wallet signs directly. AgentDock never receives your private key.</p>
  </section>;
};