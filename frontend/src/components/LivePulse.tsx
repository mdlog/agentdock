import { useEffect, useRef, useState } from "react";
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

// A figure that shows the moment it moved. The number is never interpolated —
// every value rendered here is one the API counted — so the highlight says
// "this changed just now" and claims nothing about the seconds in between.
const Figure = ({ value, testId }: { value: number; testId: string }) => {
  const previous = useRef(value);
  const [moved, setMoved] = useState(false);

  useEffect(() => {
    if (previous.current === value) return;
    previous.current = value;
    setMoved(true);
    const fade = setTimeout(() => setMoved(false), 700);
    return () => clearTimeout(fade);
  }, [value]);

  return <strong className={moved ? "moved" : undefined} data-testid={testId}>{value.toLocaleString()}</strong>;
};

// The hero's proof of life. Every number here is work this deployment actually
// did — registrations ingested, endpoints called — so it moves on its own
// without anything being staged. It is the honest alternative to decorative
// motion: a background video would look alive; this is alive.
export const LivePulse = ({ refreshMs = 6_000 }: { refreshMs?: number }) => {
  const [pulse, setPulse] = useState<Pulse | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let cancelled = false;
    const load = () => api.get("/marketplace/pulse")
      .then(r => { if (!cancelled) setPulse(r.data); })
      // A failed poll leaves the last good figures rather than replacing them
      // with a zero, which would read as "nothing is happening".
      .catch(() => {});

    // Asked at the cadence the sweep actually writes verdicts at, so the count
    // climbs while endpoints are being called instead of standing still for a
    // minute at a time. A hidden tab stops repeating: one left open all day
    // would otherwise have the API count the catalogue every few seconds for
    // nobody. The first read always happens, hidden or not — a tab opened in
    // the background would otherwise render no pulse line at all — and coming
    // back to the tab refreshes before resuming.
    let poll: ReturnType<typeof setInterval> | undefined;
    const follow = () => {
      if (poll) clearInterval(poll);
      poll = document.hidden ? undefined : setInterval(load, refreshMs);
    };
    const wake = () => {
      if (!document.hidden) load();
      follow();
    };
    load();
    follow();
    document.addEventListener("visibilitychange", wake);
    // Re-render each minute so "8 min ago" does not sit still while it ages.
    const clock = setInterval(() => setTick(n => n + 1), 60_000);
    return () => {
      cancelled = true;
      if (poll) clearInterval(poll);
      clearInterval(clock);
      document.removeEventListener("visibilitychange", wake);
    };
  }, [refreshMs]);

  if (!pulse) return null;
  const synced = ago(pulse.synced_at);
  void tick;

  return (
    <p className="live-pulse" data-testid="live-pulse">
      <span className="pulse-dot" aria-hidden />
      {synced && <><strong>Synced {synced}</strong> · </>}
      <Figure value={pulse.registered_today} testId="pulse-registered-today" /> agents registered today ·{" "}
      <Figure value={pulse.endpoints_verified} testId="pulse-endpoints-called" /> endpoints called,{" "}
      <Figure value={pulse.agents_live} testId="pulse-answered" /> answered
    </p>
  );
};
