import { useEffect, useState } from "react";
import { toast } from "sonner";

export const useCompare = () => {
  const [selected, setSelected] = useState<string[]>(() => JSON.parse(localStorage.getItem("agentdock-compare") || "[]"));
  useEffect(() => localStorage.setItem("agentdock-compare", JSON.stringify(selected)), [selected]);
  const toggle = (id: string) => setSelected(current => {
    if (current.includes(id)) return current.filter(x => x !== id);
    if (current.length >= 3) { toast.error("You can compare up to three agents."); return current; }
    return [...current, id];
  });
  return { selected, toggle, clear: () => setSelected([]) };
};