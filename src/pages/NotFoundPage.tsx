import { Link } from 'react-router-dom';
import { useWorkspace } from '../hooks/useWorkspace';

export default function NotFoundPage() {
  // The NotFoundPage is mounted under /ws/:workspaceId/* so the
  // "back to home" link keeps the user in their current workspace
  // rather than bouncing them through the entry redirect.
  const { workspaceId } = useWorkspace();
  return (
    <div className="space-y-2">
      <h1 className="text-xl font-semibold">404 — page not found</h1>
      <Link to={`/ws/${workspaceId}/`} className="text-sm text-blue-600 underline">
        Back to home
      </Link>
    </div>
  );
}
