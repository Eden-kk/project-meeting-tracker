/**
 * WorkspaceSwitcher — top-right button + dropdown that replaces the old
 * cross-meeting SearchBar. Reads the current workspace from `useParams()`
 * (via `useWorkspace`); clicking a workspace navigates to the same
 * sub-path under the new id, dropping any workspace-scoped resource
 * segment (`meetings/<id>`, `processing/<id>`) since those don't exist
 * in the destination.
 */
import { useEffect, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useWorkspace } from '../hooks/useWorkspace';
import { formatRelative } from './HomeMemoryItemsCard';

/** Sub-paths that are safe to carry across a workspace switch. Anything
 *  not in this set (or a deeper path beyond the first segment) collapses
 *  to the workspace root when switching. */
const SAFE_TOP_SEGMENTS = new Set([
  'meetings',
  'action-items',
  'open-questions',
  'ask',
  'live',
  'import',
  'processing',
  'settings',
]);

/** Rewrite the URL's workspace segment for a switch. Path-preservation
 *  whitelist: keep the first sub-segment IFF it is a safe, workspace-
 *  agnostic page; otherwise (or when there is a second segment, which is
 *  always workspace-scoped — meeting id, processing id) collapse to the
 *  workspace root.
 *
 *  Examples
 *    /ws/a/action-items                → /ws/b/action-items
 *    /ws/a/meetings                    → /ws/b/meetings
 *    /ws/a/meetings/m_xyz              → /ws/b/meetings   (drop scoped id)
 *    /ws/a/meetings/m_xyz/processing   → /ws/b/meetings
 *    /ws/a/                            → /ws/b/
 *    /ws/a/weird-page                  → /ws/b/           (not whitelisted)
 */
export function buildSwitchPath(currentPath: string, newWorkspaceId: string): string {
  // split on '/', drop the empty leading segment.
  const parts = currentPath.split('/').filter(Boolean);
  // parts = ['ws', '<id>', '<top>?', ...rest]
  const top = parts[2];
  if (!top) {
    return `/ws/${newWorkspaceId}/`;
  }
  if (parts.length > 3 || !SAFE_TOP_SEGMENTS.has(top)) {
    // Workspace-scoped id present OR top segment isn't safe to carry.
    if (SAFE_TOP_SEGMENTS.has(top)) {
      return `/ws/${newWorkspaceId}/${top}`;
    }
    return `/ws/${newWorkspaceId}/`;
  }
  return `/ws/${newWorkspaceId}/${top}`;
}

export function WorkspaceSwitcher() {
  const { workspaceId, workspaces, currentWorkspace, isLoading } = useWorkspace();
  const navigate = useNavigate();
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const wrapperRef = useRef<HTMLDivElement | null>(null);

  // Click outside → close.
  useEffect(() => {
    if (!open) return;
    function onClick(e: MouseEvent) {
      if (!wrapperRef.current) return;
      if (!wrapperRef.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, [open]);

  function handleSelect(targetId: string) {
    if (targetId !== workspaceId) {
      navigate(buildSwitchPath(location.pathname, targetId));
    }
    setOpen(false);
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLDivElement>) {
    if (!open) return;
    if (e.key === 'Escape') {
      setOpen(false);
      return;
    }
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActiveIndex((i) => Math.min(workspaces.length - 1, i + 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActiveIndex((i) => Math.max(0, i - 1));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      const item = workspaces[activeIndex];
      if (item) handleSelect(item.id);
    }
  }

  // Loading: button text is ellipsis. Empty list: button disabled.
  const empty = !isLoading && workspaces.length === 0;
  const buttonLabel = isLoading
    ? '…'
    : empty
      ? 'No workspaces — create one in the DB'
      : currentWorkspace?.name ?? workspaceId;

  return (
    <div
      ref={wrapperRef}
      className="relative inline-block text-left"
      onKeyDown={onKeyDown}
      data-testid="workspace-switcher"
    >
      <button
        type="button"
        disabled={isLoading || empty}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label="Switch workspace"
        onClick={() => setOpen((v) => !v)}
        className="inline-flex items-center gap-2 rounded border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-800 hover:bg-gray-50 disabled:opacity-50"
      >
        <span className="truncate max-w-[18ch]">{buttonLabel}</span>
        <span aria-hidden="true">▾</span>
      </button>

      {open && workspaces.length > 0 && (
        <ul
          role="listbox"
          aria-label="Workspaces"
          className="absolute right-0 z-50 mt-1 max-h-80 w-72 overflow-auto rounded border border-gray-200 bg-white shadow-lg"
        >
          {workspaces.map((w, i) => {
            const active = i === activeIndex;
            const current = w.id === workspaceId;
            return (
              <li
                key={w.id}
                role="option"
                aria-selected={current}
                tabIndex={-1}
                onMouseEnter={() => setActiveIndex(i)}
                onClick={() => handleSelect(w.id)}
                className={`cursor-pointer px-3 py-2 text-sm ${
                  active ? 'bg-gray-100' : ''
                } ${current ? 'font-semibold' : ''}`}
                data-testid={`workspace-item-${w.id}`}
              >
                <div className="flex items-baseline justify-between gap-2">
                  <span className="truncate">{w.name}</span>
                  <span className="shrink-0 text-xs text-gray-500">
                    {formatRelative(w.last_meeting_at)}
                  </span>
                </div>
                {w.description && (
                  <p className="truncate text-xs text-gray-500">{w.description}</p>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
