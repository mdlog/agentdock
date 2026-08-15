import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { WagmiProvider } from "wagmi";
import "@/index.css";
import App from "@/App";
import { wagmiConfig } from "@/lib/wagmi";

const root = ReactDOM.createRoot(document.getElementById("root")!);
root.render(<React.StrictMode><WagmiProvider config={wagmiConfig}><QueryClientProvider client={new QueryClient()}><App /></QueryClientProvider></WagmiProvider></React.StrictMode>);