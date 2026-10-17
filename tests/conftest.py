import pytest

# Tiny fake lexicon so tests never need espeak-ng or the model.
LEXICON = {
    "i": "ˈaɪ",
    "think": "θˈɪŋk",
    "this": "ðˈɪs",
    "is": "ˈɪz",
    "very": "vˈɛɹi",
    "good": "ɡˈʊd",
    "school": "skˈuːl",
    "the": "ðə",
    "cat": "kˈæt",
    "sat": "sˈæt",
}


def fake_phonemize(words):
    return [LEXICON.get(w.lower(), "") for w in words]


@pytest.fixture
def phonemize():
    return fake_phonemize
