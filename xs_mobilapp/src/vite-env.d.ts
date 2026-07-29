/// <reference types="vite/client" />

/** Release identifier, injected by vite.config.ts from package.json's
 * version. Used to version the service-worker cache. */
declare const __KALLA_BUILD__: string
