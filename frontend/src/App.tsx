import "@/App.css";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Toaster } from "sonner";
import AppShell from "@/components/AppShell";
import MarketplacePage from "@/pages/MarketplacePage";
import ComparePage from "@/pages/ComparePage";
import TaskPage from "@/pages/TaskPage";
import OnchainPage from "@/pages/OnchainPage";
import MyAgentsPage from "@/pages/MyAgentsPage";
import OnchainDetailPage from "@/pages/OnchainDetailPage";
import RegisterAgentPage from "@/pages/RegisterAgentPage";
import HirePage from "@/pages/HirePage";

export default function App() {
  return <BrowserRouter><Routes><Route element={<AppShell />}><Route path="/" element={<MarketplacePage />} /><Route path="/onchain" element={<OnchainPage />} /><Route path="/onchain/:network/:tokenId" element={<OnchainDetailPage/>}/><Route path="/my-agents" element={<MyAgentsPage/>}/><Route path="/my-agents/new" element={<RegisterAgentPage/>}/><Route path="/compare" element={<ComparePage />} /><Route path="/hire/:resourceId" element={<HirePage />} /><Route path="/tasks/:taskId" element={<TaskPage />} /></Route></Routes><Toaster richColors position="top-right" /></BrowserRouter>;
}