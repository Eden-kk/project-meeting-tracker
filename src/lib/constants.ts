/**
 * Entry-redirect fallback only.
 *
 * As of the workspace-switcher slice, the active workspace lives in the
 * URL (`/ws/:workspaceId/...`) — every consumer reads it via
 * `useWorkspace()`. This constant is only used by `RootRedirect` as a
 * last-resort target when both `localStorage.lastWorkspaceId` is empty
 * AND the `/api/workspaces` list is empty (extreme edge case in
 * pre-production where the migration seed has been wiped).
 */
export const DEV_WORKSPACE_ID = 'ws_dev';
export const POLL_INTERVAL_MS = 1000;
export const MAX_UPLOAD_BYTES = 100 * 1024 * 1024;
