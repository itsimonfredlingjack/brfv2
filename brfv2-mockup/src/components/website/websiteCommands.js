// Turning what a person did in the editor into the same commands the AI sends.
//
// This module is the human half of the "one command engine" rule. The editor
// library has its own action vocabulary (insert / reorder / replace / remove /
// duplicate, addressed by index and zone); the product has its own (insert_block
// / move_block / update_text …, addressed by block id). Everything below is the
// translation between them, and it exists so that dragging a section and asking
// the AI to move it end up in exactly the same validator on the server.
//
// Two rules it must never break:
//
// 1. **Never send a page.** A `replace` action carries a whole component object,
//    and forwarding it as-is would be the replacement write this codebase has
//    already been bitten by. `diffProps` reduces it to the keys that actually
//    changed, so two people editing different fields of the same block produce
//    two changes rather than one silently winning.
// 2. **Never forward a bulk action.** `setData` / `set` are what Puck dispatches
//    when *we* load or re-sync its state, and echoing those back to the server
//    would turn a refresh into a write.
//
// Pure functions, no fetch, no React: the mapping is the part worth testing on
// its own, and websiteCommands.test.js does.

export const ROOT_ZONE_SUFFIX = ':default-zone';

/** Actions that describe an edit. Everything else is Puck talking to itself. */
const EDIT_ACTIONS = new Set(['insert', 'remove', 'reorder', 'move', 'replace', 'duplicate', 'replaceRoot']);

const contentOf = (state) => state?.data?.content || [];
const idOf = (item) => item?.props?.id || '';

/**
 * Domain props out of Puck props: drop `id` (which is the block's identity, not
 * one of its values) and anything the component does not declare.
 *
 * Filtering against the declared fields rather than trusting the payload is
 * belt-and-braces — the server refuses unknown props anyway — but it keeps a
 * stray internal key from turning an ordinary edit into a 422 the operator
 * cannot act on.
 */
export function domainProps(props, fieldNames) {
  const out = {};
  Object.entries(props || {}).forEach(([key, value]) => {
    if (key === 'id' || key === 'puck') return;
    if (fieldNames && !fieldNames.includes(key)) return;
    out[key] = value;
  });
  return out;
}

const same = (a, b) => JSON.stringify(a ?? null) === JSON.stringify(b ?? null);

/** Only the keys whose value actually differs. */
export function diffProps(before, after, fieldNames) {
  const from = domainProps(before, fieldNames);
  const to = domainProps(after, fieldNames);
  const changed = {};
  Object.keys(to).forEach((key) => {
    if (!same(from[key], to[key])) changed[key] = to[key];
  });
  return changed;
}

/**
 * One Puck action → zero or more product commands.
 *
 * `fieldsByType` comes from the backend's own vocabulary, so the editor and the
 * validator agree on what a component's fields are called.
 */
