import { describe, it, expect, vi, beforeEach } from 'vitest';
import { runAskQuestion } from './askQuestion';
import { api } from './api';
import { buildAnswerMessage, buildErrorMessage } from './chatResponseMapping';

// Proves the actual askQuestion wiring (App.jsx's real call site — see
// `const askQuestion = (question) => runAskQuestion(question, {...})`),
// not just the pieces it calls. Mocks the HTTP layer via vi.mock('./api')
// per the brief, and simulates React's functional setState with a plain
// in-memory variable so the exact `setChatMessages(prev => ...)` calls this
// module makes can be exercised without mounting a component.

vi.mock('./api', () => ({ api: { ask: vi.fn() } }));

function makeState(initial) {
  let value = initial;
  const set = vi.fn((updater) => {
    value = typeof updater === 'function' ? updater(value) : updater;
  });
  return { get: () => value, set };
}

function baseDeps(overrides = {}) {
  return {
    activeBrfId: 'brf-1',
    chatBusy: false,
    setCurrentTab: vi.fn(),
    setActiveDocument: vi.fn(),
    setChatMessages: vi.fn(),
    setChatBusy: vi.fn(),
    handleApiError: vi.fn(() => false),
    ...overrides,
  };
}

describe('runAskQuestion', () => {
  beforeEach(() => {
    api.ask.mockReset();
  });

  it('(a) api.ask resolves: the pending message is replaced by buildAnswerMessage(resp), busy toggles true then false', async () => {
    const resp = {
      answer: 'Enligt stadgarna gäller detta.',
      citations: [
        { document_name: 'Stadgar.pdf', page: 4, quote: 'Andrahandsuthyrning...', chunk_id: 'hash-1', rects: [[1, 2, 3, 4]], score: 0.81 },
      ],
      rejected_citations: [],
      refusal: false,
      warning: null,
    };
    api.ask.mockResolvedValueOnce(resp);

    const messages = makeState([]);
    const busy = makeState(false);
    const tab = makeState('overview');
    const doc = makeState('some-doc-id');
    const handleApiError = vi.fn(() => false);

    await runAskQuestion('Vad gäller?', baseDeps({
      setCurrentTab: tab.set,
      setActiveDocument: doc.set,
      setChatMessages: messages.set,
      setChatBusy: busy.set,
      handleApiError,
    }));

    expect(api.ask).toHaveBeenCalledTimes(1);
    expect(api.ask).toHaveBeenCalledWith('brf-1', 'Vad gäller?');
    expect(tab.get()).toBe('chat');
    expect(doc.get()).toBeNull();
    expect(busy.set).toHaveBeenNthCalledWith(1, true);
    expect(busy.set).toHaveBeenLastCalledWith(false);
    expect(busy.get()).toBe(false);
    expect(handleApiError).not.toHaveBeenCalled();

    const finalMessages = messages.get();
    expect(finalMessages).toHaveLength(2); // user message + final ai message (pending replaced, not appended)
    expect(finalMessages[0]).toEqual({ role: 'user', content: 'Vad gäller?' });
    expect(finalMessages[1]).toEqual(buildAnswerMessage(resp));
    expect(finalMessages[1].pending).toBeUndefined();
  });

  it('(b) api.ask rejects and handleApiError does not consume it: appends buildErrorMessage(error)', async () => {
    const error = new Error('Failed to fetch');
    api.ask.mockRejectedValueOnce(error);

    const messages = makeState([]);
    const busy = makeState(false);
    const handleApiError = vi.fn(() => false);

    await runAskQuestion('Vad gäller?', baseDeps({
      setChatMessages: messages.set,
      setChatBusy: busy.set,
      handleApiError,
    }));

    expect(handleApiError).toHaveBeenCalledWith(error);
    const finalMessages = messages.get();
    expect(finalMessages).toHaveLength(2);
    expect(finalMessages[1]).toEqual(buildErrorMessage(error));
    expect(finalMessages[1].citations).toBeUndefined();
    expect(busy.get()).toBe(false);
  });

  it('(b2) api.ask rejects with a 401: the handleApiError guard is respected — no error message appended', async () => {
    const error = Object.assign(new Error('Session expired'), { status: 401 });
    api.ask.mockRejectedValueOnce(error);

    const messages = makeState([]);
    const handleApiError = vi.fn(() => true); // simulates App.jsx's resetToLogin path having already handled it

    await runAskQuestion('Vad gäller?', baseDeps({
      setChatMessages: messages.set,
      handleApiError,
    }));

    expect(handleApiError).toHaveBeenCalledWith(error);
    // Only the initial user + pending append happened — the catch block must
    // not also append an error message once handleApiError has claimed it.
    expect(messages.get()).toHaveLength(2);
    expect(messages.get()[1]).toEqual({ role: 'ai', pending: true, content: 'Söker i dokumenten…' });
  });

  it('(c) blank input: does not call api.ask and does not touch chat state', async () => {
    const messages = makeState([]);
    const busy = makeState(false);

    await runAskQuestion('   ', baseDeps({ setChatMessages: messages.set, setChatBusy: busy.set }));

    expect(api.ask).not.toHaveBeenCalled();
    expect(messages.get()).toEqual([]);
    expect(busy.set).not.toHaveBeenCalled();
  });

  it('(c) already busy: does not call api.ask even with valid input', async () => {
    const messages = makeState([]);

    await runAskQuestion('Vad gäller?', baseDeps({ chatBusy: true, setChatMessages: messages.set }));

    expect(api.ask).not.toHaveBeenCalled();
    expect(messages.get()).toEqual([]);
  });
});
