import { useEffect, useState } from "react";
import { api } from "@/lib/api";

type Pulse = {
  catalogue_total: number;
  registered_today: number;
  endpoints_verified: number;
  agents_live: number;
  synced_at: string | null;
};

const ago = (iso: string | null) => {
  if (!iso) return null;
  const seconds = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000));
  if (seconds < 90) return "moments ago";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  return hours < 24 ? `${hours} hr ago` : `${Math.round(hours / 24)} d ago`;
};

// The hero's proof of life. Every number here is work this deployment actually
// did — registrations ingested, endpoints called — so it moves on its own
// without anything being staged. It is the honest alternative to decorative
// motion: a background video would look alive; this is alive.
export const LivePulse = ({ refreshMs = 60_000 }: { refreshMs?: number }) => {
  const [pulse, setPulse] = useState<Pulse | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    const load = () => api.get("/marketplace/pulse")
      .then(r => { if (!cancelled) setPulse(r.data); })
      // A failed poll leaves the last good figures rather than replacing them
      // with a zero, which would read as "nothing is happening".
      .catch(() => {});
    load();
    const poll = setInterval(load, refreshMs);
    // Re-render each minute so "8 min ago" does not sit still while it ages.
    const clock = setInterval(() => setTick(n => n + 1), 60_000);
    return () => { cancelled = true; clearInterval(poll); clearInterval(clock); };
  }, [refreshMs]);

  if (!pulse) return null;
  const synced = ago(pulse.synced_at);
  void tick;

  return (
    <p className="live-pulse" data-testid="live-pulse">
      <span className="pulse-dot" aria-hidden />
      {synced && <><strong>Synced {synced}</strong> · </>}
      <strong>{pulse.registered_today.toLocaleString()}</strong> agents registered today ·{" "}
      <strong>{pulse.endpoints_verified.toLocaleString()}</strong> endpoints called,{" "}
      <strong>{pulse.agents_live}</strong> answered
    </p>
  );
};
