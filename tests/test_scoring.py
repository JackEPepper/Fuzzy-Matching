import math

import pytest

from fuzzy_match.scoring import (
    WeightSettings,
    normalize,
    position_weights,
    similarity,
    weighted_distance,
)


def test_identical_strings_score_100():
    assert similarity("Acme", "Acme") == 100.0


def test_blank_values_never_match():
    assert similarity("", "") == 0.0
    assert similarity(None, float("nan")) == 0.0


def test_normalize_case_accents_whitespace_and_replacements():
    s = WeightSettings(replacements={"&": " and "}, regex_replacements={r"\bco\b": "company"})
    assert normalize("  Café  &   Co ", s) == "cafe and company"


def test_case_sensitive_option():
    s = WeightSettings(case_sensitive=True)
    assert similarity("ABC", "abc", s) < 100.0


def test_unweighted_matches_plain_levenshtein():
    s = WeightSettings()
    assert weighted_distance("kitten", "sitting", s) == 3


def test_character_class_weight_reduces_penalty():
    plain = similarity("Acme Co", "Acme-Co.", WeightSettings())
    weighted = similarity(
        "Acme Co", "Acme-Co.", WeightSettings(char_class_weights={"punctuation": 0.1})
    )
    assert weighted > plain


def test_zero_weight_character_is_ignored():
    s = WeightSettings(char_weights={"-": 0.0})
    assert similarity("pied-piper", "piedpiper", s) == 100.0


def test_specific_character_overrides_class():
    s = WeightSettings(char_class_weights={"punctuation": 0.0}, char_weights={"#": 1.0})
    assert similarity("a.b", "ab", s) == 100.0
    assert similarity("a#b", "ab", s) < 100.0


def test_char_weight_keys_are_case_folded():
    s = WeightSettings(char_weights={"X": 0.0})
    assert similarity("abxc", "abc", s) == 100.0


def test_word_weights_multiply_character_weights():
    s = WeightSettings(word_weights={"inc": 0.1})
    w = position_weights("acme inc", s)
    assert w[:4] == [1.0] * 4
    assert all(math.isclose(x, 0.1) for x in w[5:])
    assert similarity("Acme Inc", "Acme", s) > similarity("Acme Inc", "Acme", WeightSettings())


def test_word_weight_only_applies_to_whole_words():
    s = WeightSettings(word_weights={"co": 0.1})
    assert position_weights("cola", s) == [1.0] * 4


def test_substitution_cost_is_symmetric():
    s = WeightSettings(substitution_costs={("0", "o"): 0.2})
    assert weighted_distance("b0b", "bob", s) == pytest.approx(0.2)
    assert weighted_distance("bob", "b0b", s) == pytest.approx(0.2)


def test_score_is_between_0_and_100():
    s = WeightSettings(word_weights={"x": 0.01})
    for a, b in [("x", "yyyy"), ("abc", "xyz"), ("a", "")]:
        assert 0.0 <= similarity(a, b, s) <= 100.0
