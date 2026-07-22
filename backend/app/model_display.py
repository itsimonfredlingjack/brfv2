"""Human-friendly display name for a raw model identifier.

Self-hosted deployments configure a terse alias (BRF_LLM_MODEL, e.g.
"gemma4:e12b"); the OpenAI-compat server itself reports something else
entirely (a full GGUF weights-file path) via /v1/models. Neither is fit to
show a user. This maps known aliases to a friendly label; anything
unrecognized falls back to the raw identifier untouched — never a fabricated
name for a model this table doesn't know about.
"""

from __future__ import annotations

KNOWN_MODEL_DISPLAY_NAMES: dict[str, str] = {
    "gemma4:e12b": "Gemma 4 12B",
    "gemma4:e4b": "Gemma 4 4B",
}


def display_name_for(raw_model: str) -> str:
    if not raw_model:
        return ""
    key = raw_model.strip().lower()
    if key in KNOWN_MODEL_DISPLAY_NAMES:
        return KNOWN_MODEL_DISPLAY_NAMES[key]
    # A weights-file path or other unrecognized identifier still names its
    # model family as a substring (e.g. ".../gemma-4-12b-it-Q4_K_M.gguf") —
    # match on that rather than requiring an exact alias.
    for alias, label in KNOWN_MODEL_DISPLAY_NAMES.items():
        family = alias.split(":")[0].replace("4", "-4-")  # gemma4 -> gemma-4-
        if family in key.replace("_", "-"):
            return label
    return raw_model
