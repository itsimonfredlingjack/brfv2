import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import HeroSearch from './HeroSearch';

// Task 4 (cleanup-task-4-brief.md): the Overview tab's hero-search box is the
// only search affordance in the Home/App shell, and it already routes to the
// real ask flow — App.jsx passes it the identical `handleChatSubmit`/
// `askQuestion` functions the chat tab's own input uses (same function
// references, not a parallel path). This proves the DOM wiring (typed text
// reaches the submit callback verbatim, Enter submits, the button submits,
// suggestion pills call the real ask entry point directly) — the resulting
// runAskQuestion call is already covered end-to-end by askQuestion.test.js.
// Renders no results, counts, or scores of its own: it is a pure input,
// never a mock results view (cleanup-global-constraints.md #1).

describe('HeroSearch render path', () => {
  it('renders the current chatInput value and calls onSubmit when the button is clicked', () => {
    const onSubmit = vi.fn();
    render(
      <HeroSearch
        chatInput="Vad gäller uthyrning?"
        setChatInput={vi.fn()}
        chatBusy={false}
        onSubmit={onSubmit}
        onSuggestionClick={vi.fn()}
      />
    );

    const input = screen.getByPlaceholderText("T.ex. 'Vad säger stadgarna om andrahandsuthyrning?'");
    expect(input.value).toBe('Vad gäller uthyrning?');

    screen.getByRole('button', { name: /Fråga/ }).click();
    expect(onSubmit).toHaveBeenCalledTimes(1);
  });

  it('typing calls setChatInput with the raw keystroke value (no transformation)', () => {
    const setChatInput = vi.fn();
    render(
      <HeroSearch
        chatInput=""
        setChatInput={setChatInput}
        chatBusy={false}
        onSubmit={vi.fn()}
        onSuggestionClick={vi.fn()}
      />
    );

    const input = screen.getByPlaceholderText("T.ex. 'Vad säger stadgarna om andrahandsuthyrning?'");
    input.dispatchEvent(new Event('focus'));
    Object.defineProperty(input, 'value', { value: 'stambyte', writable: true });
    input.dispatchEvent(new Event('input', { bubbles: true }));

    expect(setChatInput).toHaveBeenCalledWith('stambyte');
  });

  it('pressing Enter in the input calls onSubmit', () => {
    const onSubmit = vi.fn();
    render(
      <HeroSearch
        chatInput="fråga"
        setChatInput={vi.fn()}
        chatBusy={false}
        onSubmit={onSubmit}
        onSuggestionClick={vi.fn()}
      />
    );

    const input = screen.getByPlaceholderText("T.ex. 'Vad säger stadgarna om andrahandsuthyrning?'");
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
    expect(onSubmit).toHaveBeenCalledTimes(1);
  });

  it('a non-Enter key does not call onSubmit', () => {
    const onSubmit = vi.fn();
    render(
      <HeroSearch
        chatInput="fråga"
        setChatInput={vi.fn()}
        chatBusy={false}
        onSubmit={onSubmit}
        onSuggestionClick={vi.fn()}
      />
    );

    const input = screen.getByPlaceholderText("T.ex. 'Vad säger stadgarna om andrahandsuthyrning?'");
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'a', bubbles: true }));
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('clicking a suggestion pill calls onSuggestionClick with that exact suggestion text — the real ask entry point, no mock result', () => {
    const onSuggestionClick = vi.fn();
    render(
      <HeroSearch
        chatInput=""
        setChatInput={vi.fn()}
        chatBusy={false}
        onSubmit={vi.fn()}
        onSuggestionClick={onSuggestionClick}
      />
    );

    screen.getByText('När startar snöröjningsjouren?').click();
    expect(onSuggestionClick).toHaveBeenCalledWith('När startar snöröjningsjouren?');
    expect(onSuggestionClick).toHaveBeenCalledTimes(1);
  });

  it('while chatBusy the input and submit button are disabled (no submit mid-flight)', () => {
    render(
      <HeroSearch
        chatInput="fråga"
        setChatInput={vi.fn()}
        chatBusy={true}
        onSubmit={vi.fn()}
        onSuggestionClick={vi.fn()}
      />
    );

    const input = screen.getByPlaceholderText("T.ex. 'Vad säger stadgarna om andrahandsuthyrning?'");
    expect(input.disabled).toBe(true);
    expect(screen.getByRole('button', { name: /Fråga/ }).disabled).toBe(true);
  });

  it('renders no result list, count, or score — a pure input, never a mock results view', () => {
    const { container } = render(
      <HeroSearch
        chatInput=""
        setChatInput={vi.fn()}
        chatBusy={false}
        onSubmit={vi.fn()}
        onSuggestionClick={vi.fn()}
      />
    );

    // Only the title/subtitle/box/suggestion-pills markup exists — no
    // results/cards/counts of any kind.
    expect(container.querySelectorAll('[class*="result"]')).toHaveLength(0);
    expect(container.querySelectorAll('[class*="count"]')).toHaveLength(0);
  });
});
