from pronunciation_coach.phonemes import expected_for_sentence, split_words, tokenize_ipa


def test_strips_stress_and_length_marks():
    assert tokenize_ipa("skˈuːl") == ["s", "k", "u", "l"]
    assert tokenize_ipa("ˌɪntɚnˈæʃənəl") == ["ɪ", "n", "t", "ɚ", "n", "æ", "ʃ", "ə", "n", "ə", "l"]


def test_space_separated_and_glued_inputs_match():
    assert tokenize_ipa("t iː tʃ ɚ") == tokenize_ipa("tˈiːtʃɚ") == ["t", "i", "tʃ", "ɚ"]


def test_multichar_units_are_single_tokens():
    assert tokenize_ipa("dʒ ʌ dʒ") == ["dʒ", "ʌ", "dʒ"]
    assert tokenize_ipa("ɡˈoʊ") == ["ɡ", "oʊ"]
    assert tokenize_ipa("bˈaɪ") == ["b", "aɪ"]


def test_recognizer_composite_tokens_are_resegmented():
    # The model vocabulary contains tokens like "ɑːɹ" and "əl".
    assert tokenize_ipa("k ɑːɹ") == ["k", "ɑ", "ɹ"]
    assert tokenize_ipa("l ɪ ɾ əl") == ["l", "ɪ", "ɾ", "ə", "l"]


def test_folds_espeak_specific_symbols():
    assert tokenize_ipa("ɐbˈaʊt") == ["ə", "b", "aʊ", "t"]
    assert tokenize_ipa("ɹˈoʊzᵻz") == ["ɹ", "oʊ", "z", "ɪ", "z"]
    assert tokenize_ipa("g r") == ["ɡ", "ɹ"]


def test_removes_language_flags_and_separators():
    assert tokenize_ipa("(en)hˈɛloʊ(fr)") == ["h", "ɛ", "l", "oʊ"]
    assert tokenize_ipa("a|b") == ["a", "b"]


def test_split_words_preserves_text():
    sentence = "Hello, world! It's 9 o'clock."
    segs = split_words(sentence)
    assert "".join(s.text for s in segs) == sentence
    assert [s.text for s in segs if s.word is not None] == ["Hello", "world", "It's", "9", "o'clock"]
    assert [s.word for s in segs if s.word is not None] == [0, 1, 2, 3, 4]


def test_expected_for_sentence_uses_word_boundaries(phonemize):
    words = expected_for_sentence("I think, this is good.", phonemize=phonemize)
    assert [w.text for w in words] == ["I", "think", "this", "is", "good"]
    assert words[1].phonemes == ["θ", "ɪ", "ŋ", "k"]
    assert words[2].phonemes == ["ð", "ɪ", "s"]
