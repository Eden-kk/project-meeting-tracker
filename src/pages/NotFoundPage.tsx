import { Link } from 'react-router-dom';

export default function NotFoundPage() {
  return (
    <div className="space-y-2">
      <h1 className="text-xl font-semibold">404 — page not found</h1>
      <Link to="/" className="text-sm text-blue-600 underline">
        Back to home
      </Link>
    </div>
  );
}
