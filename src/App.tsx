import { BrowserRouter, Route, Routes } from 'react-router-dom';
import HomePage from './pages/HomePage';
import ImportPage from './pages/ImportPage';
import MeetingsPage from './pages/MeetingsPage';
import ProcessingPage from './pages/ProcessingPage';
import MeetingReviewPage from './pages/MeetingReviewPage';
import NotFoundPage from './pages/NotFoundPage';
import SettingsPage from './pages/SettingsPage';
import { SidebarShell } from './layouts/SidebarShell';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<SidebarShell />}>
          <Route path="/" element={<HomePage />} />
          <Route path="/meetings" element={<MeetingsPage />} />
          <Route path="/import" element={<ImportPage />} />
          <Route path="/meetings/:id/processing" element={<ProcessingPage />} />
          <Route path="/meetings/:id" element={<MeetingReviewPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
