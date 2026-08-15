import "@/App.css";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Toaster } from "sonner";
import AppShell from "@/components/AppShell";
import MarketplacePage from "@/pages/MarketplacePage";
import ComparePage from "@/pages/ComparePage";
import AgentPage from "@/pages/AgentPage";
import TaskPage from "@/pages/TaskPage";

export default function App() {
  return <BrowserRouter><Routes><Route element={<AppShell />}><Route path="/" element={<MarketplacePage />} /><Route path="/compare" element={<ComparePage />} /><Route path="/agents/:agentId" element={<AgentPage />} /><Route path="/tasks/:taskId" element={<TaskPage />} /></Route></Routes><Toaster richColors position="top-right" /></BrowserRouter>;
}