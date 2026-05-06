"""M9 Security utilities.

Centralizes prompt-injection markers and shared safety logic per MASTER §8.
"""

import re

# Phrase markers — matched as whole-word sequences (case-insensitive) so
# substrings inside ordinary words ("reprint secrets-handling guide") do not
# false-positive. Add multi-word phrases verbatim; the compiler escapes them
# and inserts \b on each end.
_PHRASE_MARKERS = (
    "ignore rules",
    "print secrets",
    "disable guardrails",
    "change system behavior",
)

# Literal markers — matched as exact substrings (case-insensitive) because
# they are not natural-language phrases (e.g. HTML comments).
_LITERAL_MARKERS = (
    "<!-- prompt_injection_marker -->",
)

_PHRASE_RE = re.compile(
    r"|".join(rf"\b{re.escape(p)}\b" for p in _PHRASE_MARKERS),
    re.IGNORECASE,
)

# Public for backward compatibility; callers should prefer is_injection_flagged.
INJECTION_MARKERS = _PHRASE_MARKERS + _LITERAL_MARKERS


def is_injection_flagged(text: str) -> bool:
    """Return True if text contains any known injection markers."""
    if _PHRASE_RE.search(text):
        return True
    low = text.lower()
    return any(m in low for m in _LITERAL_MARKERS)
