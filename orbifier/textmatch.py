"""
textmatch.py – forgiving text matching for game searches.

Ignores case, accents, trademark symbols and punctuation so that e.g.
"call of duty modern warfare", "Call of Duty: Modern-Warfare" and
"Call of Duty®: Modern Warfare®" all match each other.
"""

import re
import unicodedata

_STRIP_SYMBOLS = str.maketrans("", "", "®™©℠'’`´")
_NON_WORD = re.compile(r"[\W_]+", re.UNICODE)

# Lower score = better match. NO_MATCH means the text doesn't match at all.
EXACT, PREFIX, CONTAINS, COMPACT, TOKENS, NO_MATCH = range(6)


def normalize(text: str) -> str:
    """Lowercase, strip accents/symbols, turn punctuation into single spaces."""
    text = (text or "").translate(_STRIP_SYMBOLS)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower().replace("&", " and ")
    return " ".join(_NON_WORD.sub(" ", text).split())


def match_score(query: str, text: str) -> int:
    """Score how well *query* matches *text* (both raw, unnormalized)."""
    q, t = normalize(query), normalize(text)
    if not q or not t:
        return NO_MATCH
    q_compact, t_compact = q.replace(" ", ""), t.replace(" ", "")
    if q == t or q_compact == t_compact:
        return EXACT
    if t.startswith(q) or t_compact.startswith(q_compact):
        return PREFIX
    if q in t:
        return CONTAINS
    if q_compact in t_compact:
        return COMPACT
    if all(token in t_compact for token in q.split()):
        return TOKENS
    return NO_MATCH


def best_score(query: str, texts) -> int:
    """Best (lowest) score of *query* against any of *texts*."""
    return min((match_score(query, t) for t in texts), default=NO_MATCH)
