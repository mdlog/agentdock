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

export const CategoryBrowse = ({ categories, selected, onSelect, leading }: {
  categories: AgentCategory[];
  selected: string | null;
  onSelect: (key: string | null) => void;
  // Rendered at the head of the same row as the chips: choosing a registry and
  // choosing a job are one decision made in two parts, so they read as one
  // control rather than two stacked blocks.
  leading?: React.ReactNode;
}) => (
  <section className="category-browse" data-testid="category-browse">
    <div className="category-browse-head">
      <div><p className="section-kicker"><Layers size={13} /> Browse by category</p><h2 data-testid="category-heading">What should the agent do?</h2></div>
      {selected && <button className="category-clear" data-testid="category-clear" onClick={() => onSelect(null)}>Show all agents</button>}
    </div>
    <div className="category-grid" data-testid="category-grid">
      {leading}
      <div className="category-chips">
      {categories.map(cat => {
        const Icon = ICONS[cat.key] ?? Layers;
        const active = selected === cat.key;
        // The registration count sets an expectation; this is the number that
        // says whether a visitor can actually do anything in this category.
        const hireable = (cat.ready ?? 0) + (cat.payable ?? 0);
        return (
          <button
            key={cat.key}
            data-testid={`category-card-${cat.key}`}
            className={`category-card${active ? " active" : ""}`}
            aria-pressed={active}
            onClick={() => onSelect(active ? null : cat.key)}
          >
            <span className="category-icon"><Icon size={14} /></span>
            <strong>{cat.label}</strong>
            {/* The count that predicts whether a visitor can do anything here.
                The registration total and the blurb both reappear the moment a
                category is picked, in the section heading below. */}
            <span className="category-ready" data-testid={`category-ready-${cat.key}`}>
              {hireable > 0
                ? <b>{hireable}</b>
                : <em>0</em>}
            </span>
            <span className="category-count" data-testid={`category-count-${cat.key}`}>/ {cat.count.toLocaleString()}</span>
          </button>
        );
      })}
      </div>
    </div>
  </section>
);
