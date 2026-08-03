import { describe, expect, it } from 'vitest';
import {
  actionToCommands,
  coalesce,
  diffProps,
  domainProps,
  groundingMetadata,
  toPuckData,
} from './components/website/websiteCommands';

// The human half of the "one command engine" rule.
//
// These are the translations that decide whether a drag becomes a `move_block`
// or a page-shaped write, so they are tested on their own rather than only
// through the editor — the bug this guards against is silent, and would look
// exactly like a working editor right up until two people edited one page.

const FIELDS = {
  Hero: ['heading', 'preamble', 'image', 'action', 'variant'],
  NewsList: ['heading', 'items'],
};

const item = (id, type, props = {}) => ({ type, props: { id, ...props } });
const state = (content, root = {}) => ({ data: { content, root } });

describe('domainProps', () => {
  it('drops the block id, which is identity and not a value', () => {
    expect(domainProps({ id: 'b1', heading: 'Hej' }, FIELDS.Hero)).toEqual({ heading: 'Hej' });
  });

  it('drops anything the component does not declare', () => {
    expect(domainProps({ id: 'b1', heading: 'Hej', smuggled: '<script>' }, FIELDS.Hero))
      .toEqual({ heading: 'Hej' });
  });
});

describe('diffProps', () => {
  it('returns only what actually changed', () => {
    const before = { id: 'b1', heading: 'Före', preamble: 'Samma' };
    const after = { id: 'b1', heading: 'Efter', preamble: 'Samma' };
    expect(diffProps(before, after, FIELDS.Hero)).toEqual({ heading: 'Efter' });
  });

  it('compares nested values structurally, not by reference', () => {
    const before = { id: 'b1', image: { src: '/a.jpg', alt: 'Gården' } };
    const after = { id: 'b1', image: { src: '/a.jpg', alt: 'Gården' } };
    expect(diffProps(before, after, FIELDS.Hero)).toEqual({});
  });
});

describe('actionToCommands', () => {
  const pageId = 'page-1';

  it('turns an insert into insert_block carrying the id the editor minted', () => {
    const next = state([item('b-new', 'Hero', { heading: 'Välkommen' })]);
    const commands = actionToCommands({
      action: { type: 'insert', componentType: 'Hero', destinationIndex: 0, destinationZone: 'root' },
      appState: next,
      prevAppState: state([]),
      pageId,
      fieldsByType: FIELDS,
    });
    expect(commands).toEqual([{
      command: 'insert_block',
      page_id: pageId,
      type: 'Hero',
      block_id: 'b-new',
      props: { heading: 'Välkommen' },
      index: 0,
    }]);
  });

  it('turns a drag into move_block with the finished position', () => {
    const before = state([item('a', 'Hero'), item('b', 'NewsList')]);
    const after = state([item('b', 'NewsList'), item('a', 'Hero')]);
    const commands = actionToCommands({
      action: { type: 'reorder', sourceIndex: 0, destinationIndex: 1, destinationZone: 'root' },
      appState: after,
      prevAppState: before,
      pageId,
      fieldsByType: FIELDS,
    });
    expect(commands).toEqual([{ command: 'move_block', page_id: pageId, block_id: 'a', index: 1 }]);
  });

  it('turns a delete into delete_block naming the block that was there', () => {
    const before = state([item('a', 'Hero'), item('b', 'NewsList')]);
    const commands = actionToCommands({
      action: { type: 'remove', index: 1, zone: 'root' },
      appState: state([item('a', 'Hero')]),
      prevAppState: before,
      pageId,
      fieldsByType: FIELDS,
    });
    expect(commands).toEqual([{ command: 'delete_block', page_id: pageId, block_id: 'b' }]);
  });

  it('turns a duplicate into duplicate_block with both ids', () => {
    const before = state([item('a', 'Hero')]);
    const after = state([item('a', 'Hero'), item('a-copy', 'Hero')]);
    expect(actionToCommands({
      action: { type: 'duplicate', sourceIndex: 0, sourceZone: 'root' },
      appState: after,
      prevAppState: before,
      pageId,
      fieldsByType: FIELDS,
    })).toEqual([{
      command: 'duplicate_block', page_id: pageId, block_id: 'a', block_id_new: 'a-copy',
    }]);
  });

  it('reduces a whole-component replace to the one field that changed', () => {
    // This is the important one. Puck's `replace` carries the entire component;
    // forwarding it would be the replacement write the backend exists to refuse.
    const before = state([item('a', 'Hero', { heading: 'Före', preamble: 'Rör inte' })]);
    const commands = actionToCommands({
      action: {
        type: 'replace',
        destinationIndex: 0,
        destinationZone: 'root',
        data: item('a', 'Hero', { heading: 'Efter', preamble: 'Rör inte' }),
      },
      appState: state([item('a', 'Hero', { heading: 'Efter', preamble: 'Rör inte' })]),
      prevAppState: before,
      pageId,
      fieldsByType: FIELDS,
    });
    expect(commands).toEqual([{
      command: 'update_text', page_id: pageId, block_id: 'a', field: 'heading', value: 'Efter',
    }]);
    expect(JSON.stringify(commands)).not.toContain('preamble');
  });

  it('uses update_block when more than one field changed at once', () => {
    const before = state([item('a', 'Hero', { heading: 'A', variant: 'image' })]);
    const commands = actionToCommands({
      action: {
        type: 'replace',
        destinationIndex: 0,
        destinationZone: 'root',
        data: item('a', 'Hero', { heading: 'B', variant: 'plain' }),
      },
      appState: state([item('a', 'Hero', { heading: 'B', variant: 'plain' })]),
      prevAppState: before,
      pageId,
      fieldsByType: FIELDS,
    });
    expect(commands).toEqual([{
      command: 'update_block', page_id: pageId, block_id: 'a', props: { heading: 'B', variant: 'plain' },
    }]);
  });

  it('emits nothing when a replace changed nothing', () => {
    const same = item('a', 'Hero', { heading: 'Lika' });
    expect(actionToCommands({
      action: { type: 'replace', destinationIndex: 0, destinationZone: 'root', data: same },
      appState: state([same]),
      prevAppState: state([same]),
      pageId,
      fieldsByType: FIELDS,
    })).toEqual([]);
  });

  it('never forwards a bulk state action', () => {
    // setData is what we dispatch to re-sync the canvas from the server. Echoing
    // it back would turn a refresh into a write.
    ['setData', 'set', 'setUi', 'registerZone', 'unregisterZone'].forEach((type) => {
      expect(actionToCommands({
        action: { type, data: { content: [] } },
        appState: state([]),
        prevAppState: state([item('a', 'Hero')]),
        pageId,
        fieldsByType: FIELDS,
      })).toEqual([]);
    });
  });

  it('emits nothing without a page, rather than guessing one', () => {
    expect(actionToCommands({
      action: { type: 'remove', index: 0, zone: 'root' },
      appState: state([]),
      prevAppState: state([item('a', 'Hero')]),
      pageId: '',
      fieldsByType: FIELDS,
    })).toEqual([]);
  });

  it('renames the page when the root title changes', () => {
    expect(actionToCommands({
      action: { type: 'replaceRoot', root: { props: { title: 'Nytt namn' } } },
      appState: state([], { props: { title: 'Nytt namn' } }),
      prevAppState: state([], { props: { title: 'Gammalt' } }),
      pageId,
      fieldsByType: FIELDS,
    })).toEqual([{ command: 'rename_page', page_id: pageId, title: 'Nytt namn' }]);
  });
});

