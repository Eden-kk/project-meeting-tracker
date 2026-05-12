import { BrowserRouter, Route, Routes } from 'react-router-dom';
import HomePage from './pages/HomePage';
import ImportPage from './pages/ImportPage';
import LivePage from './pages/LivePage';
import MeetingsPage from './pages/MeetingsPage';
import ProcessingPage from './pages/ProcessingPage';
import MeetingReviewPage from './pages/MeetingReviewPage';
import NotFoundPage from './pages/NotFoundPage';
import SettingsPage from './pages/SettingsPage';
import ActionItemsPage from './pages/ActionItemsPage';
import OpenQuestionsPage from './pages/OpenQuestionsPage';
import AskPage from './pages/AskPage';
import { WorkspaceShell } from './components/WorkspaceShell';
import { RootRedirect } from './components/RootRedirect';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Entry redirect: resolve last-used workspace and Navigate
            into the /ws/:workspaceId tree. */}
        <Route path="/" element={<RootRedirect />} />
        <Route path="ws/:workspaceId" element={<WorkspaceShell />}>
          <Route index element={<HomePage />} />
          <Route path="meetings" element={<MeetingsPage />} />
          <Route path="import" element={<ImportPage />} />
          <Route path="live" element={<LivePage />} />
          <Route path="ask" element={<AskPage />} />
          <Route path="meetings/:id/processing" element={<ProcessingPage />} />
          <Route path="meetings/:id" element={<MeetingReviewPage />} />
          <Route path="action-items" element={<ActionItemsPage />} />
          <Route path="open-questions" element={<OpenQuestionsPage />} />
          <Route path="settings" element={<SettingsPage />} />
          {/* In-workspace 404. */}
          <Route path="*" element={<NotFoundPage />} />
        </Route>
        {/* Top-level catch-all: anything outside /ws/* falls through here
            and gets redirected to the entry workspace. */}
        <Route path="*" element={<RootRedirect />} />
      </Routes>
    </BrowserRouter>
  );
}
