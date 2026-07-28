"""Abbreviation-aware sentence splitting for Agent 6 (sentiment_agent.py).

Why this exists: whole-paragraph sentiment scoring forces one polarity out
of text that may genuinely contain two (see "Markets calmed after the
strike, though officials warn the ceasefire is fragile and could collapse"
in tests/fixtures/sentiment_labeled_set.json — a real mixed-sentiment
failure case for the old whole-blob approach). Splitting into sentences
first and scoring each independently lets Phi4OllamaScorer make a tighter,
better-grounded judgment per sentence, and produces a defensible per-sentence
evidence quote rather than an ambiguous clause pulled from a longer blob.

Why NOT naive `text.split(".")`: that breaks on abbreviations ("U.S.",
"Dr.", "St.", "Inc.", "vs.", "e.g.", "i.e.", "Jan.", "Rep.") and decimal
numbers ("$69.02", "12.7%", "5.7 million barrels") — all common in
geopolitical/financial news text, i.e. exactly this project's domain.

This is a regex-based heuristic splitter, not a full NLP sentence tokenizer
(no spaCy/nltk dependency is added, matching the project's lightweight
dependency footprint per pyproject.toml). It handles the realistic cases in
this domain; it is not claimed to be bulletproof against every edge case in
general English text — treat over- or under-splits on unusual input as a
known limitation, not a silent correctness guarantee.
"""

from __future__ import annotations

import re

# Titles and common abbreviations that precede a name/noun and must NOT be
# treated as a sentence boundary even though they end in a period.
_ABBREVIATIONS = {
    "mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "rep", "sen", "gov",
    "gen", "col", "lt", "capt", "sgt", "adm", "maj",
    "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec",
    "inc", "corp", "co", "ltd", "llc", "vs", "etc", "eg", "ie", "no", "approx",
    "u.s", "u.k", "u.n", "e.u",
}

# Matches a period/!/? that's followed by whitespace + an uppercase letter
# (or end of string) — the usual sentence-boundary shape.
_BOUNDARY_RE = re.compile(r"([.!?])\s+(?=[A-Z\"'\u2018\u201c]|$)")

# Matches a decimal number context around a period: digit.digit
_DECIMAL_RE = re.compile(r"\d\.\d")


def split_sentences(text: str) -> list[str]:
    """Split `text` into sentences, protecting known abbreviations and
    decimal numbers from being treated as sentence boundaries.

    Approach: find candidate boundary positions (. ! ? followed by
    whitespace + capital letter), then reject a candidate if the token
    immediately before the punctuation is a known abbreviation, or if the
    punctuation is actually part of a decimal number.
    """
    if not text or not text.strip():
        return []

    text = text.strip()

    # Protect decimal numbers by temporarily replacing their periods with a
    # placeholder that won't be mistaken for a sentence boundary, then
    # restore afterward. This sidesteps the boundary regex entirely for
    # numbers like "12.7%" or "$69.02" regardless of what follows them.
    placeholder = "\u0000"
    protected = _DECIMAL_RE.sub(lambda m: m.group(0).replace(".", placeholder), text)

    spans: list[str] = []
    last_end = 0
    for m in _BOUNDARY_RE.finditer(protected):
        boundary_pos = m.end(1)  # position right after the punctuation mark
        preceding = protected[last_end:boundary_pos]
        # Extract the last word-token before the punctuation to check against
        # the abbreviation list (case-insensitive).
        last_token = ""
        word_before_period = re.search(r"([A-Za-z]+)\s*[.!?]$", preceding)
        if word_before_period:
            last_token = word_before_period.group(1).lower()

        if m.group(1) == "." and last_token in _ABBREVIATIONS:
            continue  # not a real sentence boundary — keep accumulating

        spans.append(protected[last_end:boundary_pos].strip())
        last_end = m.end()

    tail = protected[last_end:].strip()
    if tail:
        spans.append(tail)

    # Restore protected decimal periods and drop empty fragments.
    return [s.replace(placeholder, ".") for s in spans if s]
