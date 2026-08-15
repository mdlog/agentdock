import { useEffect, useState } from "react";
import { toast } from "sonner";

// Onchain ids are minted as `bsc-<chainId>-<tokenId>` by the backend projection.
// Anything else in storage predates the seed catalog being removed and is dropped
// on read so a stale selection cannot resolve to a missing agent.
const isOnchainId = (id: unknown): id is string => typeof id === "string" && id.startsWith("bsc-");

const read = (): string[] => {
  try {
    const stored = JSON.parse(localStorage.getItem("agentdock-compare") || "[]");
    return Array.isArray(stored) ? stored.filter(isOnchainId) : [];
  } catch {
    return [];
  }
};

export const useCompare = () => {
  const [selected, setSelected] = useState<string[]>(read);
  useEffect(() => localStorage.setItem("agentdock-compare", JSON.stringify(selected)), [selected]);
  const toggle = (id: string) => setSelected(current => {
    if (current.includes(id)) return current.filter(x => x !== id);
    if (current.length >= 3) { toast.error("You can compare up to three agents."); return current; }
    return [...current, id];
  });
  return { selected, toggle, clear: () => setSelected([]) };
};
