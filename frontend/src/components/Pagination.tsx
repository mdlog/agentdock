import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";

// Server-side paging. The catalogue is far larger than any page, so the browser
// never receives it whole and page numbers are derived from the server's total.
export const Pagination = ({ total, offset, limit, onChange, testId = "pagination" }: {
  total: number; offset: number; limit: number; onChange: (offset: number) => void; testId?: string;
}) => {
  const pages = Math.max(1, Math.ceil(total / limit));
  const page = Math.floor(offset / limit) + 1;
  if (total <= limit) return null;

  const jump = (delta: number) => onChange(Math.min(Math.max(0, offset + delta * limit), (pages - 1) * limit));

  return <div className="pager" data-testid={testId}>
    <Button data-testid={`${testId}-first`} variant="outline" size="sm" disabled={page === 1} onClick={() => onChange(0)}>First</Button>
    <Button data-testid={`${testId}-prev`} variant="outline" size="sm" disabled={page === 1} onClick={() => jump(-1)}><ChevronLeft size={14} /> Prev</Button>
    <span data-testid={`${testId}-label`}>
      Page <strong>{page.toLocaleString()}</strong> of <strong>{pages.toLocaleString()}</strong>
      <em>{total.toLocaleString()} agents</em>
    </span>
    <Button data-testid={`${testId}-next`} variant="outline" size="sm" disabled={page >= pages} onClick={() => jump(1)}>Next <ChevronRight size={14} /></Button>
    <Button data-testid={`${testId}-last`} variant="outline" size="sm" disabled={page >= pages} onClick={() => onChange((pages - 1) * limit)}>Last</Button>
  </div>;
};
