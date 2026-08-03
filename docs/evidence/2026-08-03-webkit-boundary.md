# WebKitGTK website-editor boundary — 2026-08-03

## Reproduction

Environment:

- WebKitGTK/JSC: `2.52.5` (`pkg-config --modversion webkit2gtk-4.1`)
- Vite: `8.1.5` (Rolldown)
- Puck: `@puckeditor/core 0.22.4`
- dnd-kit state: `0.4.0`
- Signals: `@preact/signals-core 1.14.4`

`make website-acceptance RUN_LABEL=2026-08-03-webkit-investigation` started a
fresh `tauri-driver`, `WebKitWebDriver`, sidecar backend, and release app. It
reached the authenticated product and the Hemsidan workspace, then the lazy
editor import rejected before the empty-workspace card rendered:

`TypeError: Attempted to assign to readonly property.`

The machine-readable receipt and screenshot are:

- `2026-08-03-webkit-investigation-website-acceptance.json`
- `2026-08-03-webkit-investigation-website-failure.png`

A diagnostic build temporarily displayed the JavaScript stack. It identified
the generated `Website` chunk at line 2, column 7595. A Vite source-map build
mapped that generated position into
`@preact/signals-core/dist/signals-core.module.js`, near its prototype setup.
That position is not treated as the exact write: JavaScriptCore has a known
module-mode bug that reports readonly-assignment errors at an earlier source
position; see [WebKit bug 275145](https://bugs.webkit.org/show_bug.cgi?id=275145).

Isolated checks narrowed the boundary but did not produce a safe production
repair:

1. Direct JSC evaluation of Signals passed.
2. A Vite-built dnd-kit `ValueHistory` entry passed JSC.
3. A Vite-built Puck entry passed JSC with minimal browser stubs.
4. The full real Tauri/WebKitGTK application still fails when the website
   workspace is opened.

## Repair attempts

Two compatibility candidates were built and exercised through the real
acceptance harness, then reverted because both reproduced the same failure:

- `2026-08-03-webkit-es2019-website-acceptance.json`: Vite target lowered to
  ES2019; failed before the empty workspace.
- `2026-08-03-webkit-cjs-signals-website-acceptance.json`: Signals aliased to
  its CommonJS distribution; failed before the empty workspace.

The committed Vite configuration remains unchanged. The existing lazy import
and `WorkspaceBoundary` remain in place as containment, but they are not
counted as a fix: the real Tauri acceptance is intentionally recorded as
failed until the editor module can start in WebKitGTK.
