import { useEffect, useRef, useState } from "react";

// The headline used to promise "your next DeFi move", which described 8 of the
// 34 agents that actually answer. The rest do market data, swaps, bridging,
// marketing. Rotating through what the catalogue really covers is both truer
// and more useful — and the words come from the live agents themselves, so a
// job nothing here can do is never named.
//
// The motion is a vertical hand-off: the incoming word drops in from above as
// the outgoing one falls away below, so the line reads as one word being
// replaced rather than two words crossfading.
export const RotatingWord = ({ words, intervalMs = 4600 }: { words: string[]; intervalMs?: number }) => {
  const [index, setIndex] = useState(0);
  const [leaving, setLeaving] = useState<string | null>(null);
  const reduced = useRef(false);

  useEffect(() => {
    reduced.current = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
  }, []);

  useEffect(() => {
    if (words.length < 2) return;
    const timer = setInterval(() => {
      setIndex(current => {
        if (!reduced.current) setLeaving(words[current]);
        return (current + 1) % words.length;
      });
    }, intervalMs);
    return () => clearInterval(timer);
  }, [words, intervalMs]);

  // Clearing the outgoing word after the animation keeps a single element in
  // the DOM at rest, so the line does not carry stale text for a screen reader.
  useEffect(() => {
    if (!leaving) return;
    const timer = setTimeout(() => setLeaving(null), 800);
    return () => clearTimeout(timer);
  }, [leaving]);

  const word = words[index] ?? "";
  return (
    <span className="rotating-word" data-testid="rotating-word">
      {/* The widest word reserves the width, so the headline always breaks at
          the same place. Without it the line was one deep for "yield" and two
          for "market data", and the whole hero jumped every few seconds.
          Nothing follows the word, so the reserved space is invisible. */}
      <span className="rotating-sizer" aria-hidden>
        {words.reduce((longest, candidate) => (candidate.length > longest.length ? candidate : longest), "")}
      </span>
      {leaving && <span className="rotating-out" aria-hidden key={`out-${leaving}`}>{leaving}</span>}
      <span className={leaving ? "rotating-in" : ""} key={word} aria-live="polite">{word}</span>
    </span>
  );
};
