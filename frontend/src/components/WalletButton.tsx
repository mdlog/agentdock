import { LogOut, Wallet } from "lucide-react";
import { useAccount, useConnect, useDisconnect, useSwitchChain } from "wagmi";
import { toast } from "sonner";
import { DEFAULT_CHAIN } from "@/lib/erc8004";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";

export const WalletButton = () => {
  const { address, chainId } = useAccount();
  const { connectors, connect, isPending } = useConnect();
  const { disconnect } = useDisconnect();
  const { switchChain } = useSwitchChain();
  const short = address ? `${address.slice(0, 6)}…${address.slice(-4)}` : "Connect wallet";
  const hasBinanceConnector = connectors.some(connector => connector.name.toLowerCase().includes("binance"));
  const binanceWalletUrl = process.env.REACT_APP_BINANCE_WALLET_URL;

  if (address) return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild><Button data-testid="connected-wallet-menu" variant="outline" className="wallet-button"><span className="wallet-dot" />{short}</Button></DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {chainId !== DEFAULT_CHAIN.chainId && <DropdownMenuItem data-testid="switch-default-chain" onClick={() => switchChain({ chainId: DEFAULT_CHAIN.chainId })}>Switch to {DEFAULT_CHAIN.label}</DropdownMenuItem>}
        <DropdownMenuItem data-testid="disconnect-wallet" onClick={() => disconnect()}><LogOut size={15} /> Disconnect</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild><Button data-testid="connect-wallet-button" disabled={isPending}><Wallet size={16} />{short}</Button></DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        {connectors.map((connector, index) => (
          <DropdownMenuItem data-testid={`wallet-option-${index}`} key={`${connector.uid}-${index}`} onClick={() => connect({ connector }, { onError: (e) => toast.error(e.message) })}>{connector.name}</DropdownMenuItem>
        ))}
        {!hasBinanceConnector && binanceWalletUrl && <DropdownMenuItem data-testid="wallet-option-binance-install" onClick={() => window.open(binanceWalletUrl, "_blank", "noopener,noreferrer")}>Binance Wallet · Install extension</DropdownMenuItem>}
      </DropdownMenuContent>
    </DropdownMenu>
  );
};