export function actionToCommands({ action, appState, prevAppState, pageId, fieldsByType = {} }) {
  if (!action || !EDIT_ACTIONS.has(action.type) || !pageId) return [];

  const next = contentOf(appState);
  const prev = contentOf(prevAppState);
  const fieldsFor = (type) => fieldsByType[type];

  switch (action.type) {
    case 'insert': {
      const item = next[action.destinationIndex];
      if (!item) return [];
      return [{
        command: 'insert_block',
        page_id: pageId,
        type: item.type,
        // The id Puck minted travels with the command so the server stores the
        // same one. Without it a retry — or the re-sync after it — would leave
        // the canvas pointing at a block id the server never used.
        block_id: idOf(item),
        props: domainProps(item.props, fieldsFor(item.type)),
        index: action.destinationIndex,
      }];
    }

    case 'duplicate': {
      const source = prev[action.sourceIndex];
      const copy = next[action.sourceIndex + 1];
      if (!source || !copy) return [];
      return [{
        command: 'duplicate_block',
        page_id: pageId,
        block_id: idOf(source),
        block_id_new: idOf(copy),
      }];
    }

    case 'remove': {
      const gone = prev[action.index];
      if (!gone) return [];
      return [{ command: 'delete_block', page_id: pageId, block_id: idOf(gone) }];
    }

    case 'reorder':
    case 'move': {
      const moved = prev[action.sourceIndex];
      if (!moved) return [];
      if (action.sourceIndex === action.destinationIndex) return [];
      return [{
        command: 'move_block',
        page_id: pageId,
        block_id: idOf(moved),
        // `index` is the position in the finished list, which is what a drag
        // reports. The server reads it that way; `after_block_id` is the other
        // spelling, and is what the AI uses.
        index: action.destinationIndex,
      }];
    }

    case 'replace': {
      const before = prev[action.destinationIndex];
      const after = action.data;
      if (!after) return [];
      const blockId = idOf(after) || idOf(before);
      if (!blockId) return [];
      const changed = diffProps(before?.props, after.props, fieldsFor(after.type));
      const keys = Object.keys(changed);
      if (keys.length === 0) return [];
      // A single text field is the overwhelmingly common case (somebody is
      // typing), and update_text is the command that cannot touch anything else.
      if (keys.length === 1 && typeof changed[keys[0]] === 'string') {
        return [{
          command: 'update_text',
          page_id: pageId,
          block_id: blockId,
          field: keys[0],
          value: changed[keys[0]],
        }];
      }
      return [{ command: 'update_block', page_id: pageId, block_id: blockId, props: changed }];
    }

    case 'replaceRoot': {
      const title = action.root?.props?.title;
      const wasTitle = prevAppState?.data?.root?.props?.title;
      if (!title || title === wasTitle) return [];
      return [{ command: 'rename_page', page_id: pageId, title }];
    }

    default:
      return [];
  }
}

/**
 * Merge a run of commands into the fewest that still say the same thing.
 *
 * Typing one word fires an action per keystroke. Sending each one would make the
 * history unreadable and the undo useless — nobody wants to press ångra eleven
 * times to take back "Vattenavstängning". Consecutive edits to the *same field
 * of the same block* collapse into the last value, which is the one that
 * survived anyway.
 */
export function coalesce(commands) {
  const out = [];
  commands.forEach((command) => {
    const last = out[out.length - 1];
    if (
      last
      && command.command === 'update_text'
      && last.command === 'update_text'
      && last.page_id === command.page_id
      && last.block_id === command.block_id
      && last.field === command.field
    ) {
      out[out.length - 1] = { ...last, value: command.value };
      return;
    }
    out.push(command);
  });
  return out;
}

/** A short Swedish name for a batch, used as the history entry's summary. */
export function describeBatch(commands, labelForType = (t) => t) {
  if (commands.length === 0) return '';
  const [first] = commands;
  const more = commands.length > 1 ? ` (+${commands.length - 1})` : '';
  switch (first.command) {
    case 'insert_block':
      return `La till ${labelForType(first.type)}${more}`;
    case 'delete_block':
      return `Tog bort ett block${more}`;
    case 'duplicate_block':
      return `Kopierade ett block${more}`;
    case 'move_block':
      return `Flyttade ett block${more}`;
    case 'update_text':
      return `Ändrade text${more}`;
    case 'update_block':
      return `Ändrade innehåll${more}`;
    case 'rename_page':
      return `Döpte om sidan${more}`;
    default:
      return `Ändrade webbplatsen${more}`;
  }
}

/** Domain page → Puck data. The block's id becomes a Puck prop; nothing else moves. */
export function toPuckData(page) {
  return {
    root: { props: { title: page?.title || '' } },
    content: (page?.content || []).map((block) => ({
      type: block.type,
      props: { ...block.props, id: block.id },
    })),
  };
}

/** Grounding metadata, keyed by block id, for the badges the canvas shows. */
export function groundingMetadata(page) {
  const byBlock = {};
  (page?.content || []).forEach((block) => {
    byBlock[block.id] = {
      grounding: block.grounding,
      grounding_label: block.grounding_label,
      sources: block.sources || [],
    };
  });
  return byBlock;
}
