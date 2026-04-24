import pytest

from storage_tagger.preprocessing import normalize_query
from storage_taxonomy.normalizer import normalize_text


@pytest.mark.parametrize("raw,expected", [
    ("厨房收纳盒", "厨房收纳盒"),
    ("boîte de rangement", "boîte"),
    ("küchen organizer", "küchen"),
    ("収納ボックス", "収納ボックス"),
])
def test_v0_normalizer_keeps_unicode_letters(raw, expected):
    assert expected in normalize_query(raw)


@pytest.mark.parametrize("raw,expected", [
    ("厨房收纳盒", "厨房收纳盒"),
    ("boîte de rangement", "boîte"),
    ("küchen organizer", "küchen"),
    ("収納ボックス", "収納ボックス"),
])
def test_v1_normalizer_keeps_unicode_letters(raw, expected):
    assert expected in normalize_text(raw)
