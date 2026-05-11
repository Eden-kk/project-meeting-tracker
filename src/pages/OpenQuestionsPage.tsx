import { listOpenQuestions } from '../api/client';
import { queryKeys } from '../api/queryKeys';
import { DashboardView } from './ActionItemsPage';

/** Wave 5.2 — cross-meeting open-questions dashboard.
 *
 * Same shape as `/action-items` (5.1) — the table component, filters,
 * row layout, and query parameters are all shared. This page is the
 * thin (route, query, label) discriminator on top.
 */
export default function OpenQuestionsPage() {
  return (
    <DashboardView
      title="Open questions"
      emptyTitle="No open questions yet"
      emptyBody="Open questions extracted across all meetings will appear here."
      queryFn={listOpenQuestions}
      queryKey={queryKeys.openQuestions}
    />
  );
}
