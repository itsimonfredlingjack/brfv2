// Tauri's freezePrototype security option freezes Object.prototype before the
// application module runs. Signals adds methods with assignment syntax; that
// is fine in a normal browser, but strict modules cannot assign an inherited
// non-writable valueOf/toString property. Define those own properties
// explicitly while keeping the prototype freeze enabled.
const FROZEN_PROTOTYPE_MODULE_RE =
  /\/node_modules\/(?:@preact\/signals-core\/dist\/signals-core\.(?:module\.js|mjs)|object-hash\/dist\/object_hash\.js)$/;
const PUCK_AUTOFRAME_MODULE_RE =
  /\/node_modules\/@puckeditor\/core\/dist\/chunk-WH6PO5ND\.mjs$/;
const INHERITED_METHOD_RE =
  /([A-Za-z_$][\w$]*)\.prototype\.(valueOf|toString|toJSON)\s*=\s*(?=function\b)/g;

function functionExpressionEnd(code, functionStart) {
  const openingBrace = code.indexOf('{', functionStart);
  if (openingBrace < 0) return -1;
  let depth = 0;
  let quote = '';
  for (let index = openingBrace; index < code.length; index += 1) {
    const character = code[index];
    const next = code[index + 1];
    if (quote) {
      if (character === '\\') index += 1;
      else if (character === quote) quote = '';
      continue;
    }
    if (character === '"' || character === "'" || character === '`') {
      quote = character;
      continue;
    }
    if (character === '/' && next === '/') {
      const newline = code.indexOf('\n', index + 2);
      index = newline < 0 ? code.length : newline;
      continue;
    }
    if (character === '/' && next === '*') {
      const close = code.indexOf('*/', index + 2);
      index = close < 0 ? code.length : close + 1;
      continue;
    }
    if (character === '{') depth += 1;
    if (character === '}' && --depth === 0) return index + 1;
  }
  return -1;
}

export function patchFrozenPrototypeAssignments(code) {
  let result = '';
  let cursor = 0;
  let match;
  INHERITED_METHOD_RE.lastIndex = 0;
  while ((match = INHERITED_METHOD_RE.exec(code))) {
    const functionStart = code.indexOf('function', match.index);
    const end = functionExpressionEnd(code, functionStart);
    if (functionStart < 0 || end < 0) continue;
    result += code.slice(cursor, match.index);
    result += `Object.defineProperty(${match[1]}.prototype,"${match[2]}",{value:`;
    result += code.slice(functionStart, end);
    result += ',writable:true,configurable:true,enumerable:true})';
    cursor = end;
    INHERITED_METHOD_RE.lastIndex = end;
  }
  return result ? result + code.slice(cursor) : code;
}

export function patchPuckAutoFrame(code) {
  const marker = '  }, [frameRef, loaded, stylesLoaded]);\n  return /* @__PURE__ */ jsx43(\n    "iframe",';
  if (!code.includes(marker)) return code;
  return code.replace(
    marker,
    `  }, [frameRef, loaded, stylesLoaded]);
  // WebKitGTK can complete a srcdoc iframe without dispatching its load event.
  // Puck otherwise never sets loaded and therefore never portals the preview.
  useEffect22(() => {
    let timer;
    let cancelled = false;
    let attempts = 0;
    const activateWhenReady = () => {
      const frame = frameRef.current;
      const doc = frame?.contentDocument;
      if (doc) {
        let root = doc?.getElementById("frame-root");
        // WebKitGTK may expose the srcdoc document while leaving its body
        // unparsed. Recreate only Puck's inert mount point; React still owns
        // all rendered content and the normal srcdoc path remains unchanged.
        //
        // Chromium, though, first exposes a *transient* about:blank document
        // that the srcdoc parse replaces moments later. Creating the mount
        // point in that one made Puck portal the preview into a dead document
        // and the canvas stayed permanently blank in every ordinary browser.
        // So an about:blank document only qualifies after the iframe's load
        // event has had ~half a second to arrive — the WebKitGTK quirk this
        // shim exists for — while the real srcdoc document qualifies at once.
        const settled = doc.URL !== "about:blank" || attempts > 30;
        if (!root && settled && doc?.body && doc.body.childNodes.length === 0) {
          root = doc.createElement("div");
          root.id = "frame-root";
          root.setAttribute("data-puck-entry", "");
          doc.body.appendChild(root);
        }
        if (root) {
          setLoaded(true);
          return;
        }
      }
      attempts += 1;
      if (!cancelled) timer = setTimeout(activateWhenReady, 16);
    };
    activateWhenReady();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [frameRef]);
  return /* @__PURE__ */ jsx43(
    "iframe",`,
  );
}

export function frozenPrototypeCompatibility() {
  return {
    name: 'brf-frozen-prototype-compatibility',
    enforce: 'pre',
    transform(code, id) {
      const patched = FROZEN_PROTOTYPE_MODULE_RE.test(id)
        ? patchFrozenPrototypeAssignments(code)
        : PUCK_AUTOFRAME_MODULE_RE.test(id)
          ? patchPuckAutoFrame(code)
          : code;
      return patched === code ? null : { code: patched, map: null };
    },
  };
}
