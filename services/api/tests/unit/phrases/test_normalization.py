"""Unit tests for `phrases/domain/normalization.py`.

Scenarios from `specs/phrase-management/spec.md`'s "Text normalization"
requirement (tasks.md Unit 1 / 1.1).
"""

import unicodedata

from app.modules.phrases.domain.normalization import comparison_form, display_form


def test_trim_and_nfc() -> None:
    # "Café" with a decomposed accent (e + combining acute, NFD form).
    decomposed = unicodedata.normalize("NFD", "  Café ")
    assert display_form(decomposed) == "Café"
    assert unicodedata.is_normalized("NFC", display_form(decomposed))


def test_zero_width_and_control_characters_stripped() -> None:
    assert display_form("Buy​ milk\u0007") == "Buy milk"
    # Whitespace controls separate words (not glued into "Buymilknow").
    assert display_form("Buy\tmilk\nnow") == "Buy milk now"


def test_zwj_zwnj_preserved_inside_text() -> None:
    family_emoji = "\U0001f468‍\U0001f469‍\U0001f467"  # man+ZWJ+woman+ZWJ+girl
    assert display_form(family_emoji) == family_emoji

    persian_word_with_zwnj = "می‌خواهم"
    assert display_form(persian_word_with_zwnj) == persian_word_with_zwnj


def test_text_made_only_of_zwj_zwnj_is_empty_after_normalization() -> None:
    assert display_form("‍‌‍") == ""


def test_comparison_form_renormalizes_after_casefold() -> None:
    # U+01F0 casefold()s to "j" + COMBINING CARON (not NFC); re-normalizing
    # recomposes it back to the single precomposed codepoint.
    source = "ǰ"
    folded_without_renormalizing = source.casefold()
    assert not unicodedata.is_normalized("NFC", folded_without_renormalizing)

    result = comparison_form(source)
    assert result == source
    assert unicodedata.is_normalized("NFC", result)


def test_emoji_and_rtl_preserved() -> None:
    milk = "Comprar leche \U0001f95b"
    assert display_form(milk) == milk

    arabic = "شراء الحليب"
    assert display_form(arabic) == arabic


def test_both_forms_are_idempotent() -> None:
    for raw in ["  Café ", "Buy\tmilk\nnow", "Comprar leche \U0001f95b", "شراء الحليب"]:
        once = display_form(raw)
        assert once == display_form(once)
    for raw in ["  Comprar   LECHE ", "ǰ", "Buy\tMilk\nNow"]:
        once = comparison_form(display_form(raw))
        assert once == comparison_form(once)


def test_padding_and_astral_chars_count_as_code_points_after_trim() -> None:
    padded = ("x" * 280) + (" " * 20)
    assert len(display_form(padded)) == 280
    # U+1F95B is one code point despite being outside the BMP (a UTF-16
    # surrogate pair); Python's `len()` on `str` already counts code points.
    assert len(display_form("\U0001f95b")) == 1
