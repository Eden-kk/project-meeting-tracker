import { useEffect, useId, useRef, useState } from 'react';
import { NavLink } from 'react-router-dom';
import { useWorkspace } from '../hooks/useWorkspace';

type NavItem = { to: string; label: string; end?: boolean };
// Relative-to-workspace nav targets. Concatenated with the current
// workspace prefix at render time so the active workspaceId stays in
// the URL.
const NAV_ITEMS: NavItem[] = [
  { to: '', label: 'Home', end: true },
  { to: 'meetings', label: 'Meetings' },
  { to: 'ask', label: 'Ask Hermes' },
  { to: 'import', label: 'Import' },
  { to: 'live', label: 'Live' },
  { to: 'action-items', label: 'Action items' },
  { to: 'open-questions', label: 'Open questions' },
];
const SECONDARY_ITEMS: NavItem[] = [{ to: 'settings', label: 'Settings' }];

function navLinkClass({ isActive }: { isActive: boolean }) {
  const base = 'block rounded px-3 py-2 text-sm';
  return isActive ? `${base} bg-gray-900 text-white` : `${base} text-gray-700 hover:bg-gray-100`;
}

function NavList() {
  const { workspaceId } = useWorkspace();
  const prefix = `/ws/${workspaceId}`;
  const renderLink = (item: NavItem) => {
    const path = item.to ? `${prefix}/${item.to}` : `${prefix}/`;
    return (
      <NavLink key={item.to} to={path} end={item.end} className={navLinkClass}>
        {item.label}
      </NavLink>
    );
  };
  return (
    <nav aria-label="Main navigation" className="flex flex-col gap-1">
      {NAV_ITEMS.map(renderLink)}
      <hr className="my-2 border-gray-200" />
      {SECONDARY_ITEMS.map(renderLink)}
    </nav>
  );
}

function SidebarContent() {
  const { workspaceId, currentWorkspace } = useWorkspace();
  return (
    <div className="flex h-full flex-col p-4">
      <div className="mb-4 text-lg font-semibold">Tracker</div>
      <NavList />
      <div className="mt-auto text-xs text-gray-500">
        {currentWorkspace?.name ?? workspaceId}
      </div>
    </div>
  );
}

export function Sidebar() {
  return (
    <aside className="hidden w-60 shrink-0 border-r border-gray-200 bg-white md:block" data-testid="sidebar">
      <SidebarContent />
    </aside>
  );
}

export function MobileSidebar() {
  const [open, setOpen] = useState(false);
  const drawerId = useId();
  const toggleRef = useRef<HTMLButtonElement | null>(null);
  const drawerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const previouslyFocused = document.activeElement as HTMLElement | null;
    const drawer = drawerRef.current;
    drawer?.querySelector<HTMLElement>('a, button')?.focus();

    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') {
        setOpen(false);
      }
    }
    document.addEventListener('keydown', onKey);

    const main = document.querySelector('main');
    if (main) main.setAttribute('inert', '');

    return () => {
      document.removeEventListener('keydown', onKey);
      if (main) main.removeAttribute('inert');
      previouslyFocused?.focus();
    };
  }, [open]);

  return (
    <div className="md:hidden">
      <div className="flex items-center justify-between border-b border-gray-200 bg-white px-4 py-3">
        <span className="text-lg font-semibold">Tracker</span>
        <button
          ref={toggleRef}
          type="button"
          aria-expanded={open}
          aria-controls={drawerId}
          aria-label="Open menu"
          onClick={() => setOpen((v) => !v)}
          className="rounded border border-gray-300 px-3 py-1 text-sm"
        >
          Menu
        </button>
      </div>
      {open && (
        <>
          <div
            className="fixed inset-0 z-40 bg-black/40"
            onClick={() => setOpen(false)}
            aria-hidden="true"
          />
          <div
            ref={drawerRef}
            id={drawerId}
            role="dialog"
            aria-modal="true"
            aria-label="Main navigation"
            className="fixed inset-y-0 left-0 z-50 w-60 border-r border-gray-200 bg-white"
          >
            <SidebarContent />
          </div>
        </>
      )}
    </div>
  );
}
