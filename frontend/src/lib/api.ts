import axios from "axios";

const backendUrl = process.env.REACT_APP_BACKEND_URL;
if (!backendUrl) throw new Error("REACT_APP_BACKEND_URL is required");

// Reads are quick. Anything that makes the backend call a third-party agent is
// not: the server budgets 45s for an agent call and 90s for a paid one, so a
// blanket 15s here reported successful work as a timeout — and on the payment
// path, abandoned a request whose signature had already been submitted.
export const api = axios.create({ baseURL: `${backendUrl}/api`, timeout: 15000 });

/** Budget for a call that waits on a third-party agent. */
export const AGENT_CALL = { timeout: 75000 };
/** Budget for a paid call: the merchant's own ceiling is 90s. */
export const PAID_CALL = { timeout: 120000 };

export const messageFromError = (error: any) => {
  const detail = error?.response?.data?.detail;
  if (typeof detail === "string") return detail;
  if (detail) return JSON.stringify(detail);
  // No response at all means the browser never saw one — a timeout, a dropped
  // connection, or an edge error page. Say which, rather than "Network Error".
  if (error?.code === "ECONNABORTED") return "The agent did not answer in time. The task page shows what was recorded.";
  if (!error?.response) return "Could not reach AgentDock. Check your connection and try again.";
  return error?.message || "Something went wrong";
};
