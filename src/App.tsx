import { BrowserRouter, Route, Routes } from 'react-router-dom';
import HomePage from './pages/HomePage';
import ImportPage from './pages/ImportPage';
import LivePage from './pages/LivePage';
import MeetingsPage from './pages/MeetingsPage';
import ProcessingPage from './pages/ProcessingPage';
import MeetingReviewPage from './pages/MeetingReviewPage';
import NotFoundPage from './pages/NotFoundPage';
import SettingsPage from './pages/SettingsPage';
<<<<<<< HEAD
import ActionItemsPage from './pages/ActionItemsPage';
import OpenQuestionsPage from './pages/OpenQuestionsPage';
=======
import AskPage from './pages/AskPage';
>>>>>>> origin/feat/p6-global-ask-hermes
import { SidebarShell } from './layouts/SidebarShell';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<SidebarShell />}>
          <Route path="/" element={<HomePage />} />
          <Route path="/meetings" element={<MeetingsPage />} />
          <Route path="/import" element={<ImportPage />} />
<<<<<<< HEAD
          <Route path="/live" element={<LivePage />} />
=======
          <Route path="/ask" element={<AskPage />} />
>>>>>>> origin/feat/p6-global-ask-hermes
          <Route path="/meetings/:id/processing" element={<ProcessingPage />} />
          <Route path="/meetings/:id" element={<MeetingReviewPage />} />
          <Route path="/action-items" element={<ActionItemsPage />} />
          <Route path="/open-questions" element={<OpenQuestionsPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
