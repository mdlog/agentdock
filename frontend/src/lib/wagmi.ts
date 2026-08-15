import { createConfig, http } from "wagmi";
import { bscTestnet } from "wagmi/chains";
import { injected } from "wagmi/connectors";
import { getWagmiConnectorV2 } from "@binance/w3w-wagmi-connector-v2";

const rpcUrl = process.env.REACT_APP_BSC_RPC_URL;
if (!rpcUrl) throw new Error("REACT_APP_BSC_RPC_URL is required");
const binanceConnector = getWagmiConnectorV2();

export const wagmiConfig = createConfig({
  chains: [bscTestnet],
  connectors: [injected({ target: "metaMask" }), binanceConnector()],
  transports: { [bscTestnet.id]: http(rpcUrl) },
});