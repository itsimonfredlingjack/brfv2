# kalla-native — agent notes

Directory-specific guidance for the Träff native Android app (Expo Router + React Native).

**Repo-wide product, invariants, clients, and commands:** see root [`AGENTS.md`](../AGENTS.md) and [`conductor/`](../conductor/).

## Expo versioned docs (required)

Expo APIs and defaults change across SDK versions. **Read the versioned docs for this app’s SDK before writing code**—do not rely on unversioned “latest” pages alone.

This app targets the Expo SDK documented at:

https://docs.expo.dev/versions/v57.0.0/

If `package.json` / app config show a different SDK major, use the matching `https://docs.expo.dev/versions/vNN.0.0/` tree instead and update this link when you intentionally upgrade.

## Identity

Built during the Källa period; shipped as **Träff**. See `kalla-native/README.md` for rebrand notes. Product API contract matches the mobile PWA (`xs_mobilapp/`) over the shared FastAPI backend.
