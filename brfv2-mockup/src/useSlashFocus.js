import { useEffect } from 'react';

const TYPING = 'input, textarea, select, [contenteditable="true"]';

/**
 * "/" focuses the view's own filter — the home-row shortcut for power users.
 *
 * Never fires while the user is already typing somewhere, and never with a
 * modifier held: browser and OS shortcuts win. `enabled` lets a shell gate
 * the shortcut to the tab where the field is actually on screen.
 */
export default function useSlashFocus(ref, enabled = true) {
  useEffect(() => {
    if (!enabled) return undefined;
    const onKeyDown = (event) => {
      if (event.key !== '/' || event.metaKey || event.ctrlKey || event.altKey) return;
      if (event.target instanceof HTMLElement && event.target.closest(TYPING)) return;
      const target = ref.current;
      if (!target) return;
      event.preventDefault();
      target.focus();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [ref, enabled]);
}