describe('coalesce', () => {
  it('collapses a run of keystrokes in one field into the value that survived', () => {
    const typed = 'Vatten'.split('').map((_, i) => ({
      command: 'update_text', page_id: 'p', block_id: 'b', field: 'heading',
      value: 'Vatten'.slice(0, i + 1),
    }));
    expect(coalesce(typed)).toEqual([{
      command: 'update_text', page_id: 'p', block_id: 'b', field: 'heading', value: 'Vatten',
    }]);
  });

  it('keeps edits to different fields apart', () => {
    const commands = [
      { command: 'update_text', page_id: 'p', block_id: 'b', field: 'heading', value: 'A' },
      { command: 'update_text', page_id: 'p', block_id: 'b', field: 'preamble', value: 'B' },
    ];
    expect(coalesce(commands)).toHaveLength(2);
  });

  it('keeps edits to different blocks apart', () => {
    const commands = [
      { command: 'update_text', page_id: 'p', block_id: 'b1', field: 'heading', value: 'A' },
      { command: 'update_text', page_id: 'p', block_id: 'b2', field: 'heading', value: 'B' },
    ];
    expect(coalesce(commands)).toHaveLength(2);
  });

  it('never merges across a structural change', () => {
    const commands = [
      { command: 'update_text', page_id: 'p', block_id: 'b', field: 'heading', value: 'A' },
      { command: 'delete_block', page_id: 'p', block_id: 'x' },
      { command: 'update_text', page_id: 'p', block_id: 'b', field: 'heading', value: 'B' },
    ];
    expect(coalesce(commands)).toHaveLength(3);
  });
});

describe('toPuckData', () => {
  it('moves the block id into props and leaves the values alone', () => {
    const data = toPuckData({
      title: 'Start',
      content: [{ id: 'b1', type: 'Hero', props: { heading: 'Hej' } }],
    });
    expect(data).toEqual({
      root: { props: { title: 'Start' } },
      content: [{ type: 'Hero', props: { heading: 'Hej', id: 'b1' } }],
    });
  });

  it('keeps domain-only metadata out of the editor entirely', () => {
    const data = toPuckData({
      title: 'Start',
      content: [{
        id: 'b1', type: 'Hero', props: { heading: 'Hej' },
        grounding: 'grounded', sources: [{ document_name: 'Stadgar.pdf' }],
      }],
    });
    expect(data.content[0].props).not.toHaveProperty('grounding');
    expect(data.content[0].props).not.toHaveProperty('sources');
  });
});

describe('groundingMetadata', () => {
  it('keys the evidence by block so the canvas can badge it', () => {
    const meta = groundingMetadata({
      content: [{
        id: 'b1', type: 'Hero', props: {}, grounding: 'grounded',
        grounding_label: 'Hämtat ur föreningens dokument',
        sources: [{ document_name: 'Stadgar.pdf', page: 3 }],
      }],
    });
    expect(meta.b1.grounding).toBe('grounded');
    expect(meta.b1.sources[0].document_name).toBe('Stadgar.pdf');
  });
});
