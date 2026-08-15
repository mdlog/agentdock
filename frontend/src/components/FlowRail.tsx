import { AlertTriangle, Check } from "lucide-react";

// The hire page and the task page are one journey, so they show one rail. It
// adapts to the route the agent actually takes: a paid service is priced and
// signed before it runs, a free onchain agent is not, and inventing a payment
// step for an agent that never charges would misdescribe the work.
//
// Labels sit under their markers and the connector runs between markers only —
// the previous rail drew one line straight through the words.
export type FlowStep = { key: string; label: string; hint: string };

export const PAID_FLOW: FlowStep[] = [
  { key: "created", label: "Describe", hint: "Say what you need" },
  { key: "payment_pending", label: "Price", hint: "Merchant quotes it" },
  { key: "paid", label: "Sign", hint: "Your wallet approves" },
  { key: "completed", label: "Result", hint: "The agent replies" },
];

export const FREE_FLOW: FlowStep[] = [
  { key: "created", label: "Describe", hint: "Say what you need" },
  { key: "running", label: "Run", hint: "We call the endpoint" },
  { key: "completed", label: "Result", hint: "The agent replies" },
];

export const FlowRail = ({ steps, current, busy = false, failed = false, testId = "flow-rail" }: {
  steps: FlowStep[];
  current: number;
  busy?: boolean;
  failed?: boolean;
  testId?: string;
}) => (
  <nav className="flow-rail" data-testid={testId} aria-label="Task progress">
    <ol>
      {steps.map((step, index) => {
        const done = index < current;
        const isCurrent = index === current;
        const state = done ? "done" : isCurrent ? (failed ? "error" : "current") : "upcoming";
        return (
          <li key={step.key} className={`${state}${isCurrent && busy && !failed ? " busy" : ""}`} data-testid={`flow-step-${step.key}`}>
            <span className="marker" aria-hidden>
              {done ? <Check size={14} /> : isCurrent && failed ? <AlertTriangle size={13} /> : index + 1}
            </span>
            <strong data-testid={`task-stage-${step.key}`}>{step.label}</strong>
            <small>{isCurrent && failed ? "Did not complete" : step.hint}</small>
          </li>
        );
      })}
    </ol>
  </nav>
);
