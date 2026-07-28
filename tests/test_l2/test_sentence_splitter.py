"""Tests for sentence_splitter.py — the abbreviation/decimal-aware splitter
used to ground Phi4OllamaScorer at the sentence level (see sentiment_agent.py
docstring on why sentence-level grounding matters for mixed-sentiment text).
"""
from __future__ import annotations

from geopulse.l2_orchestration.agents.sentence_splitter import split_sentences


def test_splits_on_real_sentence_boundaries():
    text = "Officials responded within hours. Markets reacted the next day."
    assert split_sentences(text) == [
        "Officials responded within hours.",
        "Markets reacted the next day.",
    ]


def test_does_not_split_on_decimal_percent():
    text = "The strike affected 12.7% of global supply. Markets reacted immediately."
    result = split_sentences(text)
    assert len(result) == 2
    assert "12.7%" in result[0]


def test_does_not_split_on_decimal_dollar_amount():
    text = "Brent crude rose to $69.02 per barrel. Analysts called it unprecedented."
    result = split_sentences(text)
    assert len(result) == 2
    assert "$69.02" in result[0]


def test_does_not_split_on_title_abbreviation():
    text = "Dr. Smith warned of escalation. The situation remains tense."
    result = split_sentences(text)
    assert len(result) == 2
    assert result[0] == "Dr. Smith warned of escalation."


def test_does_not_split_on_place_abbreviation():
    text = "St. Petersburg saw protests. Meanwhile, Gov. Lee called for calm."
    result = split_sentences(text)
    assert result == [
        "St. Petersburg saw protests.",
        "Meanwhile, Gov. Lee called for calm.",
    ]


def test_does_not_split_on_us_abbreviation():
    text = "The U.S. issued a statement. Markets responded calmly."
    result = split_sentences(text)
    assert len(result) == 2
    assert "U.S." in result[0]


def test_handles_question_and_exclamation_marks():
    text = "Is this an escalation? The markets seem to think so! Prices are climbing."
    assert split_sentences(text) == [
        "Is this an escalation?",
        "The markets seem to think so!",
        "Prices are climbing.",
    ]


def test_single_sentence_with_no_terminal_punctuation():
    text = "Just one sentence with no ending punctuation"
    assert split_sentences(text) == [text]


def test_empty_string_returns_empty_list():
    assert split_sentences("") == []
    assert split_sentences("   ") == []


def test_comma_joined_clauses_stay_one_sentence():
    """Known, documented limitation: sentence splitting only helps when
    mixed sentiment spans separate sentences. A single sentence with two
    comma-joined clauses of opposite sentiment ("X, but Y") is NOT split —
    that's still the scoring model's job to handle, not the splitter's."""
    text = "The attack caused an initial panic, but a swift agreement helped prices recover"
    assert split_sentences(text) == [text]


def test_multiple_abbreviations_in_sequence():
    text = "Sen. Warren issued a statement. Rep. Johnson disagreed."
    assert split_sentences(text) == [
        "Sen. Warren issued a statement.",
        "Rep. Johnson disagreed.",
    ]
