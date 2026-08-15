import { createConfig, http } from "wagmi";
import { bsc, bscTestnet } from "wagmi/chains";
import { getWagmiConnectorV2 } from "@binance/w3w-wagmi-connector-v2";

const rpcUrl = process.env.REACT_APP_BSC_RPC_URL;
const mainnetRpcUrl = process.env.REACT_APP_BSC_MAINNET_RPC_URL;
if (!rpcUrl || !mainnetRpcUrl) throw new Error("BSC RPC URLs are required");

// Browser wallets are discovered over EIP-6963 by wagmi itself
// (`multiInjectedProviderDiscovery` defaults to true), so none is listed here.
//
// Do not reintroduce `injected({ target: "metaMask" })`. That target rejects any
// window.ethereum carrying a competitor flag — isRabby, isPhantom, isOkxWallet
// and a dozen more — so on any machine where another extension owns
// window.ethereum it resolves no provider and throws ProviderNotFoundError.
// It cannot be deduped away either: injected() targets carry no `rdns`, so wagmi
// keeps it alongside the genuine discovered MetaMask as a second, broken entry.
const binanceConnector = getWagmiConnectorV2();
const connectors: any[] = [];
if (typeof window !== "undefined" && window.binancew3w?.ethereum) connectors.push(binanceConnector());

export const wagmiConfig = createConfig({
  chains: [bsc, bscTestnet],
  connectors,
  transports: { [bsc.id]: http(mainnetRpcUrl), [bscTestnet.id]: http(rpcUrl) },
});
