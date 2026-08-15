import { createConfig, http } from "wagmi";
import { bscTestnet } from "wagmi/chains";
import { injected } from "wagmi/connectors";
import { getWagmiConnectorV2 } from "@binance/w3w-wagmi-connector-v2";

const rpcUrl = process.env.REACT_APP_BSC_RPC_URL;
if (!rpcUrl) throw new Error("REACT_APP_BSC_RPC_URL is required");
const binanceConnector = getWagmiConnectorV2();
const connectors: any[] = [injected({ target: "metaMask" })];
if (typeof window !== "undefined" && window.binancew3w?.ethereum) connectors.push(binanceConnector());

export const wagmiConfig = createConfig({
  chains: [bscTestnet],
  connectors,
  transports: { [bscTestnet.id]: http(rpcUrl) },
});