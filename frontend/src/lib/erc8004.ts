import type { Address } from "viem";

const mainnetRegistry = process.env.REACT_APP_ERC8004_MAINNET_REGISTRY as Address;
const testnetRegistry = process.env.REACT_APP_ERC8004_TESTNET_REGISTRY as Address;
const scanBase = process.env.REACT_APP_8004SCAN_URL;
if (!mainnetRegistry || !testnetRegistry || !scanBase) throw new Error("ERC-8004 network configuration is required");

export const ERC8004_NETWORKS = {
  mainnet: { label:"BSC Mainnet", chainId:56, registry:mainnetRegistry, explorer:"https://bscscan.com" },
  testnet: { label:"BSC Testnet", chainId:97, registry:testnetRegistry, explorer:"https://testnet.bscscan.com" },
} as const;

export type AgentMetadataInput = { name:string; description:string; image:string; serviceName:string; serviceEndpoint:string; serviceVersion:string; x402Support:boolean; active:boolean; supportedTrust:string };

export const identityAbi = [
  {type:"function",name:"register",stateMutability:"nonpayable",inputs:[{name:"agentURI",type:"string"}],outputs:[{type:"uint256"}]},
  {type:"function",name:"setAgentURI",stateMutability:"nonpayable",inputs:[{name:"agentId",type:"uint256"},{name:"newURI",type:"string"}],outputs:[]},
  {type:"function",name:"ownerOf",stateMutability:"view",inputs:[{name:"tokenId",type:"uint256"}],outputs:[{type:"address"}]},
  {type:"function",name:"tokenURI",stateMutability:"view",inputs:[{name:"tokenId",type:"uint256"}],outputs:[{type:"string"}]},
  {type:"event",name:"Registered",inputs:[{indexed:true,name:"agentId",type:"uint256"},{indexed:false,name:"agentURI",type:"string"},{indexed:true,name:"owner",type:"address"}]},
  {type:"event",name:"URIUpdated",inputs:[{indexed:true,name:"agentId",type:"uint256"},{indexed:false,name:"newURI",type:"string"},{indexed:true,name:"updatedBy",type:"address"}]},
] as const;

export const metadataToDataUri = (input:AgentMetadataInput) => {
  const registration = {
    type:"https://eips.ethereum.org/EIPS/eip-8004#registration-v1",
    name:input.name.trim(), description:input.description.trim(),
    ...(input.image.trim()?{image:input.image.trim()}:{}),
    services:[{name:input.serviceName,endpoint:input.serviceEndpoint.trim(),...(input.serviceVersion.trim()?{version:input.serviceVersion.trim()}: {})}],
    x402Support:input.x402Support, active:input.active,
    supportedTrust:input.supportedTrust.split(",").map(x=>x.trim()).filter(Boolean),
  };
  const json=JSON.stringify(registration); const bytes=new TextEncoder().encode(json);
  let binary=""; bytes.forEach(byte=>binary+=String.fromCharCode(byte));
  return { uri:`data:application/json;base64,${btoa(binary)}`, bytes:bytes.length, registration };
};

export const scanAgentUrl=(network:"mainnet"|"testnet",tokenId:number)=>`${scanBase}/agents/${network==="testnet"?"bsc-testnet":"bsc"}/${tokenId}`;
export const scanCreateUrl=()=>`${scanBase}/create`;