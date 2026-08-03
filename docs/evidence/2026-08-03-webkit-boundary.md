# WebKitGTK website-editor repair — 2026-08-03

## Reproduction

Environment:

- WebKitGTK/JSC: `2.52.5` (`pkg-config --modversion webkit2gtk-4.1`)
- Vite: `8.1.5` (Rolldown)
- Puck: `@puckeditor/core 0.22.4`
- dnd-kit state: `0.4.0`
- Signals: `@preact/signals-core 1.14.4`

The original failure had two layers:

1. `src-tauri/tauri.conf.json` enabled Tauri's `freezePrototype`, which injects
   `Object.freeze(Object.prototype)` before application modules run. Signals
   assigned `Signal.prototype.valueOf`, and Puck's `object-hash` browser bundle
   assigned `Buffer.prototype.toString` and `toJSON`. Those names are inherited
   non-writable properties after the freeze, so strict module evaluation threw
   `TypeError: Attempted to assign to readonly property.`
2. After that was repaired, WebKitGTK exposed Puck's `srcdoc` iframe but left its
   document body empty and did not dispatch the iframe `load` event. Puck's
   `AutoFrame` therefore never found `#frame-root` and never mounted the preview.

The generated line/column in the first failure pointed near Signals' prototype
setup. JavaScriptCore reports module readonly-assignment locations incorrectly
in this case; see [WebKit bug 275145](https://bugs.webkit.org/show_bug.cgi?id=275145).

## Repair

`brfv2-mockup/src/webkitCompat.js` is a narrowly scoped Vite compatibility
plugin. It:

- rewrites only Signals' and `object-hash`'s inherited-method assignments to
  equivalent `Object.defineProperty` calls, preserving writable/configurable
  behavior and keeping `freezePrototype: true`;
- patches only Puck 0.22.4's AutoFrame module to poll for the completed iframe,
  recreate Puck's inert `frame-root` when WebKit exposed an empty `srcdoc`
  body, and then let normal React portals render into it.

The lazy import and `WorkspaceBoundary` remain as independent containment for
future editor failures.

## Passing real acceptance

`make website-acceptance RUN_LABEL=2026-08-03-webkit-fixed-final` started a fresh
`tauri-driver`, `WebKitWebDriver`, sidecar backend, and release app. It passed
the complete journey: authenticated startup, empty site, same-origin iframe,
light site stylesheet, block insertion, editing/history, 390px mobile canvas,
publication boundary, rollback, model-less AI refusal, and append-only undo.

The machine-readable receipt and screenshots are:

- `2026-08-03-webkit-fixed-final-website-acceptance.json`
- `2026-08-03-webkit-fixed-final-website-empty.png`
- `2026-08-03-webkit-fixed-final-website-canvas.png`
- `2026-08-03-webkit-fixed-final-website-selected.png`
- `2026-08-03-webkit-fixed-final-website-mobile.png`
- `2026-08-03-webkit-fixed-final-website-published.png`
- `2026-08-03-webkit-fixed-final-website-versions.png`
