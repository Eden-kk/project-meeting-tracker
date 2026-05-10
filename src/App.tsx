import { BrowserRouter, Link, Route, Routes } from 'react-router-dom';
import ImportPage from './pages/ImportPage';
import ProcessingPage from './pages/ProcessingPage';
import MeetingReviewPage from './pages/MeetingReviewPage';

export default function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen bg-white text-gray-900">
        <header className="border-b border-gray-200 px-4 py-3">
          <Link to="/" className="text-lg font-semibold">
            Tracker
          </Link>
        </header>
        <main className="px-4 py-6">
          <Routes>
            <Route path="/" element={<ImportPage />} />
            <Route path="/meetings/:id/processing" element={<ProcessingPage />} />
            <Route path="/meetings/:id" element={<MeetingReviewPage />} />
            <Route path="*" element={<div>404 — page not found</div>} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}
