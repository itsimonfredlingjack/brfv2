import { api } from './api';
import { buildAnswerMessage, buildErrorMessage } from './chatResponseMapping';

// Extracted from App.jsx's askQuestion (cleanup/verified-ui Task 1 follow-up)
// so the real api.ask() call and its success/error/busy-guard wiring are
// under test — not just proven by eye. App.jsx's askQuestion is now a thin
// wrapper that calls this with its live state setters (same function, no
// parallel copy); tests drive it via `vi.mock('./api')`.
//
// deps:
//   activeBrfId, chatBusy                              — current values (component-closure state)
//   setCurrentTab, setActiveDocument                    — React setters
//   setChatMessages                                     — React setter, called with a functional updater (prev => next), same as before extraction
//   setChatBusy                                         — React setter
//   handleApiError(e) => boolean                        — true if e was a 401 session-expiry (already handled elsewhere; the error message must NOT also be appended)
export async function runAskQuestion(question, deps) {
  const {
    activeBrfId,
    chatBusy,
    setCurrentTab,
    setActiveDocument,
    setChatMessages,
    setChatBusy,
    handleApiError,
  } = deps;

  const q = question.trim();
  if (!q || chatBusy) return;

  setCurrentTab('chat');
  setActiveDocument(null);
  setChatMessages((prev) => [
    ...prev,
    { role: 'user', content: q },
    { role: 'ai', pending: true, content: 'Söker i dokumenten…' },
  ]);
  setChatBusy(true);
  try {
    const resp = await api.ask(activeBrfId, q);
    setChatMessages((prev) => [...prev.slice(0, -1), buildAnswerMessage(resp)]);
  } catch (e) {
    if (!handleApiError(e)) {
      setChatMessages((prev) => [...prev.slice(0, -1), buildErrorMessage(e)]);
    }
  } finally {
    setChatBusy(false);
  }
}
