// Human-friendly labels for raw model/provider identifiers reported by the
// backend (/api/health's `llm` object, and AskResponse.provider/model on
// every answered question). Mirrors backend/app/model_display.py's mapping
// so the header status and per-answer provenance never drift from each
// other — anything unrecognized falls back to the raw identifier rather
// than fabricating a name.

const KNOWN_MODEL_DISPLAY_NAMES = {
  'gemma4:e12b': 'Gemma 4 12B',
  'gemma4:e4b': 'Gemma 4 4B',
};

// Only the providers this UI ships alongside. The desktop payload contains no
// hosted provider implementation at all (ops/forbidden_providers.json), so a
// friendly label for one would be a hosted identifier shipped in the artifact
// for a provider that cannot occur. A backend that does report one — the web
// product in development, where the hosted plug-in is installed — falls
// through to the raw identifier, which is the same rule this module already
// applies to every model it does not know.
const PROVIDER_LABELS = {
  selfhosted: 'Self-hosted',
  fake: 'Testläge',
  none: 'Ingen modell',
};

export function displayNameForModel(rawModel) {
  if (!rawModel) return '';
  const key = rawModel.trim().toLowerCase();
  if (KNOWN_MODEL_DISPLAY_NAMES[key]) return KNOWN_MODEL_DISPLAY_NAMES[key];
  const normalized = key.replace(/_/g, '-');
  for (const [alias, label] of Object.entries(KNOWN_MODEL_DISPLAY_NAMES)) {
    const family = alias.split(':')[0].replace('4', '-4-'); // gemma4 -> gemma-4-
    if (normalized.includes(family)) return label;
  }
  return rawModel;
}

export function displayNameForProvider(providerName) {
  return PROVIDER_LABELS[providerName] || providerName || '';
}
