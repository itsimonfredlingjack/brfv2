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

const PROVIDER_LABELS = {
  selfhosted: 'Self-hosted',
  'anthropic-api': 'Anthropic',
  'claude-cli': 'Claude CLI',
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
