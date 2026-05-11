import { BrowserRouter, Route, Routes } from 'react-router-dom';
import HomePage from './pages/HomePage';
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
          <Route path="/" element={<HomePage />} />
          <Route path="/import" element={<ImportPage />} />
          <Route path="/meetings/:id/processing" element={<ProcessingPage />} />
          <Route path="/meetings/:id" element={<MeetingReviewPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
