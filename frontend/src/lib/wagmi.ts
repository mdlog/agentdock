import { createConfig, http } from "wagmi";
import { bsc, bscTestnet } from "wagmi/chains";
import { injected } from "wagmi/connectors";
import { getWagmiConnectorV2 } from "@binance/w3w-wagmi-connector-v2";

const rpcUrl = process.env.REACT_APP_BSC_RPC_URL;
const mainnetRpcUrl = process.env.REACT_APP_BSC_MAINNET_RPC_URL;
if (!rpcUrl || !mainnetRpcUrl) throw new Error("BSC RPC URLs are required");
const binanceConnector = getWagmiConnectorV2();
const connectors: any[] = [injected({ target: "metaMask" })];
if (typeof window !== "undefined" && window.binancew3w?.ethereum) connectors.push(binanceConnector());

export const wagmiConfig = createConfig({
  chains: [bsc, bscTestnet],
  connectors,
  transports: { [bsc.id]:http(mainnetRpcUrl), [bscTestnet.id]: http(rpcUrl) },
});