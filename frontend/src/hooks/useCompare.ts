import { useEffect, useState } from "react";
import { toast } from "sonner";

// Onchain ids are minted as `bsc-<chainId>-<tokenId>` by the backend projection;
// seed catalog ids are slugs. The two kinds expose different columns, so a
// comparison holds one kind at a time.
export type CompareKind = "onchain" | "demo";
export const compareKind = (id: string): CompareKind => (id.startsWith("bsc-") ? "onchain" : "demo");

const read = (): string[] => {
  try {
    const stored = JSON.parse(localStorage.getItem("agentdock-compare") || "[]");
    return Array.isArray(stored) ? stored.filter((x): x is string => typeof x === "string") : [];
  } catch {
    return [];
  }
};

export const useCompare = () => {
  const [selected, setSelected] = useState<string[]>(read);
  useEffect(() => localStorage.setItem("agentdock-compare", JSON.stringify(selected)), [selected]);
  const toggle = (id: string) => setSelected(current => {
    if (current.includes(id)) return current.filter(x => x !== id);
    if (current.length && compareKind(current[0]) !== compareKind(id)) {
      toast.error("Compare onchain agents with onchain agents, or demo agents with demo agents.");
      return current;
    }
    if (current.length >= 3) { toast.error("You can compare up to three agents."); return current; }
    return [...current, id];
  });
  return { selected, toggle, clear: () => setSelected([]) };
};
