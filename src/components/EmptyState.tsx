import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';

type Props = {
  icon?: ReactNode;
  title: string;
  body?: string;
  cta?: { to: string; label: string };
};

export function EmptyState({ icon, title, body, cta }: Props) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded border border-dashed border-gray-300 px-6 py-12 text-center">
      {icon && <div className="text-gray-400">{icon}</div>}
      <h2 className="text-lg font-semibold">{title}</h2>
      {body && <p className="max-w-md text-sm text-gray-600">{body}</p>}
      {cta && (
        <Link to={cta.to} className="rounded bg-gray-900 px-4 py-2 text-sm text-white">
          {cta.label}
        </Link>
      )}
    </div>
  );
}
