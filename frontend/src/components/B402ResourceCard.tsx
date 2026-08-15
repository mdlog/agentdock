import { ArrowUpRight, Globe2, Zap } from "lucide-react";
import { Link } from "react-router-dom";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { AgentAvatar } from "@/components/AgentAvatar";
import type { B402Resource } from "@/types";

// A listing from Binance's b402 Bazaar: an endpoint that actually accepts
// payment on BNB Chain. Unlike the 8004scan identities these can be hired, so
// the price is deliberately left blank here — it is quoted by the merchant at
// run time and shown before anything is signed.
export const B402ResourceCard = ({ resource }: { resource: B402Resource }) => (
  <article className="onchain-card" data-testid={`b402-resource-${resource.id}`}>
    <div className="onchain-card-top">
      <AgentAvatar name={resource.resource} testId={`b402-avatar-${resource.id}`} />
      <div>
        <div className="onchain-name"><h2 data-testid={`b402-host-${resource.id}`}>{resource.host}</h2></div>
        <span>{new URL(resource.resource).pathname.slice(0, 46)}</span>
      </div>
      <Badge className="x402-badge"><Zap size={10} /> x402</Badge>
    </div>

    <p data-testid={`b402-description-${resource.id}`}>{resource.description}</p>
    <div className="protocol-list">
      <span>{resource.type?.toUpperCase() || "HTTP"}</span>
      <span>x402 v{resource.x402_version}</span>
      <span>BNB Chain</span>
    </div>

    <div className="onchain-hire-row">
      <div>
        <strong data-testid={`b402-price-${resource.id}`}>Quoted at run time</strong>
        <span>Price per call</span>
      </div>
      <div className="card-actions">
        <Button data-testid={`hire-b402-${resource.id}`} size="sm" asChild>
          <Link to={`/hire/${resource.id}`}>Hire <ArrowUpRight size={14} /></Link>
        </Button>
      </div>
    </div>

    <div className="onchain-footer">
      <span><Globe2 size={12} />{resource.source_label}</span>
      <div>
        <a href={resource.resource} target="_blank" rel="noreferrer" data-testid={`b402-endpoint-${resource.id}`}>Endpoint</a>
      </div>
    </div>
  </article>
);
