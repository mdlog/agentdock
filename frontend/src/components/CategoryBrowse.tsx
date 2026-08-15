import { Layers, RefreshCw, Grid3x3, TrendingUp, HeartPulse } from "lucide-react";
import type { AgentCategory } from "@/types";

// The four judged agent categories, browsable as first-class entry points. This
// is the "find an agent by category" journey the marketplace is scored on. Icons
// are keyed to the taxonomy so the mapping is fixed, not guessed at render time.
const ICONS: Record<string, typeof Layers> = {
  "rebalancing": RefreshCw,
  "grid-trading": Grid3x3,
  "yield-optimisation": TrendingUp,
  "health-factor": HeartPulse,
};

export const CategoryBrowse = ({ categories, selected, onSelect }: {
  categories: AgentCategory[];
  selected: string | null;
  onSelect: (key: string | null) => void;
}) => (
  <section className="category-browse" data-testid="category-browse">
    <div className="category-browse-head">
      <div><p className="section-kicker"><Layers size={13} /> Browse by category</p><h2 data-testid="category-heading">What should the agent do?</h2></div>
      {selected && <button className="category-clear" data-testid="category-clear" onClick={() => onSelect(null)}>Show all agents</button>}
    </div>
    <div className="category-grid" data-testid="category-grid">
      {categories.map(cat => {
        const Icon = ICONS[cat.key] ?? Layers;
        const active = selected === cat.key;
        return (
          <button
            key={cat.key}
            data-testid={`category-card-${cat.key}`}
            className={`category-card${active ? " active" : ""}`}
            aria-pressed={active}
            onClick={() => onSelect(active ? null : cat.key)}
          >
            <span className="category-top">
              <span className="category-icon"><Icon size={15} /></span>
              <strong>{cat.label}</strong>
              <span className="category-count" data-testid={`category-count-${cat.key}`}>{cat.count.toLocaleString()}</span>
            </span>
            <p>{cat.blurb}</p>
          </button>
        );
      })}
    </div>
  </section>
);
