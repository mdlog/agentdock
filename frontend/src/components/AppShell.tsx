import { Bot, Database, GitCompareArrows, Search, UserRound } from "lucide-react";
import { Link, NavLink, Outlet } from "react-router-dom";
import { WalletButton } from "./WalletButton";

export default function AppShell() {
  return <div className="app-shell">
    <header className="topbar" data-testid="app-header">
      <Link to="/" className="brand" data-testid="brand-home-link"><span className="brand-mark"><Bot size={20} /></span><span>AgentDock</span><em>BSC</em></Link>
      <nav className="main-nav" data-testid="main-navigation">
        <NavLink to="/" end data-testid="nav-marketplace"><Search size={15} /> Marketplace</NavLink>
        <NavLink to="/onchain" data-testid="nav-onchain"><Database size={15} /> Onchain</NavLink>
        <NavLink to="/my-agents" data-testid="nav-my-agents"><UserRound size={15}/> My Agents</NavLink>
        <NavLink to="/compare" data-testid="nav-compare"><GitCompareArrows size={15} /> Compare</NavLink>
      </nav>
      <WalletButton />
    </header>
    <main><Outlet /></main>
    <footer className="footer" data-testid="app-footer"><span>AgentDock · Research agents on BSC Testnet</span><span>Agents recommend. You approve every financial action.</span></footer>
  </div>;
}