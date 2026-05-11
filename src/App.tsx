import { BrowserRouter, Route, Routes } from 'react-router-dom';
import ImportPage from './pages/ImportPage';
import ProcessingPage from './pages/ProcessingPage';
import MeetingReviewPage from './pages/MeetingReviewPage';
import NotFoundPage from './pages/NotFoundPage';
import { SidebarShell } from './layouts/SidebarShell';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<SidebarShell />}>
          {/* Stage 1: dual-mount ImportPage at / and /import so existing tests stay green.
              Stage 4 flips / to HomePage and removes this duplicate. */}
          <Route path="/" element={<ImportPage />} />
          <Route path="/import" element={<ImportPage />} />
          <Route path="/meetings/:id/processing" element={<ProcessingPage />} />
          <Route path="/meetings/:id" element={<MeetingReviewPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
